import os
import asyncio

from decimal import Decimal
from datetime import date, datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, cast

from tastytrade import Account, Session, DXLinkStreamer, API_URL
from tastytrade.account import CurrentPosition
from tastytrade.instruments import (get_option_chain, 
                                    InstrumentType,
                                    Cryptocurrency, Equity,
                                    Future, FutureOption,
                                    Option, OptionType,
                                    NestedFutureOptionChain,
                                    NestedFutureOptionChainExpiration,
                                    NestedOptionChain,
                                    NestedOptionChainExpiration)
from tastytrade.dxfeed import Quote, Greeks, Trade, Summary
from tastytrade.metrics import MarketMetricInfo, a_get_market_metrics
from tastytrade.order import (NewOrder, NewComplexOrder, OrderAction, OrderType, OrderTimeInForce, PriceEffect, PlacedOrderResponse, TradeableTastytradeJsonDataclass)
from tastytrade.streamer import EventType
from tastytrade.utils import today_in_new_york, now_in_new_york, TastytradeError
from utils.log import get_logger, log_error

logger = get_logger(__name__)
ZERO = Decimal(0)


def serialize_datetime(obj): 
    if isinstance(obj, datetime) or isinstance(obj, date): 
        return obj.isoformat() 
    raise TypeError(f'Type {type(obj)} is not serializable') 


class OrderDirection(Enum):
    BTO = 'BTO'
    STO = 'STO'
    BTC = 'BTC'
    STC = 'STC'


@dataclass
class WebHookData:
    ticker: str
    price: Decimal
    timestamp: datetime
    action: OrderDirection
    quantity: int
    strike: Decimal
    expiration: date
    DTE: Optional[int] = None


@dataclass
class Position(CurrentPosition):
    streamer_symbol:str = None
    direction:int = None
    strike_price:Decimal = None
    close_price_prev:Decimal = None
    day_change:Decimal = None
    pnl_day:Decimal = None
    pnl_total:Decimal = None
    mark_price:Decimal = None
    trade_price:Decimal = None
    iv_rank:float = None
    delta:float = None
    theta:float = None
    gamma:float = None
    beta_weighted_delta:float = None
    net_liquidity:Decimal = None
    dividend_next_date:date = None
    earnings_next_date:date = None

    def __init__(self, curPos: CurrentPosition):
        super().__init__(**vars(curPos))


@dataclass 
class PositionsSummary:
    positions:List[Position] = field(default_factory=list)
    net_liquidity:Decimal = Decimal(0)
    pnl_total:Decimal = Decimal(0)
    pnl_day:Decimal = Decimal(0)
    delta:Decimal = Decimal(0)
    theta:Decimal = Decimal(0)
    gamma:Decimal = Decimal(0)
    beta_weighted_delta:Decimal = Decimal(0)


class TastytradeSessionMeta(type):
    @staticmethod
    def get_credentials() -> tuple[str, str]:
        username = os.getenv('TT_USERNAME')
        password = os.getenv('TT_PASSWORD')

        if not username:
            raise Exception('Username is not provided!')
        if not password:
            raise Exception('Password is not provided!')

        return username, password


    def __new__(cls, name, bases, attrs):
        username, password = TastytradeSessionMeta.get_credentials()
        session = Session(username, password)
        attrs['session'] = session
        accounts = [acc for acc in Account.get_accounts(session) if not acc.is_closed]
        attrs['accounts'] = accounts 
        logger.info(f'New session is created at the start of the program.')
        logger.info(f'Accounts {", ".join([a.account_number for a in accounts])} are available for trading.')
        return super().__new__(cls, name, bases, attrs)


class TastytradeSession(metaclass=TastytradeSessionMeta):
    session: Session = None
    accounts: list[Account] = []


    @staticmethod
    def get_session() -> Session:
        if TastytradeSession.session is None or not TastytradeSession.session.validate():
            # either the token expired or doesn't exist
            username, password = TastytradeSessionMeta.get_credentials()
            TastytradeSession.session = Session(username, password)
            TastytradeSession.accounts = [acc for acc in Account.get_accounts(TastytradeSession.session) if not acc.is_closed]
            # write session token to cache
            logger.info('Logged in with new session, cached for next login.')
        else:
            logger.info('Logged in with cached session.')
        return TastytradeSession.session
    

    @staticmethod
    def get_account(account_number: str = None) -> Account:
        if not account_number:
            account_number = os.getenv('TT_ACCOUNT')
        if not account_number:
            raise Exception('Account number is not provided!')        
        try:
            return next(a for a in TastytradeSession.accounts if a.account_number == account_number)
        except StopIteration:
            err_msg = f'Account {account_number} is provided, but the account doesn\'t appear to exist!'
            logger.error(err_msg)
            raise Exception(err_msg)
    
    
    @staticmethod
    def round_to_width(x, base=Decimal(1)):
        return base * round(x / base)
    
    
    @staticmethod
    def is_monthly(day: date) -> bool:
        return day.weekday() == 4 and 15 <= day.day <= 21


    @staticmethod
    def round_to_width(x, base=Decimal(1)):
        return base * round(x / base)

    def __init__(self):
        TastytradeSession.get_session()


    async def _listen_events(self, event_type: EventType, symbols:List[str], retry:int=5, delay_secs:float=5):
        try:
            data_dict:dict = {}
            async with DXLinkStreamer(TastytradeSession.get_session()) as streamer:
                await streamer.subscribe(event_type, symbols)            
                async for data in streamer.listen(event_type):
                    data_dict[data.eventSymbol] = data
                    if len(data_dict) >= len(symbols): break
                return data_dict
        except Exception as ex:
            if retry <= 0:
                raise ex
            retry -= 1
            await asyncio.sleep(delay_secs)
            

    def test_order_handle_errors(
                self,
                session: Session,
                account: Account,
                order: NewOrder
            ) -> Optional[PlacedOrderResponse]:
        url = f'{API_URL}/accounts/{account.account_number}/orders/dry-run'
        json = order.model_dump_json(exclude_none=True, by_alias=True)
        response = session.sync_client.post(url, data=json)
        # modified to use our error handling
        if response.status_code // 100 != 2:
            content = response.json()['error']
            log_error(f"{content['message']}", logger=logger)
            errors = content.get('errors')
            if errors is not None:
                for error in errors:
                    if "code" in error:
                        log_error(f"{error['message']}", logger=logger)
                    else:
                        log_error(f"{error['reason']}", logger=logger)
            return None
        else:
            data = response.json()['data']
            return PlacedOrderResponse(**data)


    async def send_option_order(self, option_type: OptionType,
            symbol: str, quantity: int,
            strike: Optional[Decimal] = None, delta: Optional[int] = None,
            expiration: Optional[date] = None, dte: Optional[int] = None,
            width: Optional[int] = None, order_type:OrderType = OrderType.MARKET,
            stop_price: Optional[Decimal] = None,
            gtc: bool = False, weeklies: bool = False):

        is_future = symbol[0] == '/'
        option_type_str = 'call' if option_type == OptionType.CALL else 'put'
        option_streamer_symbol = 'call_streamer_symbol' if option_type == OptionType.CALL else 'put_streamer_symbol'
        accepted_order_types = [OrderType.LIMIT, OrderType.MARKET, OrderType.STOP]
        error_msg = []        
        error_header = f'ERROR in option order command: {option_type_str.upper()} symbol: {symbol}, quantity: {quantity}, strike: {strike}, delta: {delta}, expiration: {expiration}, dte: {dte}, width: {width}, order_type: {order_type}, gtc: {gtc}, weeklies: {weeklies}'

        if option_type not in [OptionType.CALL, OptionType.PUT]:
            error_msg.append(f'Invalid option type. Accepted types: {OptionType.CALL}, {OptionType.PUT}')
        if order_type not in accepted_order_types:
            error_msg.append(f'Invalid order type. Accepted types: {accepted_order_types}')
        if quantity is None or quantity == 0:
            error_msg.append('Quantity cannot be zero or None.')
        if order_type == OrderType.STOP and stop_price is None:
            error_msg.append('Specify stop price for stop orders.')
        if expiration is None and dte is None:
            error_msg.append('Specify either expiration or dte for the option.')
        if strike is not None and delta is not None:
            error_msg.append('Specify either delta or strike, but not both.')
        if not strike and not delta:
            error_msg.append('Specify either delta or strike for the option.')
        if delta is not None and abs(delta) > 99:
            error_msg.append('Delta value is too high, -99 <= delta <= 99.')
        if width is not None and width <= 0:
            error_msg.append('Width must be a positive integer where 1 means next strike etc.')
        if width is not None and order_type == OrderType.MARKET:
            error_msg.append('Width (ie spread) is not supported for market orders.')            

        tt_session:Session = TastytradeSession.get_session()
        if tt_session is None:
            error_msg.append('Session cannot be created.')
        else:
            if is_future:  # futures options
                chain = NestedFutureOptionChain.get_chain(tt_session, symbol)
                if dte is None:
                    subchain = None
                    option_chain = chain.option_chains[0]
                    exps = [e for e in option_chain.expirations if e.expiration_date == expiration]
                    if len(exps) == 1:
                        subchain = exps[0]
                    else:
                        error_msg.append(f'Expiration not found.')
                else:
                    subchain = min(chain.option_chains[0].expirations, key=lambda exp: abs(exp.days_to_expiration - dte))
                    tick_size = subchain.tick_sizes[0].value
            else:
                chain = NestedOptionChain.get_chain(tt_session, symbol)
                if dte is None:
                    exps = [e for e in chain.expirations if e.expiration_date == expiration]
                    if len(exps) == 1:
                        subchain = exps[0]
                    else:
                        error_msg.append(f'Expiration not found.')
                else:
                    subchain = min(chain.expirations, key=lambda exp: abs((exp.expiration_date - datetime.now().date()).days - dte))
                    tick_size = chain.tick_sizes[0].value

        if len(error_msg) > 0:
            log_error('\n'.join(error_msg), error_header, logger)
            return

        # precision = tick_size.as_tuple().exponent
        # precision = abs(precision) if precision < 0 else ZERO
        # precision_str = f'.{precision}f'

        # find the closest strike to the delta
        if strike:
            option_at_strike = next(s for s in subchain.strikes if s.strike_price == strike)
        else:
            delta = Decimal(delta)
            delta = delta if option_type == OptionType.CALL else -delta
            option_symbols = [getattr(s, option_streamer_symbol) for s in subchain.strikes]
            greeks_dict = await self._listen_events(Greeks, option_symbols)
            greeks:List[Greeks] = list(greeks_dict.values())

            lowest = Decimal(1)
            greeks_at_strike = None
            for g in greeks:
                diff = abs(g.delta - delta)
                if diff < lowest:
                    greeks_at_strike = g
                    lowest = diff
            # find option with the closest delta
            option_at_strike = next(s for s in subchain.strikes if getattr(s, option_streamer_symbol) == greeks_at_strike.eventSymbol)

        if width:
            if option_type == OptionType.CALL:
                spread_strikes = [s for s in subchain.strikes if s.strike_price > option_at_strike.strike_price]
            else:
                spread_strikes = [s for s in sorted(subchain.strikes, key=lambda x: x.strike_price, reverse=True) if s.strike_price < option_at_strike.strike_price]
            if len(spread_strikes) < width:
                log_error(f'No second leg strikes available for {option_type_str} spread with strike {option_at_strike.strike_price} and width {width}.', error_header, logger)
                return
            spread_strike = spread_strikes[width - 1]

            if order_type == OrderType.LIMIT or order_type == OrderType.MARKET:
                quote_dict = await self._listen_events(Quote, [getattr(option_at_strike, option_streamer_symbol), getattr(spread_strike, option_streamer_symbol)])
                bid = quote_dict[getattr(option_at_strike, option_streamer_symbol)].bidPrice - quote_dict[getattr(spread_strike, option_streamer_symbol)].askPrice
                ask = quote_dict[getattr(option_at_strike, option_streamer_symbol)].askPrice - quote_dict[getattr(spread_strike, option_streamer_symbol)].bidPrice
                mid = (bid + ask) / Decimal(2)
                mid = TastytradeSession.round_to_width(mid, tick_size)
                mid = mid if quantity < 0 else -mid
            elif order_type == OrderType.STOP:
                mid = None
                # TODO: implement stop price for spreads
        else:
            if order_type == OrderType.LIMIT or order_type == OrderType.MARKET:
                quote_dict = await self._listen_events(Quote, [getattr(option_at_strike, option_streamer_symbol)])
                quote = quote_dict[getattr(option_at_strike, option_streamer_symbol)]
                bid = quote.bidPrice
                ask = quote.askPrice
                mid = (bid + ask) / Decimal(2)
                mid = TastytradeSession.round_to_width(mid, tick_size)
                mid = mid if quantity < 0 else -mid
            elif order_type == OrderType.STOP:
                mid = None
                # TODO: implement stop price for single options

        price = mid # mid price for limit orders, None for stop orders

        short_symbol = next(getattr(s, option_type_str) for s in subchain.strikes if s.strike_price == option_at_strike.strike_price)        
        if width:
            if is_future:  # futures options
                option_legs = FutureOption.get_future_options(tt_session, [short_symbol, getattr(spread_strike, option_type_str)])
            else:
                option_legs = Option.get_options(tt_session, [short_symbol, getattr(spread_strike, option_type_str)])
            option_legs.sort(key=lambda x: x.strike_price, reverse=option_type == OptionType.PUT)
            legs = [
                option_legs[0].build_leg(abs(quantity), OrderAction.SELL_TO_OPEN if quantity < 0 else OrderAction.BUY_TO_OPEN),
                option_legs[1].build_leg(abs(quantity), OrderAction.BUY_TO_OPEN if quantity < 0 else OrderAction.SELL_TO_OPEN)
            ]
        else:
            if is_future:
                option_leg = FutureOption.get_future_option(tt_session, short_symbol)
            else:
                option_leg = Option.get_option(tt_session, short_symbol)
            legs = [option_leg.build_leg(abs(quantity), OrderAction.SELL_TO_OPEN if quantity < 0 else OrderAction.BUY_TO_OPEN)]
        
        if order_type == OrderType.MARKET:
            order = NewOrder(
                time_in_force=OrderTimeInForce.GTC if gtc else OrderTimeInForce.DAY,
                order_type=OrderType.MARKET,
                legs=legs
            )
        elif order_type == OrderType.LIMIT:
            order = NewOrder(
                time_in_force=OrderTimeInForce.GTC if gtc else OrderTimeInForce.DAY,
                order_type=OrderType.LIMIT,
                legs=legs,
                price=price,
                price_effect=PriceEffect.CREDIT if quantity < 0 else PriceEffect.DEBIT
            )
        elif order_type == OrderType.STOP:
            order = NewOrder(
                time_in_force=OrderTimeInForce.GTC if gtc else OrderTimeInForce.DAY,
                order_type=OrderType.STOP,
                legs=legs,
                stop_trigger=price,
                price_effect=PriceEffect.CREDIT if quantity < 0 else PriceEffect.DEBIT
            )
        else:
            log_error(f'Invalid order type {order_type}. Accepted order types are {accepted_order_types}', error_header, logger)
            return
        
        acc = TastytradeSession.get_account()

        # data = self.test_order_handle_errors(tt_session, acc, order)
        # if data is None:
        #     return

        acc_balances = acc.get_balances(tt_session)
        nl = acc_balances.net_liquidating_value
        # bp = data.buying_power_effect.change_in_buying_power
        # percent = bp / nl * Decimal(100)
        # fees = data.fee_calculation.total_fees

        try:
            order_resp:PlacedOrderResponse = acc.place_order(tt_session, order, dry_run=True)
        except TastytradeError as e:
            err_msg = str(e) + f'\nOptions BP: ${acc_balances.derivative_buying_power}'
            if price is not None:
                err_msg += f'\nPrice: {price}'
            log_error(err_msg, error_header, logger)
            return
        
        order_resp:PlacedOrderResponse = acc.place_order(tt_session, order, dry_run=False)
        newline_tab = '\n\t'
        tab = '\t'
        if order_resp.errors is None or len(order_resp.errors) == 0:
            if order_resp.warnings is not None and len(order_resp.warnings) > 0:
                logger.warning(f'Order placed with warnings:{newline_tab}{newline_tab.join([f"code: {o.code}{tab}message: {o.message}" for o in order_resp.warnings])}')
            logger.info(f'Order placed successfully.\
                Buying power effect: {order_resp.buying_power_effect}, {order_resp.buying_power_effect / nl * Decimal(100):.2f}%\n \
                Fees: {order_resp.fee_calculation}')
        else:
            log_error(
                f'Order placement failed. Errors:{newline_tab}{newline_tab.join([f"code: {o.code}{tab}message: {o.message}" for o in order_resp.errors])}', error_header, logger)


    async def get_positions(self, account:Account = None) -> PositionsSummary:
        if TastytradeSession.session is None or not TastytradeSession.session.validate():
            raise Exception('Session is not established')
        today = today_in_new_york()
        if account is None:
            account = TastytradeSession.get_account()
        positions = await account.a_get_positions(TastytradeSession.session, include_marks=True)
        if not positions:
            return []
        positions.sort(key=lambda pos: pos.symbol)
        #pos_dict = {pos.symbol: pos for pos in positions}

        async with asyncio.TaskGroup() as tg:
            options_symbols = [
                p.symbol
                for p in positions
                if p.instrument_type == InstrumentType.EQUITY_OPTION
            ]
            if options_symbols:
                options_task = tg.create_task(Option.a_get_options(TastytradeSession.session, options_symbols))
            else:
                options_task = None
            
            future_options_symbols = [
                p.symbol
                for p in positions
                if p.instrument_type == InstrumentType.FUTURE_OPTION
            ]
            if future_options_symbols:
                future_options_task = tg.create_task(FutureOption.a_get_future_options(TastytradeSession.session, future_options_symbols))
            else:
                future_options_task = None
            
            equity_symbols = [
                p.symbol 
                for p in positions
                if p.instrument_type == InstrumentType.EQUITY]
            if equity_symbols:
                equities_task = tg.create_task(Equity.a_get_equities(TastytradeSession.session, equity_symbols))
            else:
                equities_task = None

            crypto_symbols = [
                p.symbol
                for p in positions
                if p.instrument_type == InstrumentType.CRYPTOCURRENCY
            ]
            if crypto_symbols:
                cryptos_task = tg.create_task(Cryptocurrency.a_get_cryptocurrencies(TastytradeSession.session, crypto_symbols))
            else:
                cryptos_task = None
        
        options = options_task.result() if options_task else []
        future_options = future_options_task.result() if future_options_task else []
        equities = equities_task.result() if equities_task else []
        cryptos = cryptos_task.result() if cryptos_task else []

        futures_symbols = [
            p.symbol
            for p in positions
            if p.instrument_type == InstrumentType.FUTURE
        ] + [fo.underlying_symbol for fo in future_options]
        futures = (await Future.a_get_futures(TastytradeSession.session, futures_symbols)
                if futures_symbols else [])
        
        options_dict = {o.symbol: o for o in options}
        future_options_dict = {fo.symbol: fo for fo in future_options}
        #equity_dict = {e.symbol: e for e in equities}
        futures_dict = {f.symbol: f for f in futures}
        crypto_dict = {c.symbol: c for c in cryptos}

        greeks_symbols = ([o.streamer_symbol for o in options] +
                        [fo.streamer_symbol for fo in future_options])
        all_symbols = list(set(
            [o.underlying_symbol for o in options] +
            [c.streamer_symbol for c in cryptos] +
            equity_symbols +
            [f.streamer_symbol for f in futures]
        )) + greeks_symbols

        async with asyncio.TaskGroup() as tg:
            greeks_task = tg.create_task(self._listen_events(Greeks, greeks_symbols))
            summary_task = tg.create_task(self._listen_events(Summary, all_symbols))
            trade_task = tg.create_task(self._listen_events(Trade, ['SPY']))

        greeks_dict: dict[str, Greeks] = greeks_task.result()
        summary_dict: dict[str, Summary] = summary_task.result()
        spy_dict: dict[str, Trade] = trade_task.result()
        spy = spy_dict['SPY']

        # greeks_dict: dict[str, Greeks] = await self._listen_events(Greeks, greeks_symbols)
        # summary_dict: dict[str, Summary] = await self._listen_events(Summary, all_symbols)        
        # spy = (await self._listen_events(Trade, ['SPY']))['SPY']

        spy_price = spy.price or 0
        tt_symbols = set(pos.symbol for pos in positions)
        tt_symbols.update(set(o.underlying_symbol for o in options))
        tt_symbols.update(set(o.underlying_symbol for o in future_options))
        metrics_list = await a_get_market_metrics(TastytradeSession.session, list(tt_symbols))
        metrics_dict = {metric.symbol: metric for metric in metrics_list}

        sums = PositionsSummary()

        for i, pos in enumerate(positions):
            ps = Position(pos)
            mark_price = pos.mark_price or 0 # current price of the position. For options, it's an option price 
            mark = pos.mark or 0 # mark_price * quantity * multiplier, i.e. total value of the position, i.e. net liquidity
            ps.direction = (1 if pos.quantity_direction == 'Long' else -1)
            # instrument type specific calculations
            if pos.instrument_type == InstrumentType.EQUITY_OPTION:
                o = options_dict[pos.symbol]
                ps.streamer_symbol = o.streamer_symbol
                ps.strike_price = o.strike_price
                ps.close_price_prev = summary_dict[o.streamer_symbol].prevDayClosePrice
                metrics = metrics_dict[o.underlying_symbol]
                ps.day_change = mark_price - (ps.close_price_prev or ZERO)  # type: ignore
                ps.pnl_day = ps.day_change * pos.quantity * pos.multiplier
                ps.pnl_total = ps.direction * (mark_price - pos.average_open_price) * pos.multiplier
                ps.trade_price = pos.average_open_price * pos.multiplier
                ps.iv_rank = (metrics.tos_implied_volatility_index_rank or 0) * 100 # to percentage
                ps.delta = greeks_dict[o.streamer_symbol].delta * pos.multiplier * ps.direction  # type: ignore
                ps.theta = greeks_dict[o.streamer_symbol].theta * pos.multiplier * ps.direction  # type: ignore
                ps.gamma = greeks_dict[o.streamer_symbol].gamma * pos.multiplier * ps.direction  # type: ignore
                beta = metrics.beta or 0
                # BWD = beta * stock price * delta / index price
                ps.beta_weighted_delta = beta *  mark * ps.delta / spy_price
                ps.net_liquidity = mark_price * pos.quantity * pos.multiplier
                ps.dividend_next_date = metrics.dividend_next_date
                if metrics.earnings:
                    ps.earnings_next_date = metrics.earnings.expected_report_date
            elif pos.instrument_type == InstrumentType.FUTURE_OPTION:
                o = future_options_dict[pos.symbol]
                f = futures_dict[o.underlying_symbol]
                ps.streamer_symbol = o.streamer_symbol
                ps.strike_price = o.strike_price
                ps.close_price_prev = summary_dict[f.streamer_symbol].prevDayClosePrice
                metrics = metrics_dict[o.root_symbol]
                ps.delta = greeks_dict[o.streamer_symbol].delta * pos.multiplier * ps.direction
                ps.theta = greeks_dict[o.streamer_symbol].theta * pos.multiplier * ps.direction
                ps.gamma = greeks_dict[o.streamer_symbol].gamma * pos.multiplier * ps.direction
                ps.dividend_next_date = metrics.dividend_next_date
                if metrics.earnings:
                    ps.earnings_next_date = metrics.earnings.expected_report_date
                beta = metrics.beta or 0
                # BWD = beta * stock price * delta / index price
                ps.beta_weighted_delta = beta * (ps.close_price_prev or ZERO) * ps.delta / spy_price
                ps.net_liquidity = mark_price * pos.quantity * pos.multiplier
                ps.iv_rank = (metrics.tos_implied_volatility_index_rank or 0) * 100 # to percentage
                ps.trade_price = pos.average_open_price / f.display_factor
                ps.pnl_total = ps.direction * (mark_price - ps.trade_price)
                ps.day_change = mark_price - (ps.close_price_prev or ZERO)  # type: ignore                
                ps.pnl_day = ps.day_change * pos.quantity * pos.multiplier
            elif pos.instrument_type == InstrumentType.EQUITY:
                #e = equity_dict[pos.symbol]
                ps.streamer_symbol = pos.symbol
                ps.close_price_prev = summary_dict[pos.symbol].prevDayClosePrice
                ps.theta = 0
                ps.gamma = 0
                ps.delta = pos.quantity * ps.direction
                metrics = metrics_dict[pos.symbol]
                ps.dividend_next_date = metrics.dividend_next_date
                if metrics.earnings:
                    ps.earnings_next_date = metrics.earnings.expected_report_date
                beta = metrics.beta or 0
                # BWD = beta * stock price * delta / index price
                ps.beta_weighted_delta = beta * mark_price * ps.delta / spy_price
                ps.net_liquidity = mark_price * pos.quantity
                ps.iv_rank = (metrics.tos_implied_volatility_index_rank or 0) * 100 # to percentage
                ps.pnl_total = mark - pos.average_open_price * pos.quantity * ps.direction
                ps.trade_price = pos.average_open_price
                ps.day_change = mark_price - (ps.close_price_prev or ZERO)  # type: ignore
                ps.pnl_day = ps.day_change * pos.quantity
            elif pos.instrument_type == InstrumentType.FUTURE:
                f = futures_dict[pos.symbol]
                ps.close_price_prev = summary_dict[f.streamer_symbol].prevDayClosePrice
                ps.theta = 0
                ps.gamma = 0
                ps.delta = pos.quantity * ps.direction * pos.multiplier
                ps.streamer_symbol = f.streamer_symbol
                metrics = metrics_dict[f.future_product.root_symbol]  # type: ignore
                ps.dividend_next_date = metrics.dividend_next_date
                if metrics.earnings:
                    ps.earnings_next_date = metrics.earnings.expected_report_date
                beta = metrics.beta or 0
                # BWD = beta * stock price * delta / index price
                ps.beta_weighted_delta = beta * mark_price * ps.delta / spy_price
                ps.net_liquidity = mark_price * pos.quantity * pos.multiplier
                ps.iv_rank = (metrics.tw_implied_volatility_index_rank or 0) * 100 # to percentage
                ps.trade_price = pos.average_open_price * f.notional_multiplier
                ps.pnl_total = ps.direction * (mark_price - ps.trade_price) * pos.quantity
                ps.day_change = mark_price - (ps.close_price_prev or ZERO)  # type: ignore
                ps.pnl_day = ps.day_change * pos.quantity * pos.multiplier
            elif pos.instrument_type == InstrumentType.CRYPTOCURRENCY:
                c = crypto_dict[pos.symbol]
                ps.close_price_prev = summary_dict[c.streamer_symbol].prevDayClosePrice
                ps.theta = 0
                ps.gamma = 0
                ps.delta = 0
                ps.beta_weighted_delta = 0
                ps.net_liquidity = mark_price * pos.quantity
                ps.iv_rank = None
                ps.pnl_total = mark - pos.average_open_price * pos.quantity * ps.direction
                ps.trade_price = pos.average_open_price
                ps.quantity = round(pos.quantity, 2)
                ps.streamer_symbol = c.streamer_symbol
                ps.day_change = mark_price - (ps.close_price_prev or ZERO)  # type: ignore
                ps.pnl_day = ps.day_change * pos.quantity * pos.multiplier
            else:
                log_error(f'Skipping {pos.symbol}, unknown instrument type {pos.instrument_type}!', logger=logger)
                continue

            if ps.created_at.date() == today:
                ps.pnl_day = ps.pnl_total
            sums.pnl_total += ps.pnl_total
            sums.pnl_day += ps.pnl_day
            sums.net_liquidity += ps.net_liquidity
            sums.delta += ps.delta
            sums.theta += ps.theta
            sums.gamma += ps.gamma
            sums.beta_weighted_delta += ps.beta_weighted_delta
            sums.positions.append(ps)
        return sums
"""             
            row.extend([
                pos.symbol,
                f'{pos.quantity * ps.direction:g}',
                conditional_color(pnl_day),
                conditional_color(pnl)
            ])
            if table_show_mark:
                row.append(f'${mark_price:.2f}')
            if table_show_trade:
                row.append(f'${trade_price:.2f}')
            row.append(f'{ivr:.1f}' if ivr else '--')
            if table_show_delta:
                row.append(f'{delta:.2f}')
            if table_show_theta:
                row.append(f'{theta:.2f}')
            if table_show_gamma:
                row.append(f'{gamma:.2f}')
            row.extend([
                f'{bwd:.2f}',
                conditional_color(net_liq),
                indicators
            ])
            table.add_row(*row, end_section=(i == len(positions) - 1))
        # summary
        final_row = ['']
        if all:
            final_row.append('')
        final_row.extend([
            '',
            '',
            conditional_color(sums['pnl_day']),
            conditional_color(sums['pnl'])
        ])
        if table_show_mark:
            final_row.append('')
        if table_show_trade:
            final_row.append('')
        final_row.append('')
        if table_show_delta:
            final_row.append('')
        if table_show_theta:
            final_row.append('')
        if table_show_gamma:
            final_row.append('')
        final_row.extend([
            f"{sums['bwd']:.2f}",
            conditional_color(sums['net_liq']),
            ''
        ])
        table.add_row(*final_row)
        console.print(table)
        if not all:
            delta_target = TastytradeSession.session.config.getint('portfolio', 'portfolio-delta-target', fallback=0)  # delta neutral
            delta_variation = TastytradeSession.session.config.getint('portfolio', 'portfolio-delta-variation', fallback=5)
            delta_diff = delta_target - sums['bwd']
            if abs(delta_diff) > delta_variation:
                print_warning(f'Portfolio beta-weighting misses target of {delta_target} substantially!')
        close = get_confirmation('Close out a position? y/N ', default=False)
        if not close:
            return
        # get the position(s) to close
        to_close = input('Enter the number(s) of the leg(s) to include in closing order, separated by commas: ')
        if not to_close:
            return
        to_close = [int(i) for i in to_close.split(',')]
        close_objs = [closing[i] for i in to_close]
        account_number = pos_dict[close_objs[0].symbol].account_number
        if any(pos_dict[o.symbol].account_number != account_number for o in close_objs):
            print('All legs must be in the same account!')
            return
        account = next(a for a in TastytradeSession.session.accounts if a.account_number == account_number)
        legs = []
        total_price = ZERO
        tif = OrderTimeInForce.DAY
        for o in close_objs:
            pos = pos_dict[o.symbol]
            total_price += pos.mark_price * (1 if pos.quantity_direction == 'Long' else -1)  # type: ignore
            if isinstance(o, Future):
                action = (OrderAction.SELL
                        if pos.quantity_direction == 'Long'
                        else OrderAction.BUY)
            else:
                action = (OrderAction.SELL_TO_CLOSE
                        if pos.quantity_direction == 'Long'
                        else OrderAction.BUY_TO_CLOSE)
            if isinstance(o, Cryptocurrency):
                tif = OrderTimeInForce.GTC
            legs.append(o.build_leg(pos.quantity, action))

        console.print(f'Mark price for trade: {conditional_color(total_price)}')
        price = input('Please enter a limit price per quantity (default mark): ')
        if price:
            total_price = Decimal(price)
        else:
            total_price = round(total_price, 2)
        
        order = NewOrder(
            time_in_force=tif,
            order_type=OrderType.LIMIT,
            legs=legs,
            price=abs(total_price),
            price_effect=PriceEffect.CREDIT if total_price > 0 else PriceEffect.DEBIT
        )
        data = self.test_order_handle_errors(account, TastytradeSession.session, order)
        if not data:
            return

        bp = data.buying_power_effect.change_in_buying_power
        bp *= -1 if data.buying_power_effect.change_in_buying_power_effect == PriceEffect.DEBIT else 1
        fees = data.fee_calculation.total_fees if data.fee_calculation else 0

        table = Table(show_header=True, header_style='bold', title_style='bold', title='Order Review')
        table.add_column('Symbol', justify='center')
        table.add_column('Price', justify='center')
        table.add_column('BP Effect', justify='center')
        table.add_column('Fees', justify='center')
        table.add_row(order.legs[0].symbol, conditional_color(total_price),
                    conditional_color(bp), f'[red]${fees:.2f}[/red]')
        for i in range(1, len(order.legs)):
            table.add_row(order.legs[i].symbol, '-', '-', '-')
        console.print(table)

        if data.warnings:
            for warning in data.warnings:
                print_warning(warning.message)
        if get_confirmation('Send order? Y/n '):
            account.place_order(TastytradeSession.session, order, dry_run=False)
"""


@dataclass
class LivePrices:
    quotes: dict[str, Quote]
    greeks: dict[str, Greeks]
    streamer: DXLinkStreamer
    puts: list[Option]
    calls: list[Option]

    @classmethod
    async def create(
        cls,
        session: Session,
        symbol: str = 'SPY',
        expiration: date = today_in_new_york()
    ):
        chain = get_option_chain(session, symbol)
        options = [o for o in chain[expiration]]
        # the `streamer_symbol` property is the symbol used by the streamer
        streamer_symbols = [o.streamer_symbol for o in options]

        streamer = await DXLinkStreamer.create(session)
        puts = [o for o in options if o.option_type == OptionType.PUT]
        calls = [o for o in options if o.option_type == OptionType.CALL]
        self = cls({}, {}, streamer, puts, calls)

        tasks = []
        # subscribe to quotes and greeks for all options on that date
        await streamer.subscribe(Quote, [symbol] + streamer_symbols)
        tasks.append(asyncio.create_task(self._update_quotes()))
        # await streamer.subscribe(Greeks, streamer_symbols)
        # tasks.append(asyncio.create_task(self._update_greeks()))

        asyncio.gather(*tasks)

        # wait we have quotes and greeks for each option
        while len(self.greeks) != len(options) or len(self.quotes) != len(options):
            await asyncio.sleep(1)

        return self

    async def _update_greeks(self):
        async for e in self.streamer.listen(Greeks):
            self.greeks[e.eventSymbol] = e

    async def _update_quotes(self):
        async for e in self.streamer.listen(Quote):
            self.quotes[e.eventSymbol] = e


async def main():
    session = Session(os.getenv('TT_USERNAME'), os.getenv('TT_PASSWORD'))
    live_prices = await LivePrices.create(session, 'SPY')
    # symbol = live_prices.calls.items[0].streamer_symbol
    
    while True:
        #expiration = live_prices.calls.values()[0].expiration
        # live_prices.trades.price
        await asyncio.sleep(1)


    print(live_prices.quotes[symbol], live_prices.greeks[symbol])


if __name__ == '__main__':
    asyncio.run(main())
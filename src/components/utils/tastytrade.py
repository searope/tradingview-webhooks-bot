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
from tastytrade.order import (NewOrder, NewComplexOrder, OrderAction, OrderType, OrderStatus, OrderTimeInForce, PriceEffect, PlacedOrderResponse, TradeableTastytradeJsonDataclass)
from tastytrade.streamer import EventType
from tastytrade.utils import today_in_new_york, now_in_new_york, TastytradeError
from utils.log import get_logger, log_ntfy, LogType

logger = get_logger(__name__)
ZERO = Decimal(0)
NEWLINE = '\n'
TAB = '\t'
NEWLINE_TAB = '\n\t'


def serializer(obj): 
    if isinstance(obj, (datetime, date)): 
        return obj.isoformat() 
    elif isinstance(obj, Decimal):
        return str(obj.quantize(Decimal('0.001')))
    elif isinstance(obj, (CurrentPosition, Position)):
        return obj.__dict__
    elif isinstance(obj, float):
        return round(obj, 2)
    raise TypeError(f'Type {type(obj)} is not serializable') 


class OrderDirection(str, Enum):
    BTO = 'BTO'
    STO = 'STO'
    BTC = 'BTC'
    STC = 'STC'
    BUY = 'BUY'
    SELL = 'SELL'

    def to_order_action(self) -> OrderAction:
        if self == OrderDirection.BTO:
            return OrderAction.BUY_TO_OPEN
        elif self == OrderDirection.STO:
            return OrderAction.SELL_TO_OPEN
        elif self == OrderDirection.BTC:
            return OrderAction.BUY_TO_CLOSE
        elif self == OrderDirection.STC:
            return OrderAction.SELL_TO_CLOSE
        elif self == OrderDirection.BUY:
            return OrderAction.BUY
        elif self == OrderDirection.SELL:
            return OrderAction.SELL
        else:
            raise Exception(f'''
            Invalid OrderDirection: {self}
            Supported order directions are {OrderDirection.BTO}, {OrderDirection.STO}, {OrderDirection.BTC}, {OrderDirection.STC}, {OrderDirection.BUY}, {OrderDirection.SELL}
            ''')


class ExpirationType(str, Enum):
    REGULAR = 'Regular'
    WEEKLY = 'Weekly'
    MONTHLY = 'Regular'
    QUARTERLY = 'Quarterly'


@dataclass
class WebHookData:
    ticker: str
    price: Decimal
    timestamp: datetime
    option_type: OptionType
    action: OrderDirection
    quantity: int
    strike: Optional[Decimal] = None
    delta: Optional[int] = None
    expiration: Optional[date] = None
    dte: Optional[int] = None


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
                    data_dict[data.event_symbol] = data
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
            log_ntfy(LogType.ERROR, f"{content['message']}", logger=logger)
            errors = content.get('errors')
            if errors is not None:
                for error in errors:
                    if "code" in error:
                        log_ntfy(LogType.ERROR, f"{error['message']}", logger=logger)
                    else:
                        log_ntfy(LogType.ERROR, f"{error['reason']}", logger=logger)
            return None
        else:
            data = response.json()['data']
            return PlacedOrderResponse(**data)


    async def send_openinng_option_order(self, option_type: OptionType, symbol: str, quantity: int,
            strike: Optional[Decimal] = None, delta: Optional[int] = None,
            expiration: Optional[date] = None, dte: Optional[int] = None,
            width: Optional[int] = None, order_type:OrderType = OrderType.MARKET,
            stop_price: Optional[Decimal] = None,
            gtc: bool = False, weeklies: bool = False, quarterlies: bool = False):
        """
        Send an BTO or STO option order to Tastyworks. 
        The order will be placed as a single leg order without width or a spread order when width is provided.
        The order will be placed as a market order if order_type is not specified. 
        If order_type is specified as OrderType.STOP, stop_price must be provided.
        If expiration is not provided, dte must be provided. If both expiration and dte are provided, expiration will be used.
        If strike is not provided, delta must be provided. If both strike and delta are provided, strike will be used.
        if width is provided, a spread order will be placed with the width as the number of strikes between the two legs. I.e. width=1 means next available strike etc.
        Parameters:
        option_type (OptionType): The type of the option (CALL or PUT).
        symbol (str): The symbol of the underlying asset.
        quantity (int): The number of contracts to trade. Negative for STO orders.
        strike (Optional[Decimal], optional): The strike price of the option. Defaults to None.
        delta (Optional[int], optional): The delta of the option. Defaults to None.
        expiration (Optional[date], optional): The expiration date of the option. Defaults to None.
        dte (Optional[int], optional): Days to expiration. Defaults to None.
        width (Optional[int], optional): The width of the spread. Defaults to None.
        order_type (OrderType, optional): The type of the order (MARKET, LIMIT, STOP). Defaults to OrderType.MARKET.
        stop_price (Optional[Decimal], optional): The stop price for stop orders. Defaults to None.
        gtc (bool, optional): Good till canceled flag. Defaults to False.
        weeklies (bool, optional): Weeklies flag. Defaults to False.
        Returns:
        None
        Raises:
        TastytradeError: If there is an error placing the order.
        Logs:
        Logs errors and warnings related to order placement.
        """

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
                if expiration is not None:
                    subchain = None
                    option_chain = chain.option_chains[0]
                    exps = [e for e in option_chain.expirations if e.expiration_date == expiration]
                    if len(exps) == 1:
                        subchain = exps[0]
                    else:
                        error_msg.append(f'Expiration not found.')
                else: 
                    # check at the beging of the func ensures either expiration or dte are present
                    # find the closest expiration to the DTE
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
                    subchain = min([expr for expr in chain.expirations 
                                    if weeklies and expr.expiration_type == ExpirationType.WEEKLY 
                                    or quarterlies and expr.expiration_type == ExpirationType.QUARTERLY
                                    or expr.expiration_type == ExpirationType.MONTHLY],
                                    key=lambda exp: abs((exp.expiration_date - datetime.now().date()).days - dte))
                    tick_size = chain.tick_sizes[0].value

        if len(error_msg) > 0:
            log_ntfy(LogType.ERROR, '\n'.join(error_msg), error_header, logger=logger)
            return

        # precision = tick_size.as_tuple().exponent
        # precision = abs(precision) if precision < 0 else ZERO
        # precision_str = f'.{precision}f'

        # find the closest strike to the delta
        if strike:
            option_at_strike = next(s for s in subchain.strikes if s.strike_price == strike)
        else:
            delta = Decimal(delta)/Decimal(100)
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
            option_at_strike = next(s for s in subchain.strikes if getattr(s, option_streamer_symbol) == greeks_at_strike.event_symbol)

        if width:
            if option_type == OptionType.CALL:
                spread_strikes = [s for s in subchain.strikes if s.strike_price > option_at_strike.strike_price]
            else:
                spread_strikes = [s for s in sorted(subchain.strikes, key=lambda x: x.strike_price, reverse=True) if s.strike_price < option_at_strike.strike_price]
            if len(spread_strikes) < width:
                log_ntfy(LogType.ERROR, f'No second leg strikes available for {option_type_str} spread with strike {option_at_strike.strike_price} and width {width}.', error_header, logger=logger)
                return
            spread_strike = spread_strikes[width - 1]

            if order_type == OrderType.LIMIT or order_type == OrderType.MARKET:
                quote_dict = await self._listen_events(Quote, [getattr(option_at_strike, option_streamer_symbol), getattr(spread_strike, option_streamer_symbol)])
                bid = quote_dict[getattr(option_at_strike, option_streamer_symbol)].bid_price - quote_dict[getattr(spread_strike, option_streamer_symbol)].ask_price
                ask = quote_dict[getattr(option_at_strike, option_streamer_symbol)].ask_price - quote_dict[getattr(spread_strike, option_streamer_symbol)].bid_price
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
                bid = quote.bid_price
                ask = quote.ask_price
                mid = (bid + ask) / Decimal(2)
                mid = TastytradeSession.round_to_width(mid, tick_size)
                mid = mid if quantity < 0 else -mid
            elif order_type == OrderType.STOP:
                mid = None
                # TODO: implement stop price for single options

        price = mid # mid price for limit orders, None for stop orders


        option_symbol = next(getattr(s, option_type_str) for s in subchain.strikes if s.strike_price == option_at_strike.strike_price)        
        subchain.strikes[0]
        if width:
            if is_future:  # futures options
                option_legs = FutureOption.get_future_options(tt_session, [option_symbol, getattr(spread_strike, option_type_str)])
            else:
                option_legs = Option.get_options(tt_session, [option_symbol, getattr(spread_strike, option_type_str)])
            option_legs.sort(key=lambda x: x.strike_price, reverse=option_type == OptionType.PUT)
            legs = [
                option_legs[0].build_leg(abs(quantity), OrderAction.SELL_TO_OPEN if quantity < 0 else OrderAction.BUY_TO_OPEN),
                option_legs[1].build_leg(abs(quantity), OrderAction.BUY_TO_OPEN if quantity < 0 else OrderAction.SELL_TO_OPEN)
            ]
        else:
            if is_future:
                option_leg = FutureOption.get_future_option(tt_session, option_symbol)
            else:
                option_leg = Option.get_option(tt_session, option_symbol)
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
            log_ntfy(LogType.ERROR, f'Invalid order type {order_type}. Accepted order types are {accepted_order_types}', error_header, logger=logger)
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
            log_ntfy(LogType.SUCCESS, 
                f'Buying power effect: {order_resp.buying_power_effect}, {order_resp.buying_power_effect / nl * Decimal(100):.2f}%', 
                f'DRY RUN order {OrderDirection.BTO if quantity > 0 else OrderDirection.STO} for {quantity} {symbol} placed successfully.', logger=logger)
            return
        except TastytradeError as e:
            err_msg = f'Options BP: ${acc_balances.derivative_buying_power}{NEWLINE}' + str(e)
            if price is not None:
                err_msg += f'\nPrice: {price}'
            log_ntfy(LogType.ERROR, err_msg, error_header, logger=logger)
            return
        
        order_resp:PlacedOrderResponse = acc.place_order(tt_session, order, dry_run=False)
        if order_resp.errors is None or len(order_resp.errors) == 0:
            if order_resp.warnings is not None and len(order_resp.warnings) > 0:
                log_ntfy(LogType.WARNING, f'Order placed with warnings:{NEWLINE_TAB}{NEWLINE_TAB.join([f"code: {o.code}{TAB}message: {o.message}" for o in order_resp.warnings])}', logger=logger)
            log_ntfy(LogType.SUCCESS, 
                f'Buying power effect: {order_resp.buying_power_effect}, {order_resp.buying_power_effect / nl * Decimal(100):.2f}%\n \
                Fees: {order_resp.fee_calculation}',
                f'Order {OrderDirection.BTO if quantity > 0 else OrderDirection.STO} for {quantity} "{option_symbol}" placed successfully.', logger=logger)
        else:
            log_ntfy(LogType.ERROR, f'Order placement failed. Errors:{NEWLINE_TAB}{NEWLINE_TAB.join([f"code: {o.code}{TAB}message: {o.message}" for o in order_resp.errors])}', error_header, logger=logger)

    
    async def send_closing_option_order(self, option_symbol:str, quantity:int, order_type:OrderType=OrderType.MARKET, price:Decimal=None, gtc:bool=False):
        """
        Closes an option position by sending BTC or STC an order to the Tastytrade platform.
        Parameters:
        symbol (str): The symbol of the option.
        quantity (int): The number of contracts to trade. Negative for STC orders.
        order_type (OrderType, optional): The type of the order (MARKET, LIMIT). Defaults to OrderType.MARKET.
        price (Decimal, optional): The price for limit orders. Defaults to None.
        gtc (bool, optional): Good till canceled flag. Defaults to False.
        Returns:
        None
        """

        option_type_str = 'call' if option_symbol[12] == OptionType.CALL else 'put' # 'SPY   250815C00590000'
        accepted_order_types = [OrderType.LIMIT, OrderType.MARKET]
        error_msg = []        
        error_header = f'ERROR in option order command: {option_type_str.upper()} symbol: "{option_symbol}", quantity: {quantity}, order_type: {order_type}, gtc: {gtc}'

        if order_type not in accepted_order_types:
            error_msg.append(f'Invalid order type. Accepted types: {accepted_order_types}')
        if order_type == OrderType.LIMIT and price is None:
            error_msg.append('Specify price for limit orders.')
        if quantity is None or quantity == 0:
            error_msg.append('Quantity cannot be zero or None.')

        tt_session:Session = TastytradeSession.get_session()
        if tt_session is None:
            error_msg.append('Session cannot be created.')

        if len(error_msg) > 0:
            log_ntfy(LogType.ERROR, '\n'.join(error_msg), error_header, logger=logger)
            return
        
        option_leg = await Option.a_get_option(tt_session, option_symbol)
        legs = [option_leg.build_leg(abs(quantity), OrderAction.SELL_TO_CLOSE if quantity < 0 else OrderAction.BUY_TO_CLOSE)]

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
                price=price
            )

        acc = TastytradeSession.get_account()
        acc_balances = await acc.a_get_balances(tt_session)
        nl = acc_balances.net_liquidating_value
        # bp = data.buying_power_effect.change_in_buying_power
        # percent = bp / nl * Decimal(100)
        # fees = data.fee_calculation.total_fees

        try:
            order_resp:PlacedOrderResponse = acc.place_order(tt_session, order, dry_run=True)
            return
        except TastytradeError as e:
            err_msg = str(e) + f'\nOptions BP: ${acc_balances.derivative_buying_power}'
            if price is not None:
                err_msg += f'\nPrice: {price}'
            log_ntfy(LogType.ERROR, err_msg, error_header, logger=logger)
            return
        
        order_resp:PlacedOrderResponse = acc.place_order(tt_session, order, dry_run=False)
        if order_resp.errors is None or len(order_resp.errors) == 0:
            if order_resp.warnings is not None and len(order_resp.warnings) > 0:
                log_ntfy(LogType.WARNING, f'{NEWLINE_TAB.join([f"code: {o.code}{TAB}message: {o.message}" for o in order_resp.warnings])}',
                         'Order placed with warnings', logger=logger)
            log_ntfy(LogType.SUCCESS, 
                f'Buying power effect: {order_resp.buying_power_effect}, {order_resp.buying_power_effect / nl * Decimal(100):.2f}%\n \
                Fees: {order_resp.fee_calculation}', 
                f'Order {OrderDirection.BTC if quantity > 0 else OrderDirection.STC} for {quantity} "{option_symbol}" placed successfully.', logger=logger)
        else:
            log_ntfy(LogType.ERROR, f'Order placement failed. Errors:{NEWLINE_TAB}{NEWLINE_TAB.join([f"code: {o.code}{TAB}message: {o.message}" for o in order_resp.errors])}', error_header, logger=logger)


    async def close_all_option_positions(self):
        """
        Closes all option positions by sending MARKET orders to the Tastytrade platform.
        Parameters:
        None
        Returns:
        None
        """

        acc = TastytradeSession.get_account()
        positions = await acc.a_get_positions(TastytradeSession.session)
        for pos in positions:
            if pos.instrument_type == InstrumentType.EQUITY_OPTION:
                await self.send_closing_option_order(pos.symbol, pos.quantity, OrderType.MARKET)

    
    async def delete_all_live_orders(self):
        """
        Delete all live orders by sending MARKET orders to the Tastytrade platform.
        Parameters:
        None
        Returns:
        None
        """

        acc = TastytradeSession.get_account()
        orders = await acc.a_get_live_orders(TastytradeSession.session)
        for order in orders:
            if order.status == OrderStatus.LIVE:
                try:
                    await acc.a_delete_order(TastytradeSession.session, order.order_id)
                except Exception as e:
                    err_msg = ''
                    for l in order.legs:
                        err_msg += f'{l.instrument_type} "{l.symbol}" Qty: {l.quantity} Action: {l.action}{NEWLINE}'
                    err_msg += f'ERROR:{NEWLINE}{str(e)}'
                    log_ntfy(LogType.ERROR, str(e), f'Error closing order {order.order_id}', logger=logger)


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
                ps.close_price_prev = summary_dict[o.streamer_symbol].prev_day_close_price
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
                ps.close_price_prev = summary_dict[f.streamer_symbol].prev_day_close_price
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
                ps.close_price_prev = summary_dict[pos.symbol].prev_day_close_price
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
                ps.close_price_prev = summary_dict[f.streamer_symbol].prev_day_close_price
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
                ps.close_price_prev = summary_dict[c.streamer_symbol].prev_day_close_price
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
                log_ntfy(LogType.ERROR, f'Skipping {pos.symbol}, unknown instrument type {pos.instrument_type}!', 'Unknown instrument type', logger=logger)
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
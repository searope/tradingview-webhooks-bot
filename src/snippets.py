from collections import defaultdict
from decimal import Decimal
from typing import cast, List

from tastytrade import Account
from tastytrade.account import CurrentPosition
from tastytrade.metrics import MarketMetricInfo, a_get_market_metrics
from tastytrade.instruments import (get_option_chain, 
                                    InstrumentType,
                                    Cryptocurrency, Equity,
                                    Future, FutureOption,
                                    Option, OptionType,
                                    NestedFutureOptionChain,
                                    NestedFutureOptionChainExpiration,
                                    NestedOptionChain,
                                    NestedOptionChainExpiration)
from tastytrade.utils import today_in_new_york, now_in_new_york, TastytradeError

from components.utils.tastytrade import TastytradeSession


async def get_positions(self, account:Account = None) -> List[CurrentPosition]:
    if TastytradeSession.session is None or not TastytradeSession.session.validate():
        raise Exception('Session is not established')
    today = today_in_new_york()
    if account is None:
        account = TastytradeSession.get_account()
    positions = account.get_positions(TastytradeSession.session, include_marks=True)
    positions.sort(key=lambda pos: pos.symbol)
    # pos_dict = {pos.symbol: pos for pos in positions}
    # options_symbols = [
    #     p.symbol
    #     for p in positions
    #     if p.instrument_type == InstrumentType.EQUITY_OPTION
    # ]
    # options = (Option.get_options(TastytradeSession.session, options_symbols)
    #         if options_symbols else [])
    # options_dict = {o.symbol: o for o in options}
    # future_options_symbols = [
    #     p.symbol
    #     for p in positions
    #     if p.instrument_type == InstrumentType.FUTURE_OPTION
    # ]
    # future_options = (
    #     FutureOption.get_future_options(TastytradeSession.session, future_options_symbols)
    #     if future_options_symbols else []
    # )
    # future_options_dict = {fo.symbol: fo for fo in future_options}
    # futures_symbols = [
    #     p.symbol
    #     for p in positions
    #     if p.instrument_type == InstrumentType.FUTURE
    # ] + [fo.underlying_symbol for fo in future_options]
    # futures = (Future.get_futures(TastytradeSession.session, futures_symbols)
    #         if futures_symbols else [])
    # futures_dict = {f.symbol: f for f in futures}
    # crypto_symbols = [
    #     p.symbol
    #     for p in positions
    #     if p.instrument_type == InstrumentType.CRYPTOCURRENCY
    # ]
    # cryptos = (Cryptocurrency.get_cryptocurrencies(TastytradeSession.session, crypto_symbols)
    #         if crypto_symbols else [])
    # crypto_dict = {c.symbol: c for c in cryptos}
    # greeks_symbols = ([o.streamer_symbol for o in options] +
    #                 [fo.streamer_symbol for fo in future_options])
    # equity_symbols = [p.symbol for p in positions
    #                 if p.instrument_type == InstrumentType.EQUITY]
    # equities = Equity.get_equities(TastytradeSession.session, equity_symbols)
    # equity_dict = {e.symbol: e for e in equities}
    # all_symbols = list(set(
    #     [o.underlying_symbol for o in options] +
    #     [c.streamer_symbol for c in cryptos] +
    #     equity_symbols +
    #     [f.streamer_symbol for f in futures]
    # )) + greeks_symbols

    # # get greeks for options
    # greeks_dict: dict[str, Greeks] = await self._listen_events(Greeks, greeks_symbols)
    # summary_dict: dict[str, Summary] = await self._listen_events(Summary, all_symbols)        
    # spy = (await self._listen_events(Trade, ['SPY']))['SPY']

    # spy_price = spy.price or 0
    # tt_symbols = set(pos.symbol for pos in positions)
    # tt_symbols.update(set(o.underlying_symbol for o in options))
    # tt_symbols.update(set(o.underlying_symbol for o in future_options))
    # metrics_list = await a_get_market_metrics(TastytradeSession.session, list(tt_symbols))
    # metrics_dict = {metric.symbol: metric for metric in metrics_list}

    # sums = defaultdict(lambda: ZERO)
    # closing: dict[int, TradeableTastytradeJsonDataclass] = {}
    for i, pos in enumerate(positions):
        ps = PositionSummary(pos)
        row = [f'{i+1}']
        mark = pos.mark or 0
        mark_price = pos.mark_price or 0
        direction = (1 if pos.quantity_direction == 'Long' else -1)
        #mark_price = mark / pos.quantity
        net_liq = Decimal(mark * direction)
        pnl_day = 0
        # instrument-specific calculations
        if pos.instrument_type == InstrumentType.EQUITY_OPTION:
            metrics = metrics_dict[o.underlying_symbol]
            o = options_dict[pos.symbol]
            closing[i + 1] = o
            ps.day_change = mark_price - (summary_dict[o.streamer_symbol].prev_day_close_price or ZERO)  # type: ignore
            ps.pnl_day = ps.day_change * pos.quantity * pos.multiplier
            ps.pnl_total = direction * (mark_price - pos.average_open_price * pos.multiplier)
            ps.trade_price = pos.average_open_price * pos.multiplier
            ps.iv_rank = (metrics.tos_implied_volatility_index_rank or 0) * 100
            ps.delta = greeks_dict[o.streamer_symbol].delta * 100 * direction  # type: ignore
            ps.theta = greeks_dict[o.streamer_symbol].theta * 100 * direction  # type: ignore
            ps.gamma = greeks_dict[o.streamer_symbol].gamma * 100 * direction  # type: ignore
            beta = metrics.beta or 0
            ps.beta_delta = beta *  mark * delta / spy_price
            ps.net_liquidity = mark_price * pos.quantity * pos.multiplier
            ps.dividend_next_date = metrics.dividend_next_date
            if metrics.earnings:
                ps.earnings_next_date = metrics.earnings.expected_report_date

            # DividendNextDate:date
            # EarningsNextDate:date

            # # BWD = beta * stock price * delta / index price
            # delta = greeks_dict[o.streamer_symbol].delta * 100 * direction  # type: ignore
            # theta = greeks_dict[o.streamer_symbol].theta * 100 * direction  # type: ignore
            # gamma = greeks_dict[o.streamer_symbol].gamma * 100 * direction  # type: ignore
            # metrics = metrics_dict[o.underlying_symbol]
            # beta = metrics.beta or 0
            # bwd = beta *  mark * delta / spy_price
            # ivr = (metrics.tos_implied_volatility_index_rank or 0) * 100
            # indicators = TastytradeSession.get_indicators(today, metrics)
            # pnl = direction * (mark_price - pos.average_open_price * pos.multiplier)
            # trade_price = pos.average_open_price * pos.multiplier
            # day_change = mark_price - (summary_dict[o.streamer_symbol].prev_day_close_price or ZERO)  # type: ignore
            # pnl_day = day_change * pos.quantity * pos.multiplier
        elif pos.instrument_type == InstrumentType.FUTURE_OPTION:
            o = future_options_dict[pos.symbol]
            closing[i + 1] = o
            delta = greeks_dict[o.streamer_symbol].delta * 100 * direction
            theta = greeks_dict[o.streamer_symbol].theta * 100 * direction
            gamma = greeks_dict[o.streamer_symbol].gamma * 100 * direction
            # BWD = beta * stock price * delta / index price
            f = futures_dict[o.underlying_symbol]
            metrics = metrics_dict[o.root_symbol]
            indicators = TastytradeSession.get_indicators(today, metrics)
            bwd = ((summary_dict[f.streamer_symbol].prev_day_close_price or ZERO) *  # type: ignore
                metrics.beta * delta / spy_price) if metrics.beta else 0
            ivr = (metrics.tos_implied_volatility_index_rank or 0) * 100
            trade_price = pos.average_open_price / f.display_factor
            pnl = (mark_price - trade_price) * direction
            day_change = mark_price - (summary_dict[o.streamer_symbol].prev_day_close_price or ZERO)  # type: ignore
            pnl_day = day_change * pos.quantity * pos.multiplier
        elif pos.instrument_type == InstrumentType.EQUITY:
            theta = 0
            gamma = 0
            delta = pos.quantity * direction
            # BWD = beta * stock price * delta / index price
            metrics = metrics_dict[pos.symbol]
            e = equity_dict[pos.symbol]
            closing[i + 1] = e
            beta = metrics.beta or 0
            indicators = TastytradeSession.get_indicators(today, metrics)
            bwd = beta * mark_price * delta / spy_price
            ivr = (metrics.tos_implied_volatility_index_rank or 0) * 100
            pnl = mark - pos.average_open_price * pos.quantity * direction
            trade_price = pos.average_open_price
            day_change = mark_price - (summary_dict[pos.symbol].prev_day_close_price or ZERO)  # type: ignore
            pnl_day = day_change * pos.quantity
        elif pos.instrument_type == InstrumentType.FUTURE:
            theta = 0
            gamma = 0
            delta = pos.quantity * direction * 100
            f = futures_dict[pos.symbol]
            closing[i + 1] = f
            # BWD = beta * stock price * delta / index price
            metrics = metrics_dict[f.future_product.root_symbol]  # type: ignore
            indicators = TastytradeSession.get_indicators(today, metrics)
            bwd = (metrics.beta * mark_price * delta / spy_price) if metrics.beta else 0
            ivr = (metrics.tw_implied_volatility_index_rank or 0) * 100
            trade_price = pos.average_open_price * f.notional_multiplier
            pnl = (mark_price - trade_price) * pos.quantity * direction
            day_change = mark_price - (summary_dict[f.streamer_symbol].prev_day_close_price or ZERO)  # type: ignore
            pnl_day = day_change * pos.quantity * pos.multiplier
            net_liq = pnl_day
        elif pos.instrument_type == InstrumentType.CRYPTOCURRENCY:
            theta = 0
            gamma = 0
            delta = 0
            bwd = 0
            ivr = None
            pnl = mark - pos.average_open_price * pos.quantity * direction
            trade_price = pos.average_open_price
            indicators = ''
            pos.quantity = round(pos.quantity, 2)
            c = crypto_dict[pos.symbol]
            closing[i + 1] = c
            day_change = mark_price - (summary_dict[c.streamer_symbol].prev_day_close_price or ZERO)  # type: ignore
            pnl_day = day_change * pos.quantity * pos.multiplier
        else:
            print(f'Skipping {pos.symbol}, unknown instrument type '
                f'{pos.instrument_type}!')
            continue
        if pos.created_at.date() == today:
            pnl_day = pnl
        sums['pnl'] += pnl
        sums['pnl_day'] += pnl_day
        sums['bwd'] += bwd
        sums['net_liq'] += net_liq
        pass
"""             
        row.extend([
            pos.symbol,
            f'{pos.quantity * direction:g}',
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
class PositionSummary(CurrentPosition):
    day_change:Decimal
    pnl_day:Decimal
    pnl_total:Decimal
    mark_price:Decimal
    trade_price:Decimal
    iv_rank:float
    delta:float
    theta:float
    gamma:float
    beta_delta:float
    net_liquidity:Decimal
    dividend_next_date:date
    earnings_next_date:date

    def __init__(self, curPos: CurrentPosition):
        super().__init__(**vars(curPos))
        # for key, value in vars(curPos).items():
        #     setattr(self, key, value)


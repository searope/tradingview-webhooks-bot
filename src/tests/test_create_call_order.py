from tastytrade.instruments import OptionType
from tastytrade.order import OrderType
from components.utils.tastytrade import TastytradeSession


async def test_SPY_not_enough_money():
    tts = TastytradeSession()
    await tts.send_openinng_option_order(OptionType.CALL, 'SPY', 1, strike=600, dte=365)


async def test_SPY_delta():
    tts = TastytradeSession()
    await tts.send_openinng_option_order(OptionType.CALL, 'SPY', 1, delta=80, dte=365)


async def test_ES_not_enough_money():
    tts = TastytradeSession()
    await tts.send_openinng_option_order(OptionType.CALL, '/ES', 1, strike=6000, dte=365)


async def test_SPY_call_spread():
    tts = TastytradeSession()
    await tts.send_openinng_option_order(OptionType.CALL, 'SPY', 1, strike=600, dte=365, width=2, order_type=OrderType.LIMIT)


async def test_SPY_put_spread():
    tts = TastytradeSession()
    await tts.send_openinng_option_order(OptionType.PUT, 'SPY', 1, strike=600, dte=365, width=2, order_type=OrderType.LIMIT)


async def test_SPY_call_delta():
    tts = TastytradeSession()
    await tts.send_openinng_option_order(OptionType.CALL, 'SPY', 1, delta=.7, dte=365, width=2, order_type=OrderType.LIMIT)


async def test_get_positions():
    tts = TastytradeSession()
    result = await tts.get_positions()
    pass

async def close_option_position():
    tts = TastytradeSession()
    await tts.send_closing_option_order('SPY   250815C00590000', -1, OrderType.MARKET)
    pass

async def test_get_account():
    tts = TastytradeSession()
    account = tts.get_account()
    account.get_positions(tts.session)
    pass

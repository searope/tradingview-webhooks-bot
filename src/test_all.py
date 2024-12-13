import asyncio
import tests.test_create_call_order as test
from dataclasses import dataclass
from tastytrade.account import CurrentPosition
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,
    Generator,
    Literal,
    Mapping,
    Set,
    Tuple,
    TypeVar,
    Union,
    cast,
    overload,
)

#asyncio.run(test_SPY_not_enough_money())
#asyncio.run(test_ES_not_enough_money())

#asyncio.run(test.test_SPY_call_spread())
#asyncio.run(test.test_SPY_put_spread())

#asyncio.run(test.test_SPY_call_delta())
asyncio.run(test.test_get_positions())
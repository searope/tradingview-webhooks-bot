import asyncio
import utils.log as log
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


# log.log_ntfy(log.LogType.CRITICAL, 'Running tests...', 'Test Runner')
# log.log_ntfy(log.LogType.ERROR, 'Running tests...', 'Test Runner')
# log.log_ntfy(log.LogType.WARNING, 'Running tests...', 'Test Runner')
# log.log_ntfy(log.LogType.INFO, 'Running tests...', 'Test Runner')
# log.log_ntfy(log.LogType.DEBUG, 'Running tests...', 'Test Runner')
# log.log_ntfy(log.LogType.SUCCESS, 'Running tests...')

#asyncio.run(test.test_SPY_not_enough_money())
asyncio.run(test.test_ES_not_enough_money())

#asyncio.run(test.test_SPY_call_spread())
#asyncio.run(test.test_SPY_put_spread())

#asyncio.run(test.test_SPY_call_delta())
#asyncio.run(test.test_get_positions())
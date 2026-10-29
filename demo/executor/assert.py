
from pydantic import BaseModel
from typing import Any
from models import Assertion

class AssertionResult():
    assertion: Assertion
    passed: bool
    actual: Any  # 字段不存在时为 None，配合 actual_missing 区分
    actual_missing: bool = False
    def __str__(self):
        return f"AssertionResult(passed={self.passed}, actual={self.actual}, actual_missing={self.actual_missing})"


def _eq(a, b) -> bool:
    # Python 里 True == 1，这里单独排除
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    return a == b


def _contains(actual, expected) -> bool:
    if isinstance(actual, str):
        return isinstance(expected, str) and expected in actual
    if isinstance(actual, list):
        return any(_eq(item, expected) for item in actual)
    if isinstance(actual, dict):
        return expected in actual  # 判断是否包含某个 key
    return False


def _number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


OPS = {
    "eq": _eq,
    "ne": lambda a, e: not _eq(a, e),
    "in": lambda a, e: any(_eq(a, item) for item in e),
    "contains": _contains,
    "gt": lambda a, e: _number(a) and _number(e) and a > e,
    "lt": lambda a, e: _number(a) and _number(e) and a < e,
}

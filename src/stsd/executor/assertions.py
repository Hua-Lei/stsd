"""确定性断言：取值（locate）× 比较（compare）。

字段不存在用 ``MISSING`` 表示，和 JSON 的 null 区分；严格比较，不做类型转换。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from stsd.shared.execution_contract import AssertionRecord, ResponseRecord

from .case import Assertion
from .jsonpath import MISSING, get as jsonpath_get


def judge(assertions: tuple[Assertion, ...] | list[Assertion],
          response: ResponseRecord) -> tuple[AssertionRecord, ...]:
    """对一条响应的全部断言求值；每条断言都保留预期、实际和结论。"""

    return tuple(check(assertion, response) for assertion in assertions)


def check(assertion: Assertion, response: ResponseRecord) -> AssertionRecord:
    """单条断言：先定位实际值，再按 op 比较，最后生成可读 message。"""

    actual = locate(assertion, response)
    missing = actual is MISSING
    passed = COMPARE[assertion.op](actual, assertion.expected)
    record = AssertionRecord(
        source=assertion.source,
        op=assertion.op,
        path=assertion.path,
        expected=assertion.expected,
        actual=None if missing else actual,
        actual_missing=missing,
        passed=passed,
        message="",
    )
    
    # message 占位 record，在 describe() 里生成最终 message 再回填
    return replace(record, message=describe(record))


def locate(assertion: Assertion, response: ResponseRecord) -> Any:
    """按 source 取值：状态码 / 响应头 / JSONPath；取不到返回 MISSING。"""

    if assertion.source == "status":
        return response.status
    if assertion.source == "header":
        return response.headers.get(assertion.path.lower(), MISSING)
    return jsonpath_get(response.body, assertion.path)


def describe(record: AssertionRecord) -> str:
    """生成“期望什么、实际什么”的一行说明，直接进入结果证据。"""

    target = record.source if record.path is None else f"{record.source} {record.path}"
    want = record.op if record.op in ("exists", "not_exists") else f"{record.op} {record.expected!r}"
    got = "<字段不存在>" if record.actual_missing else repr(record.actual)
    return f"{target}: want {want}, result {got}"


def _eq(a: Any, b: Any) -> bool:
    # bool 是 int 的子类；这里避免 True == 1 被当成相等。
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    return a == b


def _contains(actual: Any, expected: Any) -> bool:
    """字符串子串、列表元素、字典 key 三种 contains 语义。"""

    if isinstance(actual, str):
        return isinstance(expected, str) and expected in actual
    if isinstance(actual, list):
        return any(_eq(item, expected) for item in actual)
    if isinstance(actual, dict):
        return expected in actual
    return False


def _number(value: Any) -> bool:
    # bool 也满足 isinstance(int)，比较大小前显式排除。
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _present(fn: Callable[[Any, Any], bool]) -> Callable[[Any, Any], bool]:
    """除了 exists/not_exists，MISSING 一律判为不通过。"""

    return lambda actual, expected: actual is not MISSING and fn(actual, expected)


COMPARE: dict[str, Callable[[Any, Any], bool]] = {
    "exists": lambda actual, _: actual is not MISSING,
    "not_exists": lambda actual, _: actual is MISSING,
    "eq": _present(_eq),
    "ne": _present(lambda actual, expected: not _eq(actual, expected)),
    "in": _present(lambda actual, expected: any(_eq(actual, item) for item in expected)),
    "contains": _present(_contains),
    "gt": _present(lambda actual, expected: _number(actual) and _number(expected) and actual > expected),
    "lt": _present(lambda actual, expected: _number(actual) and _number(expected) and actual < expected),
}

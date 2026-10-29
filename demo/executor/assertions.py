"""断言判定：取值（locate）× 比较（compare），两个维度互相独立。

字段不存在时 locate 返回 MISSING，交给 compare 当普通值处理：
exists / not_exists 只看是否为 MISSING，其余比较遇到 MISSING 一律不通过。
比较是严格的：不做类型转换，"201" 不等于 201，True 不等于 1。
"""
from typing import Any, Callable

from demo.models import Assertion, AssertionResult, ResponseRecord
from demo.utils import jsonpath
from demo.utils.jsonpath import MISSING


def judge(assertions: list[Assertion], response: ResponseRecord) -> list[AssertionResult]:
    return [check(a, response) for a in assertions]


def check(a: Assertion, response: ResponseRecord) -> AssertionResult:
    actual = locate(a, response)
    missing = actual is MISSING
    return AssertionResult(
        assertion=a,
        passed=COMPARE[a.op](actual, a.expected),
        actual=None if missing else actual,
        actual_missing=missing,
    )


def locate(a: Assertion, response: ResponseRecord) -> Any:
    if a.source == "status":
        return response.status
    if a.source == "header":
        return response.headers.get(a.path.lower(), MISSING)
    return jsonpath.get(response.body, a.path)


def describe(r: AssertionResult) -> str:
    a = r.assertion
    target = a.source if a.path is None else f"{a.source} {a.path}"
    want = a.op if a.op in ("exists", "not_exists") else f"{a.op} {a.expected!r}"
    got = "<字段不存在>" if r.actual_missing else repr(r.actual)
    return f"{target}: want {want}, result {got}"


# ---------- 比较 ----------

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


def _present(fn: Callable[[Any, Any], bool]) -> Callable[[Any, Any], bool]:
    """actual 为 MISSING 时直接不通过，否则交给 fn 比较。"""
    return lambda actual, expected: actual is not MISSING and fn(actual, expected)


COMPARE: dict[str, Callable[[Any, Any], bool]] = {
    "exists": lambda actual, _: actual is not MISSING,
    "not_exists": lambda actual, _: actual is MISSING,
    "eq": _present(_eq),
    "ne": _present(lambda a, e: not _eq(a, e)),
    "in": _present(lambda a, e: any(_eq(a, item) for item in e)),
    "contains": _present(_contains),
    "gt": _present(lambda a, e: _number(a) and _number(e) and a > e),
    "lt": _present(lambda a, e: _number(a) and _number(e) and a < e),
}

"""变量绑定：把 ``{{name}}`` 替换为变量快照中的值。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .case import Assertion, Step
from .errors import RenderError

_WHOLE = re.compile(r"^\{\{\s*(\w+)\s*\}\}$")
_EMBEDDED = re.compile(r"\{\{\s*(\w+)\s*\}\}")


@dataclass(frozen=True)
class BoundStep:
    """变量绑定后的步骤快照；请求和断言使用同一份变量。"""

    method: str
    path: str
    headers: dict[str, str]
    query: dict[str, Any]
    body: Any
    assertions: tuple[Assertion, ...]


def bind(step: Step, variables: dict[str, Any]) -> BoundStep:
    """一次性绑定 request 与断言 expected，避免中途变量变化造成错位。"""

    request = step.request
    return BoundStep(
        method=request.method,
        path=render(request.path, variables),
        headers={key: str(render(value, variables)) for key, value in request.headers.items()},
        query=render(request.query, variables),
        body=render(request.body, variables),
        assertions=tuple(
            assertion.model_copy(update={"expected": render(assertion.expected, variables)})
            for assertion in step.assertions
        ),
    )


def render(value: Any, variables: dict[str, Any]) -> Any:
    """递归替换模板。

    整个字符串恰好是占位符时保留变量原类型（例如数字 id），
    嵌在文本中的占位符则转成字符串拼接。
    """

    if isinstance(value, str):
        whole = _WHOLE.match(value)
        if whole:
            return _lookup(whole.group(1), variables)
        return _EMBEDDED.sub(lambda match: str(_lookup(match.group(1), variables)), value)
    if isinstance(value, dict):
        return {key: render(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [render(item, variables) for item in value]
    return value


def _lookup(name: str, variables: dict[str, Any]) -> Any:
    """变量缺失是执行错误，不静默替换成空串。"""

    if name not in variables:
        raise RenderError(
            f"变量 {{{{{name}}}}} 不存在（已有: {sorted(variables) or '无'}）"
        )
    return variables[name]

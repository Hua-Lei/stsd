"""变量绑定：在变量环境里对模板求值，得到不含占位符的具体步骤。

字符串节点有两种情况：
  整个字符串恰好是一个占位符   "{{id}}"            → 变量本身，保留原类型
  占位符嵌在其他文本里         "/learners/{{id}}"  → 字符串插值
"""
import re
from dataclasses import dataclass
from typing import Any

from demo.executor.errors import RenderError
from demo.models import Assertion, RenderedRequest, Step

_WHOLE = re.compile(r"^\{\{\s*(\w+)\s*\}\}$")
_EMBEDDED = re.compile(r"\{\{\s*(\w+)\s*\}\}")


@dataclass(frozen=True)
class BoundStep:
    request: RenderedRequest
    assertions: list[Assertion]


def bind(step: Step, variables: dict[str, Any]) -> BoundStep:
    """一次性绑定 request 和断言的 expected。两者用同一份变量快照：extract 要等这一步结束才更新变量。"""
    req = step.request
    return BoundStep(
        request=RenderedRequest(
            method=req.method,
            path=render(req.path, variables),
            headers={k: str(render(v, variables)) for k, v in req.headers.items()},
            query=render(req.query, variables),
            body=render(req.body, variables),
        ),
        assertions=[a.model_copy(update={"expected": render(a.expected, variables)})
                    for a in step.assertions],
    )


def render(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        if m := _WHOLE.match(value):
            return _lookup(m.group(1), variables)
        return _EMBEDDED.sub(lambda m: str(_lookup(m.group(1), variables)), value)
    if isinstance(value, dict):
        return {k: render(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, variables) for v in value]
    return value


def _lookup(name: str, variables: dict[str, Any]) -> Any:
    if name not in variables:
        raise RenderError(f"want 变量 {{{{{name}}}}}, result 不存在（已有: {sorted(variables) or '无'}）")
    return variables[name]

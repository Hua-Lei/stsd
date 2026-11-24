"""用例格式（TestCase）。

这是执行器的输入契约：任务清单导出的 payload 必须能通过这些模型校验。
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from .jsonpath import parse as parse_jsonpath

VAR_NAME = re.compile(r"^[A-Za-z_]\w*$")


class Strict(BaseModel):
    """默认禁止未声明字段，避免用例 JSON 里的拼写错误被静默忽略。"""

    model_config = ConfigDict(extra="forbid")


class Request(Strict):
    """一步 HTTP 请求；path、headers、query、body 都可以包含 ``{{变量}}``。"""

    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    headers: dict[str, str] = {}
    query: dict[str, Any] = {}
    body: Any = None


class Assertion(Strict):
    """一条确定性断言。

    ``source`` 决定从哪里取值：状态码、响应头或 JSON body（JSONPath）。
    """

    source: Literal["status", "body", "header"]
    op: Literal["eq", "ne", "in", "exists", "not_exists", "contains", "gt", "lt"]
    path: str | None = None
    expected: Any = None

    @model_validator(mode="after")
    def check_shape(self):
        """在用例入库/执行前尽早暴露断言语义错误。"""

        if self.source == "status" and self.path is not None:
            raise ValueError("status 断言不能有 path")
        if self.source in ("body", "header") and not self.path:
            raise ValueError(f"{self.source} 断言必须有 path")
        if self.path and self.source == "body":
            parse_jsonpath(self.path)
        needs_expected = self.op not in ("exists", "not_exists")
        if needs_expected and "expected" not in self.model_fields_set:
            raise ValueError(f"op={self.op} 必须提供 expected")
        if self.op == "in" and not isinstance(self.expected, list):
            raise ValueError("op=in 的 expected 必须是列表")
        return self


class Step(Strict):
    """用例中的一个步骤：绑定变量 → 请求 → 断言 → 提取变量。"""

    name: str
    request: Request
    extract: dict[str, str] = {}
    assertions: list[Assertion] = []

    @model_validator(mode="after")
    def check_extract(self):
        """变量名必须合法，提取路径必须是可解析的 JSONPath。"""

        for name, path in self.extract.items():
            if not VAR_NAME.match(name):
                raise ValueError(f"非法变量名 {name!r}")
            parse_jsonpath(path)
        return self


class TestCase(Strict):
    """执行器接受的完整用例；必须至少有一个步骤。"""

    id: str
    title: str
    category: str = "happy_path"
    steps: list[Step]

    @model_validator(mode="after")
    def check_steps(self):
        if not self.steps:
            raise ValueError("用例至少需要一个步骤")
        return self

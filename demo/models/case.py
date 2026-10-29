"""
数据模型
"""
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from demo.utils import jsonpath

VAR_NAME = re.compile(r"^[A-Za-z_]\w*$")

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Request(Strict):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str  # 可包含 {{var}} 引用
    headers: dict[str, str] = {}
    query: dict[str, Any] = {}
    body: Any = None  # 任意 JSON；None 表示不发送 body


class Assertion(Strict):
    source: Literal["status", "body", "header"]
    op: Literal["eq", "ne", "in", "exists", "not_exists", "contains", "gt", "lt"]
    path: str | None = None  # body 用 JSONPath，header 用头名称
    expected: Any = None

    @model_validator(mode="after")
    def check_shape(self):
        if self.source == "status" and self.path is not None:
            raise ValueError("status 断言不能有 path")
        if self.source in ("body", "header") and not self.path:
            raise ValueError(f"{self.source} 断言必须有 path")
        if self.path and self.source == "body":
            jsonpath.parse(self.path)
        # exists / not_exists 不需要 expected，其余 op 必须显式给出
        # 用 model_fields_set 区分“没写”和“写了 null”
        needs_expected = self.op not in ("exists", "not_exists")
        if needs_expected and "expected" not in self.model_fields_set:
            raise ValueError(f"op={self.op} 必须提供 expected")
        if self.op == "in" and not isinstance(self.expected, list):
            raise ValueError("op=in 的 expected 必须是列表")
        return self


class Step(Strict):
    name: str
    request: Request
    extract: dict[str, str] = {}  # 变量名 -> JSONPath
    assertions: list[Assertion] = []

    @model_validator(mode="after")
    def check_extract(self):
        for name, path in self.extract.items():
            if not VAR_NAME.match(name):
                raise ValueError(f"非法变量名 {name!r}，只能包含字母、数字、下划线")
            jsonpath.parse(path)
        return self


class TestCase(Strict):
    id: str
    title: str
    requirement_ids: list[str] = []
    category: Literal["happy_path", "boundary", "invalid_input", "auth", "state"]
    steps: list[Step]

    @model_validator(mode="after")
    def check_steps(self):
        if not self.steps:
            raise ValueError("用例至少需要一个步骤")
        return self

"""执行结果模型：执行器产出，分析器和持久化读取。

放在 models 而不是 executor 里，是因为它是执行器和下游之间的契约，
下游（分析器、报告）不应该为了读结果而依赖执行器。
"""
from typing import Any, Literal

from pydantic import BaseModel

from demo.models.case import Assertion

ErrorType = Literal["render_error", "transport_error", "assertion_failed", "extract_error"]


class RenderedRequest(BaseModel):
    method: str
    path: str
    headers: dict[str, str]
    query: dict[str, Any]
    body: Any


class ResponseRecord(BaseModel):
    status: int
    headers: dict[str, str]
    body: Any  # 能解析成 JSON 就是 JSON，否则是原始文本
    elapsed_ms: float


class AssertionResult(BaseModel):
    assertion: Assertion  # 已绑定变量后的断言
    passed: bool
    actual: Any  # 字段不存在时为 None，配合 actual_missing 区分
    actual_missing: bool = False


class StepResult(BaseModel):
    index: int
    name: str
    status: Literal["passed", "failed", "error", "skipped"]
    error_type: ErrorType | None = None
    message: str | None = None  # want / result 形式的可读说明
    request: RenderedRequest | None = None
    response: ResponseRecord | None = None
    assertions: list[AssertionResult] = []
    extracted: dict[str, Any] = {}


class CaseResult(BaseModel):
    case_id: str
    title: str
    status: Literal["passed", "failed", "error"]
    steps: list[StepResult]
    variables: dict[str, Any]

"""测试结果模块的错误码与异常。"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """结果模块对外错误码；入口层按 code 做统一错误响应。"""

    RUN_NOT_FOUND = "RUN_NOT_FOUND"
    SNAPSHOT_MISMATCH = "SNAPSHOT_MISMATCH"
    INVALID_EXECUTION = "INVALID_EXECUTION"
    PROJECT_SCOPE = "PROJECT_SCOPE"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"


class ResultError(Exception):
    """结果模块异常基类，携带 code/message，便于 JSON 化。"""

    def __init__(self, code: ErrorCode | str, message: str = "") -> None:
        self.code = str(code)
        self.message = message or self.code
        super().__init__(f"{self.code}: {self.message}")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class RunNotFound(ResultError):
    def __init__(self, run_id: str) -> None:
        super().__init__(ErrorCode.RUN_NOT_FOUND, f"执行记录不存在: {run_id}")


class InvalidArgument(ResultError):
    """参数形状或枚举值不合法。"""

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.INVALID_ARGUMENT, message)


class SnapshotMismatch(ResultError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.SNAPSHOT_MISMATCH, message)


class InvalidExecution(ResultError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.INVALID_EXECUTION, message)

"""任务清单模块的错误码与异常。

（``CASE_CONTENT_CHANGED``、``EXPORT_UNSUPPORTED``）在 README 中说明。

约定：
- 清单级失败（清单不存在、已锁定、空清单、参数非法）抛 ``TaskListError``；
- 条目级失败（某条用例加不进去）不抛异常，放进返回值的 ``rejected`` 里。
  这样 LLM 与人工看到的是同一份结构化反馈。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    TARGET_MISSING = "TARGET_MISSING"          # 创建清单时未指定目标版本
    LIST_NOT_FOUND = "LIST_NOT_FOUND"          # 清单不存在
    LIST_LOCKED = "LIST_LOCKED"                # 对已锁定清单做编辑操作
    EMPTY_LIST = "EMPTY_LIST"                  # 空清单不允许锁定
    DUPLICATE = "DUPLICATE"                    # 用例已在清单中
    CASE_NOT_FOUND = "CASE_NOT_FOUND"          # 用例库中无此用例
    NO_APPLICABLE_VERSION = "NO_APPLICABLE_VERSION"  # 目标版本下用例无适用版本
    VERSION_NOT_FOUND = "VERSION_NOT_FOUND"    # pin 指定 / 引用的版本不存在
    DEPRECATED_REF = "DEPRECATED_REF"          # 引用了已废弃版本（警告）
    SUPERSEDED = "SUPERSEDED"                  # 存在更新的适用版本（警告）
    REV_CONFLICT = "REV_CONFLICT"              # 预留，原型未启用

    INVALID_ARGUMENT = "INVALID_ARGUMENT"      # 参数形状不合法（非业务错误）
    CASE_CONTENT_CHANGED = "CASE_CONTENT_CHANGED"  # 同版本内容指纹变化，违反只读前提
    LIST_NOT_LOCKED = "LIST_NOT_LOCKED"        # 导出执行用例要求清单已锁定
    EXPORT_UNSUPPORTED = "EXPORT_UNSUPPORTED"  # 用例库适配器不提供用例正文


class TaskListError(Exception):
    """清单级失败。``details`` 用于携带逐条明细（例如锁定校验失败的所有条目）。"""

    def __init__(
        self,
        code: ErrorCode | str,
        message: str = "",
        *,
        tasklist_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = str(code)
        self.message = message or self.code
        self.tasklist_id = tasklist_id
        self.details = details or {}
        super().__init__(f"{self.code}: {self.message}")

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.tasklist_id is not None:
            out["tasklist_id"] = self.tasklist_id
        if self.details:
            out["details"] = self.details
        return out

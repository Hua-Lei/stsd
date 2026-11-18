"""错误码与异常：领域层与服务层共享的唯一错误词汇表。

设计要点（对应 Architecture Patterns with Python 的“异常是领域语言的一部分”）：

- 领域对象在破坏不变量时抛 ``TaskListError`` 的子类，每个子类自带错误码；
- 服务层只补充“需要查仓储/端口才能判断”的规则，抛同一族异常；
- 入口层只捕获 ``TaskListError``，因此新增规则不会改变 CLI / HTTP 契约；
- 条目级失败（某条用例加不进去）不抛异常，而是放进返回值的 ``rejected``，
  让 LLM 与人工看到同一份结构化反馈。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    TARGET_MISSING = "TARGET_MISSING"                # 创建清单时未指定目标版本
    LIST_NOT_FOUND = "LIST_NOT_FOUND"                # 清单不存在
    LIST_LOCKED = "LIST_LOCKED"                      # 对已锁定清单做编辑操作
    EMPTY_LIST = "EMPTY_LIST"                        # 空清单不允许锁定
    DUPLICATE = "DUPLICATE"                          # 用例已在清单中
    CASE_NOT_FOUND = "CASE_NOT_FOUND"                # 用例库中无此用例
    NO_APPLICABLE_VERSION = "NO_APPLICABLE_VERSION"  # 目标版本下用例无适用版本
    VERSION_NOT_FOUND = "VERSION_NOT_FOUND"          # pin 指定 / 引用的版本不存在
    DEPRECATED_REF = "DEPRECATED_REF"                # 引用了已废弃版本（警告）
    SUPERSEDED = "SUPERSEDED"                        # 存在更新的适用版本（警告）
    REV_CONFLICT = "REV_CONFLICT"                    # 预留，原型未启用

    INVALID_ARGUMENT = "INVALID_ARGUMENT"            # 参数形状不合法（非业务错误）
    CASE_CONTENT_CHANGED = "CASE_CONTENT_CHANGED"    # 同版本内容指纹变化，违反只读前提
    LIST_NOT_LOCKED = "LIST_NOT_LOCKED"              # 导出执行用例要求清单已锁定
    EXPORT_UNSUPPORTED = "EXPORT_UNSUPPORTED"        # 用例库适配器不提供用例正文


class TaskListError(Exception):
    """清单级失败的基类。

    ``details`` 用于携带逐条明细（例如锁定校验失败的所有条目）；
    ``tasklist_id`` 让调用方在批量操作中知道是哪份清单失败。
    """

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


# ---------------------------------------------------------------------------
# 领域规则异常：由 domain/model.py 抛出
# ---------------------------------------------------------------------------
class InvalidArgument(TaskListError):
    def __init__(self, message: str = "参数不合法") -> None:
        super().__init__(ErrorCode.INVALID_ARGUMENT, message)


class TargetMissing(TaskListError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.TARGET_MISSING, "创建清单时必须指定目标软件版本"
        )


class ListLocked(TaskListError):
    def __init__(
        self,
        message: str = "清单已锁定，不能编辑用例",
        *,
        tasklist_id: str | None = None,
    ) -> None:
        super().__init__(ErrorCode.LIST_LOCKED, message, tasklist_id=tasklist_id)


class EmptyList(TaskListError):
    def __init__(self, *, tasklist_id: str | None = None) -> None:
        super().__init__(
            ErrorCode.EMPTY_LIST, "空清单不允许锁定", tasklist_id=tasklist_id
        )


class DuplicateItem(TaskListError):
    def __init__(self, case_id: str) -> None:
        super().__init__(
            ErrorCode.DUPLICATE, f"用例 {case_id} 已在清单中"
        )


# ---------------------------------------------------------------------------
# 应用层异常：由 service_layer 抛出
# ---------------------------------------------------------------------------
class ListNotFound(TaskListError):
    def __init__(self, tasklist_id: str) -> None:
        super().__init__(
            ErrorCode.LIST_NOT_FOUND, "清单不存在", tasklist_id=tasklist_id
        )


class ListNotLocked(TaskListError):
    def __init__(self, tasklist_id: str) -> None:
        super().__init__(
            ErrorCode.LIST_NOT_LOCKED,
            "只有锁定后的清单才能导出执行",
            tasklist_id=tasklist_id,
        )


class ExportUnsupported(TaskListError):
    def __init__(self, tasklist_id: str) -> None:
        super().__init__(
            ErrorCode.EXPORT_UNSUPPORTED,
            "当前用例库适配器不提供用例正文，无法导出执行输入",
            tasklist_id=tasklist_id,
        )


# ---------------------------------------------------------------------------
# 条目级反馈：不抛异常，放进返回值
# ---------------------------------------------------------------------------
REJECT_MESSAGES: dict[str, str] = {
    ErrorCode.DUPLICATE.value: "该用例已在清单中",
    ErrorCode.CASE_NOT_FOUND.value: "用例库中无此用例",
    ErrorCode.NO_APPLICABLE_VERSION.value: "目标版本下无适用版本",
    ErrorCode.VERSION_NOT_FOUND.value: "指定版本不存在",
    ErrorCode.DEPRECATED_REF.value: "引用了已废弃版本",
}


def rejection(
    case_id: str, code: ErrorCode | str, message: str | None = None
) -> dict[str, str]:
    """构造 ``rejected`` / ``warnings`` 中的一条结构化反馈。"""

    code_str = str(code)
    return {
        "use_case_id": case_id,
        "code": code_str,
        "message": message or REJECT_MESSAGES.get(code_str, code_str),
    }

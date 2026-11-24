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
    PROJECT_VERSION_MISSING = "PROJECT_VERSION_MISSING"     # 创建清单时未指定项目版本
    PROJECT_VERSION_NOT_FOUND = "PROJECT_VERSION_NOT_FOUND"  # Access 中没有该项目的该版本
    LIST_NOT_FOUND = "LIST_NOT_FOUND"                       # 清单不存在
    LIST_LOCKED = "LIST_LOCKED"                             # 对已锁定清单做编辑操作
    EMPTY_LIST = "EMPTY_LIST"                               # 空清单不允许锁定
    DUPLICATE = "DUPLICATE"                                 # 测试点已在清单中
    TESTPOINT_NOT_FOUND = "TESTPOINT_NOT_FOUND"             # 用例库中无此测试点
    NO_APPLICABLE_REVISION = "NO_APPLICABLE_REVISION"       # 项目版本下没有可用修订
    REVISION_NOT_FOUND = "REVISION_NOT_FOUND"               # 指定 / 引用的修订不存在
    TESTPOINT_CONTENT_CHANGED = "TESTPOINT_CONTENT_CHANGED"  # 同修订内容指纹变化
    SUPERSEDED = "SUPERSEDED"                               # 存在更新的适用修订（警告）

    INVALID_ARGUMENT = "INVALID_ARGUMENT"                   # 参数形状不合法（非业务错误）
    LIST_NOT_LOCKED = "LIST_NOT_LOCKED"                     # 导出执行要求清单已锁定


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


class ProjectVersionMissing(TaskListError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.PROJECT_VERSION_MISSING, "创建清单时必须指定项目版本"
        )


class ProjectVersionNotFound(TaskListError):
    """Access 中不存在该项目的该版本。"""

    def __init__(self, project_id: str, proj_ver: str) -> None:
        self.project_id = project_id
        self.proj_ver = proj_ver
        super().__init__(
            ErrorCode.PROJECT_VERSION_NOT_FOUND,
            f"项目 {project_id} 没有版本 {proj_ver}",
        )


class ListLocked(TaskListError):
    def __init__(
        self,
        message: str = "清单已锁定，不能编辑条目",
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
    def __init__(self, testpoint_id: str) -> None:
        super().__init__(
            ErrorCode.DUPLICATE, f"测试点 {testpoint_id} 已在清单中"
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


# ---------------------------------------------------------------------------
# 条目级反馈：不抛异常，放进返回值
# ---------------------------------------------------------------------------
REJECT_MESSAGES: dict[str, str] = {
    ErrorCode.DUPLICATE.value: "该测试点已在清单中",
    ErrorCode.TESTPOINT_NOT_FOUND.value: "用例库中无此测试点",
    ErrorCode.NO_APPLICABLE_REVISION.value: "项目版本下没有可用修订",
    ErrorCode.REVISION_NOT_FOUND.value: "指定修订不存在",
}


def rejection(
    testpoint_id: str, code: ErrorCode | str, message: str | None = None
) -> dict[str, str]:
    """构造 ``rejected`` / ``warnings`` 中的一条结构化反馈。"""

    code_str = str(code)
    return {
        "testpoint_id": testpoint_id,
        "code": code_str,
        "message": message or REJECT_MESSAGES.get(code_str, code_str),
    }

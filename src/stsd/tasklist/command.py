"""任务清单服务层的命令与读请求对象。

所有写操作使用 ``...Command`` 语义的命令类；读接口也使用同类请求对象。
服务函数形状是 ``(uow, command)``，字段只放调用方必须提供的数据，不放仓储、
会话等基础设施对象。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .domain.model import CopyMode


# ---------------------------------------------------------------------------
# 写命令
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CreateTaskList:
    project_version: str | int | None
    tasklist_title: str | None = None


@dataclass(frozen=True)
class CopyTaskList:
    source_tasklist_id: str
    project_version: str | int | None
    mode: str | CopyMode = CopyMode.RERESOLVE


@dataclass(frozen=True)
class LockTaskList:
    tasklist_id: str


@dataclass(frozen=True)
class AddItems:
    tasklist_id: str
    testpoint_ids: Sequence[str] | str
    pin_versions: dict[str, int] | None = None


@dataclass(frozen=True)
class RemoveItems:
    tasklist_id: str
    testpoint_ids: Sequence[str] | str


@dataclass(frozen=True)
class RenameTaskList:
    tasklist_id: str
    tasklist_title: str | None = None


# ---------------------------------------------------------------------------
# 读请求
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GetTaskList:
    tasklist_id: str


@dataclass(frozen=True)
class PreviewTaskList:
    tasklist_id: str
    view: str = "full"
    page: int = 1
    page_size: int | None = None


@dataclass(frozen=True)
class ListTaskLists:
    status: str | None = None


@dataclass(frozen=True)
class ExportTestPoints:
    tasklist_id: str

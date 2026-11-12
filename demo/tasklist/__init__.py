"""任务清单模块（TaskList）公共入口。

只导出稳定的核心类型；适配器按需从 ``tasklist.adapters`` 导入。
"""

from .errors import ErrorCode, TaskListError
from .models import CaseRef, CopyMode, ItemRecord, Status, TaskListRecord
from .ports import (
    CaseBrief,
    CaseLibraryPort,
    DurationStat,
    LastRun,
    ResolveOutcome,
    RunHistoryPort,
    VersionRecord,
)
from .repo import TaskListRepo
from .service import TaskListService

__all__ = [
    "ErrorCode",
    "TaskListError",
    "CaseRef",
    "CopyMode",
    "ItemRecord",
    "Status",
    "TaskListRecord",
    "CaseBrief",
    "CaseLibraryPort",
    "DurationStat",
    "LastRun",
    "ResolveOutcome",
    "RunHistoryPort",
    "VersionRecord",
    "TaskListRepo",
    "TaskListService",
]

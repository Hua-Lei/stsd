"""任务清单模块。

把已冻结的修订组织成可执行的清单：DRAFT → LOCKED，锁定后内容不可变。
模块只依赖 ``TestPointLibraryPort`` 与 ``RunHistoryPort`` 两个只读端口，不
引用用例库或结果系统的实现。

模块门面的服务接口形状为 ``(uow, command)``，命令与读请求对象见
``tasklist.command``。应用外层使用 ``build_tasklist_app`` 装配好的
``TaskListApp``：每个用例只接收一个 command，工作单元和端口在内部注入。
"""

from .app import TaskListApp, build_tasklist_app
from .command import (
    AddItems,
    CopyTaskList,
    CreateTaskList,
    ExportTestPoints,
    GetTaskList,
    ListTaskLists,
    LockTaskList,
    PreviewTaskList,
    RemoveItems,
    RenameTaskList,
)
from .domain.errors import (
    DuplicateItem,
    EmptyList,
    ErrorCode,
    InvalidArgument,
    ListLocked,
    ListNotFound,
    ListNotLocked,
    ProjectVersionMissing,
    ProjectVersionNotFound,
    TaskListError,
)
from .domain.hashing import compute_list_content_hash, compute_testpoint_content_hash
from .domain.model import (
    CopyMode,
    Status,
    TaskList,
    TaskListItem,
    TestPointRef,
    validate_project_version,
)
from .ports import (
    DurationStat,
    LastRun,
    ProjectVersionLookup,
    RevisionKey,
    RevisionOutcome,
    RevisionRecord,
    RunHistoryPort,
    TestPointBrief,
    TestPointLibraryPort,
)
from .service_layer.service import (
    add_items,
    copy_tasklist,
    create_tasklist,
    export_testpoints,
    get_tasklist,
    list_tasklists,
    lock_tasklist,
    preview_tasklist,
    remove_items,
    rename_tasklist,
)
from .service_layer.unit_of_work import (
    AbstractUnitOfWork,
    SqlAlchemyUnitOfWork,
)

__all__ = [
    "AbstractUnitOfWork",
    "AddItems",
    "CopyMode",
    "CopyTaskList",
    "CreateTaskList",
    "DuplicateItem",
    "DurationStat",
    "EmptyList",
    "ErrorCode",
    "ExportTestPoints",
    "GetTaskList",
    "InvalidArgument",
    "LastRun",
    "ListLocked",
    "ListNotFound",
    "ListNotLocked",
    "ListTaskLists",
    "LockTaskList",
    "PreviewTaskList",
    "ProjectVersionLookup",
    "ProjectVersionMissing",
    "ProjectVersionNotFound",
    "RemoveItems",
    "RenameTaskList",
    "RevisionKey",
    "RevisionOutcome",
    "RevisionRecord",
    "RunHistoryPort",
    "SqlAlchemyUnitOfWork",
    "Status",
    "TaskList",
    "TaskListApp",
    "TaskListError",
    "TaskListItem",
    "TestPointBrief",
    "TestPointLibraryPort",
    "TestPointRef",
    "add_items",
    "build_tasklist_app",
    "compute_list_content_hash",
    "compute_testpoint_content_hash",
    "copy_tasklist",
    "create_tasklist",
    "export_testpoints",
    "get_tasklist",
    "list_tasklists",
    "lock_tasklist",
    "preview_tasklist",
    "remove_items",
    "rename_tasklist",
    "validate_project_version",
]

"""任务清单的用例入口（应用装配）。

模块门面里的服务函数形状是 ``(uow, command)``，工作单元和外部端口由调用方
提供，供模块内测试和组合使用。本文件把基础设施装配进来，对应用外层只暴露
``command -> 读模型``：

- 工作单元在每次调用时新建，事务边界仍由服务层的 ``with uow`` 决定；
- ``TestPointLibraryPort`` / ``RunHistoryPort`` 在装配时注入，调用方看不到适配器。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from sqlalchemy.orm import Session, sessionmaker

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
from .ports import ProjectVersionLookup, RunHistoryPort, TestPointLibraryPort
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

CommandT = TypeVar("CommandT")
ResultT = TypeVar("ResultT")


@dataclass(frozen=True)
class TaskListApp:
    """任务清单的用例入口：每个字段只接收一个命令/请求对象。"""

    create_tasklist: Callable[[CreateTaskList], dict[str, Any]]
    copy_tasklist: Callable[[CopyTaskList], dict[str, Any]]
    lock_tasklist: Callable[[LockTaskList], dict[str, Any]]
    add_items: Callable[[AddItems], dict[str, Any]]
    remove_items: Callable[[RemoveItems], dict[str, Any]]
    rename_tasklist: Callable[[RenameTaskList], dict[str, Any]]
    get_tasklist: Callable[[GetTaskList], dict[str, Any]]
    preview_tasklist: Callable[[PreviewTaskList], dict[str, Any]]
    list_tasklists: Callable[[ListTaskLists], list[dict[str, Any]]]
    export_testpoints: Callable[[ExportTestPoints], list[Any]]


def build_tasklist_app(
    session_factory: sessionmaker[Session],
    proj_id: str,
    testpoints: TestPointLibraryPort,
    project_versions: ProjectVersionLookup,
    history: RunHistoryPort | None = None,
) -> TaskListApp:
    """把任务清单的用例绑定成 ``command -> 读模型`` 的可调用对象。"""

    def new_uow() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(
            session_factory, proj_id, testpoints, history
        )

    def bind(
        use_case: Callable[[AbstractUnitOfWork, CommandT], ResultT],
    ) -> Callable[[CommandT], ResultT]:
        def bound(command: CommandT) -> ResultT:
            return use_case(new_uow(), command)

        return bound

    def bind_with_project_versions(
        use_case: Callable[
            [AbstractUnitOfWork, ProjectVersionLookup, CommandT], ResultT
        ],
    ) -> Callable[[CommandT], ResultT]:
        def bound(command: CommandT) -> ResultT:
            return use_case(new_uow(), project_versions, command)

        return bound

    return TaskListApp(
        create_tasklist=bind_with_project_versions(create_tasklist),
        copy_tasklist=bind_with_project_versions(copy_tasklist),
        lock_tasklist=bind(lock_tasklist),
        add_items=bind(add_items),
        remove_items=bind(remove_items),
        rename_tasklist=bind(rename_tasklist),
        get_tasklist=bind(get_tasklist),
        preview_tasklist=bind(preview_tasklist),
        list_tasklists=bind(list_tasklists),
        export_testpoints=bind(export_testpoints),
    )

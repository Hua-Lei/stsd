'''用例库的用例入口（应用装配）。

app.py 的唯一职责：依赖预装载。

service.py 暴露 (uow, [dep,] command)，方便单测注入 Fake 依赖；

app.py 在应用启动时接收 session_factory 和外部端口
将所有服务函数包装为每次调用自动新建 uow 的 (command) -> Result 函数，供外部调用方直接调用。
'''

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from sqlalchemy.orm import Session, sessionmaker

from stsd.library.command import (
    AddTestPoint,
    AuditAndFreeze,
    CreateSection,
    DeleteNode,
    GetImplementationFiles,
    GetSectionTree,
    GetTestPointDetail,
    ReviseTestPoint,
    SetImplementation,
)
from stsd.library.ports import ImplementationFileStore, ProjectVersionLookup
from stsd.library.service_layer.service import (
    add_testpoint,
    audit_and_freeze,
    create_section,
    delete_node,
    get_implementation_files,
    get_section_tree,
    get_testpoint_detail,
    revise_testpoint,
    set_implementation,
)
from stsd.library.service_layer.unit_of_work import (
    AbstractUnitOfWork,
    SqlAlchemyUnitOfWork,
)
from stsd.library.service_layer.views import (
    SectionTreeNode,
    TestPointDetail,
    TestPointTreeNode,
    TreeNode,
)
from stsd.shared.events import EventPublisher, NullPublisher

CommandT = TypeVar('CommandT')
ResultT = TypeVar('ResultT')


@dataclass(frozen=True)
class LibraryApp:
    '''用例库的用例入口：每个字段只接收一个命令/请求对象。'''

    create_section: Callable[[CreateSection], SectionTreeNode]
    add_testpoint: Callable[[AddTestPoint], TestPointTreeNode]
    delete_node: Callable[[DeleteNode], list[str]]
    revise_testpoint: Callable[[ReviseTestPoint], TestPointDetail]
    set_implementation: Callable[[SetImplementation], TestPointDetail]
    audit_and_freeze: Callable[[AuditAndFreeze], TestPointDetail]
    get_section_tree: Callable[[GetSectionTree], list[TreeNode]]
    get_testpoint_detail: Callable[[GetTestPointDetail], TestPointDetail]
    get_implementation_files: Callable[
        [GetImplementationFiles], dict[str, str]
    ]


def build_library_app(
    session_factory: sessionmaker[Session],
    project_versions: ProjectVersionLookup,
    publisher: EventPublisher | None = None,
    *,
    files: ImplementationFileStore,
) -> LibraryApp:
    '''把用例库的用例绑定成 ``command -> 读模型`` 的可调用对象。

    ``project_versions`` 是向 Access 确认项目版本的端口，``files`` 是实现
    文件内容的存储，二者都由组装根注入；``publisher`` 会交给每个工作单元，
    事件在 ``commit()`` 成功后才发布。
    '''
    publisher = publisher or NullPublisher()

    def bind(
        use_case: Callable[[AbstractUnitOfWork, CommandT], ResultT],
    ) -> Callable[[CommandT], ResultT]:
        def bound(command: CommandT) -> ResultT:
            uow = SqlAlchemyUnitOfWork(
                session_factory, publisher, files=files
            )
            return use_case(uow, command)

        return bound

    def bind_with_project_versions(
        use_case: Callable[
            [AbstractUnitOfWork, ProjectVersionLookup, CommandT], ResultT
        ],
    ) -> Callable[[CommandT], ResultT]:
        def bound(command: CommandT) -> ResultT:
            uow = SqlAlchemyUnitOfWork(
                session_factory, publisher, files=files
            )
            return use_case(uow, project_versions, command)

        return bound

    return LibraryApp(
        create_section=bind(create_section),
        add_testpoint=bind_with_project_versions(add_testpoint),
        delete_node=bind(delete_node),
        revise_testpoint=bind_with_project_versions(revise_testpoint),
        set_implementation=bind(set_implementation),
        audit_and_freeze=bind(audit_and_freeze),
        get_section_tree=bind(get_section_tree),
        get_testpoint_detail=bind(get_testpoint_detail),
        get_implementation_files=bind(get_implementation_files),
    )

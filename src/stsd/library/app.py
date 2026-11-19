'''用例库的用例入口（应用装配）。

模块门面里的服务函数形状是 ``(uow[, dep], command)``，工作单元和外部端口
由调用方提供，供模块内测试和组合使用。本文件把基础设施装配进来，对应用
外层只暴露 ``command -> 读模型``：

- 工作单元在每次调用时新建，事务边界仍由服务层的 ``with uow`` 决定；
- ``AddTestPoint`` / ``ReviseTestPoint`` 需要向 Access 确认项目版本，
  ``ProjectVersionLookup`` 在装配时注入，调用方看不到适配器。
'''

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from sqlalchemy.orm import Session, sessionmaker

from stsd.library.command import (
    AddImplementation,
    AddTestPoint,
    AuditAndFreeze,
    CreateSection,
    DeleteNode,
    GetSectionTree,
    GetTestPointDetail,
    ReviseTestPoint,
)
from stsd.library.ports import ProjectVersionLookup
from stsd.library.service_layer.service import (
    add_implementation,
    add_testpoint,
    audit_and_freeze,
    create_section,
    delete_node,
    get_section_tree,
    get_testpoint_detail,
    revise_testpoint,
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
    add_implementation: Callable[[AddImplementation], TestPointDetail]
    audit_and_freeze: Callable[[AuditAndFreeze], TestPointDetail]
    get_section_tree: Callable[[GetSectionTree], list[TreeNode]]
    get_testpoint_detail: Callable[[GetTestPointDetail], TestPointDetail]


def build_library_app(
    session_factory: sessionmaker[Session],
    project_versions: ProjectVersionLookup,
    publisher: EventPublisher | None = None,
) -> LibraryApp:
    '''把用例库的用例绑定成 ``command -> 读模型`` 的可调用对象。

    ``project_versions`` 是向 Access 确认项目版本的端口，由组装根注入；
    ``publisher`` 会交给每个工作单元，事件在 ``commit()`` 成功后才发布。
    '''
    publisher = publisher or NullPublisher()

    def bind(
        use_case: Callable[[AbstractUnitOfWork, CommandT], ResultT],
    ) -> Callable[[CommandT], ResultT]:
        def bound(command: CommandT) -> ResultT:
            uow = SqlAlchemyUnitOfWork(session_factory, publisher)
            return use_case(uow, command)

        return bound

    def bind_with_project_versions(
        use_case: Callable[
            [AbstractUnitOfWork, ProjectVersionLookup, CommandT], ResultT
        ],
    ) -> Callable[[CommandT], ResultT]:
        def bound(command: CommandT) -> ResultT:
            uow = SqlAlchemyUnitOfWork(session_factory, publisher)
            return use_case(uow, project_versions, command)

        return bound

    return LibraryApp(
        create_section=bind(create_section),
        add_testpoint=bind_with_project_versions(add_testpoint),
        delete_node=bind(delete_node),
        revise_testpoint=bind_with_project_versions(revise_testpoint),
        add_implementation=bind(add_implementation),
        audit_and_freeze=bind(audit_and_freeze),
        get_section_tree=bind(get_section_tree),
        get_testpoint_detail=bind(get_testpoint_detail),
    )

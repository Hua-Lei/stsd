'''组装根。

这是唯一允许同时导入 access 和 library 的地方，它承担三件各模块都不该自己
决定的事：

1. 进程级的 ``start_mappers``。``clear_mappers()`` 作用于整个进程，映射的
   启停不属于任何单个模块。
2. 跨模块实现的选择。``AccessProjectVersionLookup`` 在这里构造并注入，
   library 的应用层因此不出现 Access 的名字。
3. 事件处理器的注册表。模块只依赖 ``EventPublisher``，注册表归这里。

对外交出的 ``AppContext`` 里，每个用例函数的签名都是 ``(uow, command)``；
需要外部读依赖的那两个用例，依赖已经注入好，调用方看不到它。
'''

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from stsd.access import service_layer as access_services
from stsd.access.adapters import orm as access_orm
from stsd.access.service_layer.unit_of_work import (
    AbstractUnitOfWork as AccessUnitOfWork,
)
from stsd.access.service_layer.unit_of_work import (
    SqlAlchemyUnitOfWork as SqlAlchemyAccessUnitOfWork,
)
from stsd.library import service_layer as library_services
from stsd.library.adapters import orm as library_orm
from stsd.integration.access.project_versions import AccessProjectVersionLookup
from stsd.library.command import AddTestPoint, ReviseTestPoint
from stsd.library.ports import ProjectVersionLookup
from stsd.library.service_layer.unit_of_work import (
    AbstractUnitOfWork as LibraryUnitOfWork,
)
from stsd.library.service_layer.unit_of_work import (
    SqlAlchemyUnitOfWork as SqlAlchemyLibraryUnitOfWork,
)
from stsd.library.service_layer.views import TestPointDetail, TestPointTreeNode
from stsd.shared.events import EventPublisher, NullPublisher


@dataclass(frozen=True)
class AppContext:
    '''已装配好的应用入口。

    只暴露用例函数、工作单元工厂和发布者；会话工厂、仓储、跨模块适配器等
    基础设施留在装配过程里，调用方拿不到。
    '''

    publisher: EventPublisher
    access_uow: Callable[[], AccessUnitOfWork]
    library_uow: Callable[[], LibraryUnitOfWork]

    # Access 用例
    create_user: Callable[..., object]
    create_project: Callable[..., object]
    add_project_version: Callable[..., object]
    add_user_to_project: Callable[..., object]
    get_user_projects: Callable[..., object]
    get_project_members: Callable[..., object]
    list_project_versions: Callable[..., object]
    get_project_version: Callable[..., object]

    # 用例库用例
    create_section: Callable[..., object]
    add_testpoint: Callable[..., object]
    delete_node: Callable[..., object]
    revise_testpoint: Callable[..., object]
    add_implementation: Callable[..., object]
    audit_and_freeze: Callable[..., object]
    get_section_tree: Callable[..., object]
    get_testpoint_detail: Callable[..., object]


def start_mappers() -> None:
    '''启动两个模块的 ORM 映射。重复调用安全。'''
    access_orm.start_mappers()
    library_orm.start_mappers()


def reset_mappers() -> None:
    '''清空映射。

    ``clear_mappers()`` 是进程级的，清一次会把两个模块的映射一起清掉，所以
    这件事只在这里提供，模块门面上不再暴露 ``stop_mappers``。
    '''
    access_orm.stop_mappers()


def bootstrap(
    session_factory: sessionmaker[Session],
    publisher: EventPublisher | None = None,
    project_versions: ProjectVersionLookup | None = None,
) -> AppContext:
    '''装配应用。

    ``publisher`` 缺省为 ``NullPublisher``：两个模块目前都没有领域事件。
    ``project_versions`` 缺省包装 Access 的读服务；测试可以注入内存实现，
    从而在不建 Access 表的情况下测用例库。
    '''
    start_mappers()

    publisher = publisher or NullPublisher()
    lookup = project_versions or AccessProjectVersionLookup(session_factory)

    # 这两个用例需要外部读依赖。用显式闭包而非 functools.partial，是为了让
    # 对外的签名正好是 (uow, command)，调用方看不到已注入的 lookup。
    def add_testpoint(
        uow: LibraryUnitOfWork, command: AddTestPoint
    ) -> TestPointTreeNode:
        return library_services.add_testpoint(uow, lookup, command)

    def revise_testpoint(
        uow: LibraryUnitOfWork, command: ReviseTestPoint
    ) -> TestPointDetail:
        return library_services.revise_testpoint(uow, lookup, command)

    return AppContext(
        publisher=publisher,
        access_uow=lambda: SqlAlchemyAccessUnitOfWork(
            session_factory, publisher
        ),
        library_uow=lambda: SqlAlchemyLibraryUnitOfWork(
            session_factory, publisher
        ),
        create_user=access_services.create_user,
        create_project=access_services.create_project,
        add_project_version=access_services.add_project_version,
        add_user_to_project=access_services.add_user_to_project,
        get_user_projects=access_services.get_user_projects,
        get_project_members=access_services.get_project_members,
        list_project_versions=access_services.list_project_versions,
        get_project_version=access_services.get_project_version,
        create_section=library_services.create_section,
        add_testpoint=add_testpoint,
        delete_node=library_services.delete_node,
        revise_testpoint=revise_testpoint,
        add_implementation=library_services.add_implementation,
        audit_and_freeze=library_services.audit_and_freeze,
        get_section_tree=library_services.get_section_tree,
        get_testpoint_detail=library_services.get_testpoint_detail,
    )

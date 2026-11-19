'''组装根。

这是把模块装配成应用的地方，只做三件事：

1. 进程级 mapper 的启停。``clear_mappers()`` 作用于整个进程，映射的启停
   不属于任何单个模块。
2. 跨模块依赖的选择。把 Access 已经装配好的读接口适配成用例库的
   ``ProjectVersionLookup``，再交给用例库的装配函数。
3. 组装 ``AppContext``。它只暴露事件发布者和两个模块的用例入口；每个用例
   只接收一个 command，工作单元由模块的装配函数在内部按次创建，调用方
   看不到会话和事务。

模块门面仍保留 ``(uow[, dep], command)`` 形状，供模块内测试和组合使用；
``stsd.bootstrap`` 与 ``stsd.integration`` 是仅有的跨模块导入点。

事件：模块的工作单元已经支持在 ``commit()`` 成功后发布事件，但当前两个
模块都没有事件。出现事件和订阅者后，由模块提供注册入口，在这里的组装
过程中调用；不要在本文件里手写订阅表。
'''

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from stsd.access import AccessApp, build_access_app
from stsd.access.adapters import orm as access_orm
from stsd.integration.access import AccessProjectVersionLookup
from stsd.library import LibraryApp, build_library_app
from stsd.library.adapters import orm as library_orm
from stsd.library.ports import ProjectVersionLookup
from stsd.shared.events import EventPublisher, NullPublisher


@dataclass(frozen=True)
class AppContext:
    '''已装配好的应用入口。

    只暴露事件发布者和各模块的用例入口。会话工厂、工作单元、仓储、跨模块
    适配器留在装配过程里，调用方拿不到；每个用例只接收一个 command。
    '''

    publisher: EventPublisher
    access: AccessApp
    library: LibraryApp


def start_mappers() -> None:
    '''启动两个模块的 ORM 映射。重复调用安全。'''
    access_orm.start_mappers()
    library_orm.start_mappers()


def reset_mappers() -> None:
    '''清空映射。

    ``clear_mappers()`` 是进程级的，清一次会把两个模块的映射一起清掉，所以
    这件事只在这里提供，模块门面上不暴露 ``stop_mappers``。
    '''
    access_orm.stop_mappers()


def bootstrap(
    session_factory: sessionmaker[Session],
    publisher: EventPublisher | None = None,
    project_versions: ProjectVersionLookup | None = None,
) -> AppContext:
    '''装配应用。

    ``publisher`` 缺省为 ``NullPublisher``：两个模块目前都没有领域事件。
    ``project_versions`` 缺省把 Access 的读接口适配成用例库的端口；测试
    可以注入内存实现，从而在不建 Access 数据的情况下测用例库。
    '''
    start_mappers()

    publisher = publisher or NullPublisher()
    access = build_access_app(session_factory, publisher)
    lookup = project_versions or AccessProjectVersionLookup(
        access.get_project_version
    )
    library = build_library_app(
        session_factory, project_versions=lookup, publisher=publisher
    )
    return AppContext(publisher=publisher, access=access, library=library)

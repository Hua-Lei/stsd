'''组装根。

这是把模块装配成应用的地方，只做三件事：

1. 进程级 mapper 的启停。``clear_mappers()`` 作用于整个进程，映射的启停
   不属于任何单个模块。
2. 跨模块依赖的选择。把 Access 的读接口适配成用例库和 TaskList 的版本端口，
   把用例库的读接口适配成 TaskList 端口和执行器读取端口。
3. 组装 ``AppContext`` / ``ExecutionContext``。调用方只看到 ``command -> 读模型``
   和 ``Executor`` 的入口；工作单元由模块的装配函数在内部按次创建，调用方
   看不到会话和事务。

模块门面仍保留 ``(uow[, dep], command)`` 形状，供模块内测试和组合使用；
``stsd.bootstrap`` 与 ``stsd.integration`` 是仅有的跨模块导入点。
'''

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from stsd.access import AccessApp, build_access_app
from stsd.access.adapters import orm as access_orm
from stsd.config import ExecutionSettings, StorageSettings
from stsd.executor import ExecutionStore, Executor, RevisionRunner
from stsd.executor.adapters.platform import PytestPlatform
from stsd.executor.adapters.sandbox import (
    DockerSandboxFactory,
    LocalSandboxFactory,
)
from stsd.executor.ports import PlatformAdapter, SandboxFactory
from stsd.integration.access import (
    AccessProjectConfigLookup,
    AccessProjectVersionLookup,
)
from stsd.integration.library import (
    LibraryRevisionReader,
    LibraryTestPointAdapter,
)
from stsd.integration.tasklist import TaskListTaskReader
from stsd.library import LibraryApp, build_library_app
from stsd.library.adapters import orm as library_orm
from stsd.library.adapters.files import LocalFileStore
from stsd.library.ports import ImplementationFileStore, ProjectVersionLookup
from stsd.shared.events import (
    EventPublisher,
    MessageBus,
    NullPublisher,
)
from stsd.tasklist import TaskListApp, build_tasklist_app
from stsd.tasklist.adapters.orm import start_mappers as start_tasklist_mappers


@dataclass(frozen=True)
class AppContext:
    '''Access 与用例库的用例入口。'''

    publisher: EventPublisher
    access: AccessApp
    library: LibraryApp


@dataclass(frozen=True)
class ExecutionContext:
    '''一个项目内可执行任务的入口：Access、用例库、TaskList 与执行器。'''

    stsd: AppContext
    tasklist: TaskListApp
    executor: Executor
    publisher: EventPublisher

    @property
    def access(self) -> AccessApp:
        return self.stsd.access

    @property
    def library(self) -> LibraryApp:
        return self.stsd.library


def start_mappers() -> None:
    '''启动 Access 与用例库的 ORM 映射。重复调用安全。'''

    access_orm.start_mappers()
    library_orm.start_mappers()


def reset_mappers() -> None:
    '''清空映射。

    ``clear_mappers()`` 是进程级的，清一次会把所有模块的映射一起清掉，所以
    这件事只在这里提供，模块门面上不暴露 ``stop_mappers``。
    '''

    access_orm.stop_mappers()


def bootstrap(
    session_factory: sessionmaker[Session],
    publisher: EventPublisher | None = None,
    project_versions: ProjectVersionLookup | None = None,
    file_store: ImplementationFileStore | None = None,
) -> AppContext:
    '''装配 Access 与用例库。

    ``project_versions`` 缺省把 Access 的读接口适配成用例库的端口；测试
    可以注入内存实现，从而在不建 Access 数据的情况下测用例库。
    ``file_store`` 缺省把实现文件放在 ``STSD_FILE_ROOT`` 指向的本地目录。
    '''

    start_mappers()

    publisher = publisher or NullPublisher()
    access = build_access_app(session_factory, publisher)
    lookup = project_versions or AccessProjectVersionLookup(
        access.get_project_version
    )
    files = file_store or LocalFileStore(StorageSettings().file_root)
    library = build_library_app(
        session_factory,
        project_versions=lookup,
        publisher=publisher,
        files=files,
    )
    return AppContext(publisher=publisher, access=access, library=library)


def bootstrap_executor(
    session_factory: sessionmaker[Session],
    proj_id: str,
    *,
    publisher: EventPublisher | None = None,
    project_versions: ProjectVersionLookup | None = None,
    file_store: ImplementationFileStore | None = None,
    engine: Engine | None = None,
    work_root: str | Path | None = None,
    store: ExecutionStore | None = None,
    sandbox_factory: SandboxFactory | None = None,
    platform: PlatformAdapter | None = None,
) -> ExecutionContext:
    '''装配一个项目的 TaskList 与执行器。

    读接口由集成层适配。``STSD_RUNTIME`` 为 ``local`` 时用子进程沙箱和
    当前解释器里的 pytest，不安装声明里的依赖；为 ``docker`` 时用
    ``python:<版本>-slim`` 容器并在容器里安装依赖。调用方可以注入 store、
    沙箱工厂和平台适配器替换基础设施。
    '''
    settings = ExecutionSettings()
    runtime = settings.runtime.strip().lower()
    if runtime not in ('local', 'docker'):
        raise ValueError(
            f'STSD_RUNTIME must be "local" or "docker", got {settings.runtime!r}'
        )
    publisher = publisher or MessageBus()
    start_mappers()
    start_tasklist_mappers()

    stsd = bootstrap(
        session_factory,
        publisher=publisher,
        project_versions=project_versions,
        file_store=file_store,
    )
    lookup = project_versions or AccessProjectVersionLookup(
        stsd.access.get_project_version
    )
    tasklist = build_tasklist_app(
        session_factory,
        proj_id,
        LibraryTestPointAdapter(stsd.library),
        lookup,
    )
    execution_store = store or ExecutionStore(
        engine or _engine_from_session_factory(session_factory)
    )
    execution_store.create_schema()

    if sandbox_factory is None:
        if runtime == 'docker':
            sandbox_factory = DockerSandboxFactory(
                image_prefix=settings.docker_image,
                network=settings.docker_network,
            )
        else:
            sandbox_factory = LocalSandboxFactory(
                work_root if work_root is not None else settings.work_root
            )
    if platform is None:
        if runtime == 'docker':
            platform = PytestPlatform(
                python='python',
                install_pytest=True,
                install_requirements=True,
            )
        else:
            platform = PytestPlatform(
                python=sys.executable,
                install_pytest=False,
                install_requirements=False,
            )
    runner = RevisionRunner(
        sandbox_factory,
        platform,
        revision_timeout=settings.revision_timeout,
    )
    executor = Executor(
        store=execution_store,
        task_reader=TaskListTaskReader(tasklist),
        testpoint_reader=LibraryRevisionReader(stsd.library),
        binding_lookup=AccessProjectConfigLookup(stsd.access.get_project),
        runner=runner,
        publisher=publisher,
        lease_seconds=settings.lease_seconds,
        poll_interval=settings.poll_interval,
        project_id=proj_id,
    )
    return ExecutionContext(
        stsd=stsd,
        tasklist=tasklist,
        executor=executor,
        publisher=publisher,
    )


def _engine_from_session_factory(
    session_factory: sessionmaker[Session],
) -> Engine:
    bind = session_factory.kw.get('bind')
    if not isinstance(bind, Engine):
        raise TypeError(
            'bootstrap_executor needs a session factory bound to an Engine'
        )
    return bind

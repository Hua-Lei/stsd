'''组装根。

这是把模块装配成应用的地方，只做三件事：

1. 进程级 mapper 的启停。``clear_mappers()`` 作用于整个进程，映射的启停
   不属于任何单个模块。
2. 跨模块依赖的选择。把 Access 已经装配好的读接口适配成用例库和任务清单的
   ``ProjectVersionLookup``，把用例库的读接口适配成任务清单的
   ``TestPointLibraryPort``。
3. 组装 ``AppContext`` / ``ExperimentContext``。调用方只看到
   ``command -> 读模型`` 的入口；工作单元由模块的装配函数在内部按次创建，
   调用方看不到会话和事务。

模块门面仍保留 ``(uow[, dep], command)`` 形状，供模块内测试和组合使用；
``stsd.bootstrap`` 与 ``stsd.integration`` 是仅有的跨模块导入点。
'''

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from stsd.access import AccessApp, build_access_app
from stsd.access.adapters import orm as access_orm
from stsd.analysis import AnalysisApp, build_analysis_app
from stsd.analysis.adapters.orm import start_mappers as start_analysis_mappers
from stsd.integration.access import AccessProjectVersionLookup
from stsd.integration.library import LibraryTestPointAdapter
from stsd.integration.payload import DecodingSnapshotPort
from stsd.integration.results import ResultsRunReadAdapter
from stsd.library import GetTestPointDetail, LibraryApp, build_library_app
from stsd.library.adapters import orm as library_orm
from stsd.library.ports import ProjectVersionLookup
from stsd.results import (
    GetRun,
    ResultError,
    ResultsApp,
    SqlAlchemyUnitOfWork as ResultUoW,
    build_results_app,
    get_run,
)
from stsd.results.adapters.orm import start_mappers as start_result_mappers
from stsd.results.adapters.tasklist import TaskListSnapshotAdapter
from stsd.results.adapters.tasklist_history import TaskListHistoryAdapter
from stsd.shared.events import EventPublisher, NullPublisher
from stsd.tasklist import (
    SqlAlchemyUnitOfWork as TaskListUoW,
    TaskListApp,
    TestPointLibraryPort,
    build_tasklist_app,
)
from stsd.tasklist.adapters.orm import start_mappers as start_tasklist_mappers
from stsd.workflow import WorkflowApp, build_workflow_app
from stsd.workflow.adapters import HttpExecutorAdapter, ResultsRecorderAdapter


@dataclass(frozen=True)
class AppContext:
    '''Access 与用例库的用例入口。'''

    publisher: EventPublisher
    access: AccessApp
    library: LibraryApp


@dataclass(frozen=True)
class ExperimentContext:
    '''实验平台的完整入口：Access、用例库、TaskList、Results、Analysis、Workflow。'''

    stsd: AppContext
    tasklist: TaskListApp
    results: ResultsApp
    analysis: AnalysisApp
    workflow: WorkflowApp

    @property
    def publisher(self) -> EventPublisher:
        return self.stsd.publisher

    @property
    def access(self) -> AccessApp:
        return self.stsd.access

    @property
    def library(self) -> LibraryApp:
        return self.stsd.library


def start_mappers() -> None:
    '''启动 Access、用例库、TaskList、Results、Analysis 的 ORM 映射。重复调用安全。'''

    access_orm.start_mappers()
    library_orm.start_mappers()
    start_tasklist_mappers()
    start_result_mappers()
    start_analysis_mappers()


def reset_mappers() -> None:
    '''清空映射。

    ``clear_mappers()`` 是进程级的，清一次会把所有模块的映射一起清掉，所以
    这件事只在这里提供，模块门面上不暴露 ``stop_mappers``。
    '''

    access_orm.stop_mappers()


def build_library_port(library: LibraryApp) -> TestPointLibraryPort:
    '''把用例库读接口适配成 TaskList 的端口。'''

    return LibraryTestPointAdapter(
        lambda testpoint_id, revision_ver: library.get_testpoint_detail(
            GetTestPointDetail(
                testpoint_id=testpoint_id,
                revision_ver=revision_ver,
            )
        )
    )


def bootstrap(
    session_factory: sessionmaker[Session],
    publisher: EventPublisher | None = None,
    project_versions: ProjectVersionLookup | None = None,
) -> AppContext:
    '''装配 Access 与用例库。

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


def bootstrap_experiment(
    session_factory: sessionmaker[Session],
    proj_id: str,
    *,
    publisher: EventPublisher | None = None,
    project_versions: ProjectVersionLookup | None = None,
    testpoints: TestPointLibraryPort | None = None,
    stsd: AppContext | None = None,
) -> ExperimentContext:
    '''装配整个实验平台。

    - ``stsd`` 允许复用已经装配好的 Access + 用例库；
    - ``project_versions`` 同时供用例库和任务清单确认项目版本；
    - ``testpoints`` 缺省用真实的用例库适配器，测试可以注入内存实现。
    '''

    start_mappers()
    if stsd is None:
        stsd = bootstrap(
            session_factory,
            publisher=publisher,
            project_versions=project_versions,
        )
    lookup = project_versions or AccessProjectVersionLookup(
        stsd.access.get_project_version
    )
    port = testpoints or build_library_port(stsd.library)

    def result_uow() -> ResultUoW:
        return ResultUoW(session_factory, proj_id)

    history = TaskListHistoryAdapter(
        lambda: ResultUoW(session_factory, proj_id, immediate=False)
    )

    def task_uow() -> TaskListUoW:
        return TaskListUoW(session_factory, proj_id, port, history)

    snapshots = DecodingSnapshotPort(TaskListSnapshotAdapter(task_uow))

    def read_run(run_id: str) -> dict[str, Any] | None:
        try:
            return get_run(result_uow(), GetRun(run_id=run_id))
        except ResultError as exc:
            if exc.code == "RUN_NOT_FOUND":
                return None
            raise

    return ExperimentContext(
        stsd=stsd,
        tasklist=build_tasklist_app(
            session_factory, proj_id, port, lookup, history
        ),
        results=build_results_app(session_factory, proj_id),
        analysis=build_analysis_app(
            session_factory, ResultsRunReadAdapter(read_run)
        ),
        workflow=build_workflow_app(
            ResultsRecorderAdapter(result_uow),
            snapshots,
            HttpExecutorAdapter(),
        ),
    )

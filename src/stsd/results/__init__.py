"""结果系统模块。

接收执行结果并保存：RunRecord 是执行记录，TestPointResult 是逐条结果，
StepResult 是逐步骤证据。分析报告与回归/补测建议由 ``stsd.analysis`` 提供。

模块门面的服务接口形状为 ``(uow, command)``，命令与读请求对象见
``results.command``。应用外层使用 ``build_results_app`` 装配好的
``ResultsApp``：每个用例只接收一个 command，工作单元在内部注入。
"""

from .app import ResultsApp, build_results_app
from .command import (
    CompareRuns,
    GetRun,
    ListRuns,
    RecordAbortedExecution,
    RecordExecution,
    RecordRun,
)
from .domain.errors import ErrorCode, ResultError
from .domain.model import (
    RunKind,
    RunRecord,
    RunStatus,
    StepResult,
    StepStatus,
    TestPointResult,
    TestPointStatus,
)
from .ports import TaskListSnapshot, TaskListSnapshotItem, TaskListSnapshotPort
from .service_layer.service import (
    compare_runs,
    get_run,
    list_runs,
    record_aborted_execution,
    record_execution,
    record_run,
)
from .service_layer.unit_of_work import (
    AbstractUnitOfWork,
    SqlAlchemyUnitOfWork,
)

__all__ = [
    "AbstractUnitOfWork",
    "CompareRuns",
    "ErrorCode",
    "GetRun",
    "ListRuns",
    "RecordAbortedExecution",
    "RecordExecution",
    "RecordRun",
    "ResultError",
    "ResultsApp",
    "RunKind",
    "RunRecord",
    "RunStatus",
    "SqlAlchemyUnitOfWork",
    "StepResult",
    "StepStatus",
    "TaskListSnapshot",
    "TaskListSnapshotItem",
    "TaskListSnapshotPort",
    "TestPointResult",
    "TestPointStatus",
    "build_results_app",
    "compare_runs",
    "get_run",
    "list_runs",
    "record_aborted_execution",
    "record_execution",
    "record_run",
]

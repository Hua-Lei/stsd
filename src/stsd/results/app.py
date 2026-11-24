"""结果系统的用例入口（应用装配）。

模块门面里的服务函数形状是 ``(uow, command)``，工作单元由调用方提供，供
模块内测试和组合使用。本文件把基础设施装配进来，对应用外层只暴露
``command -> 读模型``：工作单元在每次调用时新建，调用方看不到会话和事务。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from sqlalchemy.orm import Session, sessionmaker

from .command import (
    CompareRuns,
    GetRun,
    ListRuns,
    RecordAbortedExecution,
    RecordExecution,
    RecordRun,
)
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

CommandT = TypeVar("CommandT")
ResultT = TypeVar("ResultT")


@dataclass(frozen=True)
class ResultsApp:
    """结果系统的用例入口：每个字段只接收一个命令/请求对象。"""

    record_execution: Callable[[RecordExecution], dict[str, Any]]
    record_aborted_execution: Callable[[RecordAbortedExecution], dict[str, Any]]
    record_run: Callable[[RecordRun], dict[str, Any]]
    get_run: Callable[[GetRun], dict[str, Any]]
    list_runs: Callable[[ListRuns], list[dict[str, Any]]]
    compare_runs: Callable[[CompareRuns], dict[str, Any]]


def build_results_app(
    session_factory: sessionmaker[Session], proj_id: str
) -> ResultsApp:
    """把结果系统的用例绑定成 ``command -> 读模型`` 的可调用对象。"""

    def bind(
        use_case: Callable[[AbstractUnitOfWork, CommandT], ResultT],
    ) -> Callable[[CommandT], ResultT]:
        def bound(command: CommandT) -> ResultT:
            uow = SqlAlchemyUnitOfWork(session_factory, proj_id)
            return use_case(uow, command)

        return bound

    return ResultsApp(
        record_execution=bind(record_execution),
        record_aborted_execution=bind(record_aborted_execution),
        record_run=bind(record_run),
        get_run=bind(get_run),
        list_runs=bind(list_runs),
        compare_runs=bind(compare_runs),
    )

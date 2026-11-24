"""Workflow 的结果记录适配器：把结果系统适配成 ResultRecorderPort。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from stsd.shared.execution_contract import ExecutionOutcome
from stsd.results import (
    AbstractUnitOfWork as ResultUoW,
    RecordAbortedExecution,
    RecordExecution,
    record_aborted_execution,
    record_execution,
)
from stsd.results.ports import TaskListSnapshot


class ResultsRecorderAdapter:
    """把 Results 的记录函数适配成 Workflow 的 ResultRecorderPort。"""

    def __init__(self, uow_factory: Callable[[], ResultUoW]) -> None:
        self._uow_factory = uow_factory

    def record_execution(
        self,
        snapshot: TaskListSnapshot,
        outcome: ExecutionOutcome,
        *,
        environment_name: str,
        base_url: str,
        timeout_seconds: float = 6.0,
        kind: str = "MANUAL",
        source_run_id: str | None = None,
    ) -> dict[str, Any]:
        return record_execution(
            self._uow_factory(),
            RecordExecution(
                snapshot=snapshot,
                outcome=outcome,
                environment_name=environment_name,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
                kind=kind,
                source_run_id=source_run_id,
            ),
        )

    def record_aborted_execution(
        self,
        snapshot: TaskListSnapshot,
        *,
        error_message: str,
        environment_name: str,
        base_url: str,
        timeout_seconds: float = 6.0,
        kind: str = "MANUAL",
        source_run_id: str | None = None,
    ) -> dict[str, Any]:
        return record_aborted_execution(
            self._uow_factory(),
            RecordAbortedExecution(
                snapshot=snapshot,
                error_message=error_message,
                environment_name=environment_name,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
                kind=kind,
                source_run_id=source_run_id,
            ),
        )


__all__ = ["ResultsRecorderAdapter"]

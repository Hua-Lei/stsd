"""Workflow 依赖的外部端口。"""

from __future__ import annotations

from typing import Protocol

from stsd.shared.execution_contract import ExecutionOutcome, ExecutionPlan
from stsd.results.ports import TaskListSnapshot


class ExecutorPort(Protocol):
    """Workflow 对执行器的唯一依赖；实现不能写结果库。"""

    def execute(self, plan: ExecutionPlan) -> ExecutionOutcome:
        """执行一组用例，返回原始执行结果。"""
        ...


class ResultRecorderPort(Protocol):
    """Workflow 对结果记录能力的唯一依赖，避免直接 import Results 服务。"""

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
    ) -> dict:
        ...

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
    ) -> dict:
        ...

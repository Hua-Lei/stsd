"""Workflow 的执行器适配器：把 CaseExecutor 适配成 ExecutorPort。"""

from __future__ import annotations

from typing import Any

import httpx

from stsd.shared.execution_contract import ExecutionOutcome, ExecutionPlan
from stsd.executor import CaseExecutor


class HttpExecutorAdapter:
    """每次执行创建一个 httpx.Client；测试可注入 MockTransport。"""

    def __init__(self, client_factory: Any = None) -> None:
        self._client_factory = client_factory or (lambda: httpx.Client())

    def execute(self, plan: ExecutionPlan) -> ExecutionOutcome:
        with self._client_factory() as client:
            return CaseExecutor(client).execute(plan)

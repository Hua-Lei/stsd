"""结果系统服务层的命令与读请求对象。

写入命令要么携带已经完成的 ``ExecutionOutcome``，要么携带中止原因；
读请求覆盖 RunRecord 查询、列表与对比。
"""

from __future__ import annotations

from dataclasses import dataclass

from stsd.shared.execution_contract import ExecutionOutcome

from .domain.model import RunKind, RunRecord
from .ports import TaskListSnapshot


# ---------------------------------------------------------------------------
# 写命令
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RecordExecution:
    snapshot: TaskListSnapshot
    outcome: ExecutionOutcome
    environment_name: str
    base_url: str
    timeout_seconds: float = 6.0
    kind: RunKind | str = RunKind.MANUAL
    source_run_id: str | None = None


@dataclass(frozen=True)
class RecordAbortedExecution:
    snapshot: TaskListSnapshot
    error_message: str
    environment_name: str
    base_url: str
    timeout_seconds: float = 6.0
    kind: RunKind | str = RunKind.MANUAL
    source_run_id: str | None = None


@dataclass(frozen=True)
class RecordRun:
    run: RunRecord


# ---------------------------------------------------------------------------
# 读请求
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GetRun:
    run_id: str
    include_steps: bool = True


@dataclass(frozen=True)
class ListRuns:
    tasklist_id: str | None = None
    limit: int = 50


@dataclass(frozen=True)
class CompareRuns:
    base_run_id: str
    variant_run_id: str

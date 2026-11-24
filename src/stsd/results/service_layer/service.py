"""结果模块应用层：记录 RunRecord、查询与对比。

这里不调用执行器；执行编排在 ``workflow`` 层。结果模块只接收已经完成的
``ExecutionOutcome``，或者在执行器整体失败时接收一个中止原因。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from stsd.shared.execution_contract import TestPointOutcome

from ..domain.model import RunKind, RunRecord, TestPointResult
from ..domain.errors import InvalidArgument, InvalidExecution, RunNotFound
from ..ports import TaskListSnapshot
from ..command import (
    CompareRuns,
    GetRun,
    ListRuns,
    RecordAbortedExecution,
    RecordExecution,
    RecordRun,
)
from . import views
from .unit_of_work import AbstractUnitOfWork

EXECUTOR_VERSION = "0.1"


# ===========================================================================
# 记录执行结果（不负责执行）
# ===========================================================================
def record_execution(
    uow: AbstractUnitOfWork, command: RecordExecution
) -> dict[str, Any]:
    """把一次执行结果写入结果库。

    执行器已经执行完毕；本函数只做映射、RunRecord 状态计算和持久化。
    如果执行器返回 aborted 或结果与快照不一致，RunRecord 记为 ABORTED。
    """

    snapshot = command.snapshot
    run = _new_run(
        snapshot,
        kind=_normalize_kind(command.kind),
        environment_name=command.environment_name,
        base_url=command.base_url,
        timeout_seconds=command.timeout_seconds,
        source_run_id=command.source_run_id,
    )
    run.summary["total"] = len(snapshot.items)

    if command.outcome.status == "aborted":
        run.abort("执行器返回 aborted")
        return _persist(uow, run)

    try:
        results = _map_results(snapshot, command.outcome.testpoints)
        run.complete(results)
    except (InvalidExecution, ValueError) as exc:
        # 结果条目不匹配或重复时，保留一条可查的 ABORTED 记录，不抛到 API。
        run.abort(str(exc))
        return _persist(uow, run)

    return _persist(uow, run)


def record_aborted_execution(
    uow: AbstractUnitOfWork, command: RecordAbortedExecution
) -> dict[str, Any]:
    """执行器整体抛错时，仍保留一条可查的 ABORTED RunRecord。"""

    snapshot = command.snapshot
    run = _new_run(
        snapshot,
        kind=_normalize_kind(command.kind),
        environment_name=command.environment_name,
        base_url=command.base_url,
        timeout_seconds=command.timeout_seconds,
        source_run_id=command.source_run_id,
    )
    run.summary["total"] = len(snapshot.items)
    run.abort(command.error_message)
    return _persist(uow, run)


def record_run(
    uow: AbstractUnitOfWork, command: RecordRun
) -> dict[str, Any]:
    """结果写入接口：外部执行器已完成 RunRecord 时，直接保存。"""
    return _persist(uow, command.run)


# ===========================================================================
# 查询
# ===========================================================================
def get_run(
    uow: AbstractUnitOfWork, command: GetRun
) -> dict[str, Any]:
    """读取一次 RunRecord；默认带逐步骤证据，列表场景可关掉 steps。"""

    with uow:
        run = uow.runs.get(command.run_id)
        if run is None:
            raise RunNotFound(command.run_id)
        return views.run_detail(run, include_steps=command.include_steps)


def list_runs(
    uow: AbstractUnitOfWork, command: ListRuns
) -> list[dict[str, Any]]:
    """按清单/时间列出 RunRecord；只返回 summary，不加载逐条步骤。"""

    with uow:
        return [views.run_list_item(run) for run in uow.runs.list_runs(
            tasklist_id=command.tasklist_id, limit=command.limit
        )]


def compare_runs(
    uow: AbstractUnitOfWork, command: CompareRuns
) -> dict[str, Any]:
    """比较基线 RunRecord 与变体 RunRecord 的逐测试点状态和修订版本。"""

    with uow:
        base = uow.runs.get(command.base_run_id)
        variant = uow.runs.get(command.variant_run_id)
        if base is None:
            raise RunNotFound(command.base_run_id)
        if variant is None:
            raise RunNotFound(command.variant_run_id)
        return views.compare_runs(base, variant)


# ===========================================================================
# 内部
# ===========================================================================
def _normalize_kind(kind: RunKind | str) -> RunKind:
    """允许 Workflow 用字符串传 kind，Results 内部统一成枚举。"""

    if isinstance(kind, RunKind):
        return kind
    try:
        return RunKind(str(kind).upper())
    except ValueError as exc:
        raise InvalidArgument(f"未知 RunKind: {kind!r}") from exc


def _new_run(
    snapshot: TaskListSnapshot,
    *,
    kind: RunKind,
    environment_name: str,
    base_url: str,
    timeout_seconds: float,
    source_run_id: str | None,
) -> RunRecord:
    return RunRecord.create(
        proj_id=snapshot.proj_id,
        tasklist_id=snapshot.tasklist_id,
        tasklist_rev=snapshot.rev,
        tasklist_content_hash=snapshot.content_hash,
        project_version=snapshot.project_version,
        kind=kind,
        environment_name=environment_name,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        executor_version=EXECUTOR_VERSION,
        source_run_id=source_run_id,
    )


def _map_results(snapshot: TaskListSnapshot, outcomes: Sequence[TestPointOutcome]) -> list[TestPointResult]:
    items = {item.seq: item for item in snapshot.items}
    if len(outcomes) != len(snapshot.items):
        raise InvalidExecution("执行器返回的用例数与清单条目数不一致")
    results: list[TestPointResult] = []
    for outcome in outcomes:
        item = items.get(outcome.seq)
        if item is None:
            raise InvalidExecution(f"执行器返回了清单中不存在的 seq={outcome.seq}")
        if item.testpoint_id != outcome.testpoint_id:
            raise InvalidExecution(
                f"seq={outcome.seq} 的用例不一致: {item.testpoint_id} != {outcome.testpoint_id}"
            )
        results.append(TestPointResult.from_outcome(outcome, item.payload))
    results.sort(key=lambda item: item.seq)
    return results


def _persist(uow: AbstractUnitOfWork, run: RunRecord) -> dict[str, Any]:
    with uow:
        uow.runs.add(run)
        uow.commit()
    return views.run_detail(run, include_steps=False)

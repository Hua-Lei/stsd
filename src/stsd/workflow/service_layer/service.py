"""执行编排：读取清单快照 → 调用执行器 → 交给结果记录接口。

Workflow 只依赖端口；Results 的具体实现由 ResultsRecorderAdapter 注入。
"""

from __future__ import annotations

from typing import Any

from stsd.shared.execution_contract import Environment, ExecutionTestPoint, ExecutionPlan
from stsd.results.ports import TaskListSnapshotPort

from ..command import RunTaskList
from ..ports import ExecutorPort, ResultRecorderPort


def run_tasklist(
    recorder: ResultRecorderPort,
    snapshot_port: TaskListSnapshotPort,
    executor: ExecutorPort,
    command: RunTaskList,
) -> dict[str, Any]:
    """执行一个锁定清单，并把执行结果交给 ResultRecorderPort。"""

    snapshot = snapshot_port.get_snapshot(command.tasklist_id)
    plan = ExecutionPlan(
        testpoints=tuple(
            ExecutionTestPoint(
                seq=item.seq,
                testpoint_id=item.testpoint_id,
                revision_ver=item.revision_ver,
                content_hash=item.content_hash,
                payload=item.payload,
            )
            for item in snapshot.items
        ),
        environment=Environment(
            base_url=command.base_url,
            headers=dict(command.headers or {}),
            variables=dict(command.variables or {}),
            timeout_seconds=command.timeout_seconds,
        ),
    )

    try:
        outcome = executor.execute(plan)
    except Exception as exc:
        # 执行器整体崩溃也要留下可查询的 ABORTED RunRecord。
        return recorder.record_aborted_execution(
            snapshot,
            error_message=f"{type(exc).__name__}: {exc}",
            environment_name=command.environment_name,
            base_url=command.base_url,
            timeout_seconds=command.timeout_seconds,
            kind=command.kind,
            source_run_id=command.source_run_id,
        )

    return recorder.record_execution(
        snapshot,
        outcome,
        environment_name=command.environment_name,
        base_url=command.base_url,
        timeout_seconds=command.timeout_seconds,
        kind=command.kind,
        source_run_id=command.source_run_id,
    )

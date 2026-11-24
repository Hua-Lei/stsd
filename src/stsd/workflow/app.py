"""执行编排的用例入口（应用装配）。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from stsd.results.ports import TaskListSnapshotPort

from .command import RunTaskList
from .ports import ExecutorPort, ResultRecorderPort
from .service_layer.service import run_tasklist


@dataclass(frozen=True)
class WorkflowApp:
    """执行编排的入口：只接收一个命令，协作者在装配时注入。"""

    run_tasklist: Callable[[RunTaskList], dict[str, Any]]


def build_workflow_app(
    recorder: ResultRecorderPort,
    snapshot_port: TaskListSnapshotPort,
    executor: ExecutorPort,
) -> WorkflowApp:
    """把编排用例绑定成 ``command -> 读模型`` 的可调用对象。"""

    def bound(command: RunTaskList) -> dict[str, Any]:
        return run_tasklist(recorder, snapshot_port, executor, command)

    return WorkflowApp(run_tasklist=bound)

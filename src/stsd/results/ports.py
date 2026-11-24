"""结果模块依赖的外部端口与输入 DTO。

结果模块不直接调用任务清单服务或执行器实现：``TaskListSnapshotPort``
提供锁定清单的内容快照。执行编排由 ``workflow`` 层负责。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class TaskListSnapshotItem:
    """执行输入中的一条用例：只带执行所需的标识和正文。"""

    seq: int
    testpoint_id: str
    revision_ver: int
    content_hash: str
    title: str
    payload: Any

    @property
    def revision_key(self) -> tuple[str, int]:
        return (self.testpoint_id, self.revision_ver)


@dataclass(frozen=True)
class TaskListSnapshot:
    """锁定清单的只读快照；Results 记录 RunRecord 时使用。"""

    proj_id: str
    tasklist_id: str
    rev: int
    content_hash: str | None
    project_version: str
    title: str | None
    items: tuple[TaskListSnapshotItem, ...]


class TaskListSnapshotPort(Protocol):
    """Results 读取锁定清单的端口；适配器负责从 TaskList 取数。"""

    def get_snapshot(self, tasklist_id: str) -> TaskListSnapshot:
        """读取已锁定清单；未锁定或缺少实现正文时抛 ResultError。"""
        ...

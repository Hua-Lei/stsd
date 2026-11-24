"""任务清单快照适配器：结果模块通过端口读取锁定清单，不直接依赖其内部。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from stsd.tasklist import (
    AbstractUnitOfWork as TaskListUoW,
    ExportTestPoints,
    GetTaskList,
    export_testpoints,
    get_tasklist,
)

from ..domain.errors import SnapshotMismatch
from ..ports import TaskListSnapshot, TaskListSnapshotItem


class TaskListSnapshotAdapter:
    """把 TaskList 的读取接口适配成 Results 需要的只读快照。"""

    def __init__(self, uow_factory: Callable[[], TaskListUoW]) -> None:
        self._uow_factory = uow_factory

    def get_snapshot(self, tasklist_id: str) -> TaskListSnapshot:
        """读取锁定清单的元数据 + 有序测试点实现正文。

        清单锁定后内容不变，因此分两次读取；适配器负责把 view 的
        testpoint_ref 转成 TaskListSnapshotItem。
        """

        # 清单锁定后内容不可变；分两次读取，避免在同一个 UoW 里嵌套服务调用。
        view = get_tasklist(
            self._uow_factory(), GetTaskList(tasklist_id=tasklist_id)
        )
        payloads = export_testpoints(
            self._uow_factory(), ExportTestPoints(tasklist_id=tasklist_id)
        )

        items: list[dict[str, Any]] = view["items"]
        if len(items) != len(payloads):
            raise SnapshotMismatch(
                f"清单条目数 {len(items)} 与导出正文数 {len(payloads)} 不一致"
            )

        snapshot_items = []
        for item, payload in zip(items, payloads):
            ref = item["testpoint_ref"]
            payload_title = (
                payload.get("title") if isinstance(payload, dict) else None
            )
            snapshot_items.append(
                TaskListSnapshotItem(
                    seq=int(item["seq"]),
                    testpoint_id=str(ref["testpoint_id"]),
                    revision_ver=int(ref["revision_ver"]),
                    content_hash=str(ref["content_hash"]),
                    title=str(
                        item.get("title")
                        or ref.get("title")
                        or payload_title
                        or ref["testpoint_id"]
                    ),
                    payload=payload,
                )
            )

        return TaskListSnapshot(
            proj_id=str(view["proj_id"]),
            tasklist_id=str(view["tasklist_id"]),
            rev=int(view["rev"]),
            content_hash=view.get("content_hash"),
            project_version=str(view["project_version"]),
            title=view.get("tasklist_title"),
            items=tuple(snapshot_items),
        )

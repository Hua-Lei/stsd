'''TaskList 读接口的执行器适配。

执行器只需要清单的标识、状态和有序条目；这里把 TaskList 的读模型映射成
执行器的 ``TaskDetail``，不引入 TaskList 内部对象。
'''

from __future__ import annotations

from stsd.executor.records import TaskDetail, TaskItem
from stsd.tasklist import GetTaskList, TaskListApp, TaskListError


class TaskListTaskReader:
    def __init__(self, tasklist: TaskListApp) -> None:
        self._tasklist = tasklist

    def get_task(self, task_id: str) -> TaskDetail | None:
        try:
            data = self._tasklist.get_tasklist(
                GetTaskList(tasklist_id=task_id)
            )
        except TaskListError:
            return None

        items: list[TaskItem] = []
        for item in data['items']:
            reference = item['testpoint_ref']
            items.append(
                TaskItem(
                    seq=int(item['seq']),
                    testpoint_id=reference['testpoint_id'],
                    revision_ver=int(reference['revision_ver']),
                    content_hash=reference.get('content_hash'),
                )
            )
        return TaskDetail(
            task_id=data['tasklist_id'],
            project_id=data['proj_id'],
            project_version=data['project_version'],
            status=str(data['status']),
            items=tuple(items),
        )

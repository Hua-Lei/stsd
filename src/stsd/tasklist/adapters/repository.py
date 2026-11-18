'''任务清单仓储。

仓储只做“取聚合 / 存聚合”，不开事务、不提交、不做业务判断。事务边界由
``service_layer/unit_of_work.py`` 负责，与 ``src/library`` 的分工一致。

仓储按 ``proj_id`` 注入项目范围：其他项目的清单视为不存在。这与
``src/library/adapters/repository.py`` 的 ``LibraryRepository`` 相同。
'''

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, noload

from stsd.tasklist.adapters.orm import tasklists
from stsd.tasklist.domain.model import TaskList
from stsd.tasklist.errors import ListNotFound


class TaskListRepository(Protocol):
    @property
    def proj_id(self) -> str: ...

    def get(self, tasklist_id: str) -> TaskList | None:
        """读取聚合（含条目）；不存在或不属于本项目返回 None。"""
        ...

    def get_for_update(self, tasklist_id: str) -> TaskList | None:
        """写用例读取清单。SQLite 不支持行锁，with_for_update 会被忽略。"""
        ...

    def save(self, *tasklists: TaskList) -> None:
        """把聚合加入会话并 flush；commit / rollback 由 UoW 负责。"""
        ...

    def list_all(self, *, include_items: bool = False) -> list[TaskList]:
        """按创建时间列出本项目清单；默认不加载条目。"""
        ...


class SqlAlchemyTaskListRepository:
    def __init__(self, session: Session, proj_id: str) -> None:
        self._session = session
        self._proj_id = proj_id

    @property
    def proj_id(self) -> str:
        return self._proj_id

    # ------------------------------------------------------------------ 读
    def get(self, tasklist_id: str) -> TaskList | None:
        tasklist = self._session.get(TaskList, tasklist_id)
        if tasklist is None or tasklist.proj_id != self._proj_id:
            return None
        return tasklist

    def get_for_update(self, tasklist_id: str) -> TaskList | None:
        # 经典映射下类属性不是 SQL 列，查询条件要用表的列。
        stmt = (select(TaskList)
                .where(tasklists.c.tasklist_id == tasklist_id,
                       tasklists.c.proj_id == self._proj_id)
                .with_for_update())
        return self._session.scalars(stmt).one_or_none()

    def list_all(self, *, include_items: bool = False) -> list[TaskList]:
        stmt = (select(TaskList)
                .where(tasklists.c.proj_id == self._proj_id)
                .order_by(tasklists.c.created_at, tasklists.c.tasklist_id))
        if not include_items:
            stmt = stmt.options(noload(TaskList.items))
        return list(self._session.scalars(stmt))

    # ------------------------------------------------------------------ 写
    def save(self, *lists: TaskList) -> None:
        for tasklist in lists:
            if tasklist.proj_id != self._proj_id:
                raise ListNotFound(tasklist.tasklist_id)
        self._session.add_all(lists)
        self._session.flush()

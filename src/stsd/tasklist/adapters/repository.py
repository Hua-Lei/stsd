'''任务清单仓储。

仓储只做“取聚合 / 存聚合”，不开事务、不提交、不做业务判断。事务边界由
``service_layer/unit_of_work.py`` 负责。

仓储按 ``proj_id`` 注入项目范围：其他项目的清单视为不存在。
'''

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, lazyload

from ..domain.model import TaskList
from ..domain.errors import ListNotFound
from .orm import tasklists


class TaskListRepository(Protocol):
    """服务层依赖的仓储接口。

    这是 ``typing.Protocol``，方法体里的 ``...`` 只是类型声明，不是实现；
    真正的 SQL 实现在下面的 ``SqlAlchemyTaskListRepository``。
    """

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
        """读取清单头 + 条目；不属于当前项目视为不存在。"""

        tasklist = self._session.get(TaskList, tasklist_id)
        if tasklist is None or tasklist.proj_id != self._proj_id:
            return None
        return tasklist

    def get_for_update(self, tasklist_id: str) -> TaskList | None:
        """写用例读取；SQLite 没有行锁，写锁由 UoW 的 BEGIN IMMEDIATE 持有。"""

        # 经典映射下类属性不是 SQL 列，查询条件要用表的列。
        stmt = (select(TaskList)
                .where(tasklists.c.tasklist_id == tasklist_id,
                       tasklists.c.proj_id == self._proj_id)
                .with_for_update())
        return self._session.scalars(stmt).one_or_none()

    def list_all(self, *, include_items: bool = False) -> list[TaskList]:
        """按创建时间列出本项目清单；默认不加载条目。"""

        stmt = (select(TaskList)
                .where(tasklists.c.proj_id == self._proj_id)
                .order_by(tasklists.c.created_at, tasklists.c.tasklist_id))
        if not include_items:
            stmt = stmt.options(lazyload(TaskList.items))
        return list(self._session.scalars(stmt))

    # ------------------------------------------------------------------ 写
    def save(self, *lists: TaskList) -> None:
        """加入会话并 flush；跨项目写入直接拒绝。"""

        for tasklist in lists:
            if tasklist.proj_id != self._proj_id:
                raise ListNotFound(tasklist.tasklist_id)
        self._session.add_all(lists)
        self._session.flush()

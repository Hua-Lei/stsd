'''工作单元（Unit of Work）：一个业务用例一个事务。

- 进入时从 ``sessionmaker`` 创建会话并建好仓储；
- 退出时先 ``expunge_all`` 再回滚，最后关闭会话，返回给调用方的实体在
  会话关闭后仍可读取；
- 提交必须显式调用 ``commit()``；仓储不 commit、不 rollback。

``testpoints`` / ``history`` 是任务清单的外部只读端口，和仓储一起放在 UoW 上，
服务函数的签名因此只需要一个上下文参数。
'''

from __future__ import annotations

import abc
from typing import Self

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from ..adapters.repository import (SqlAlchemyTaskListRepository,
                                   TaskListRepository)
from ..ports import TestPointLibraryPort, RunHistoryPort


class AbstractUnitOfWork(abc.ABC):
    """服务层依赖的事务边界；tasklists 是仓储，testpoints/history 是外部端口。"""

    tasklists: TaskListRepository
    testpoints: TestPointLibraryPort
    history: RunHistoryPort | None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.rollback()

    @abc.abstractmethod
    def commit(self) -> None: ...

    @abc.abstractmethod
    def rollback(self) -> None: ...


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    """SQLAlchemy 会话版 UoW；同一实例不支持嵌套进入。"""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        proj_id: str,
        testpoints: TestPointLibraryPort,
        history: RunHistoryPort | None = None,
        *,
        immediate: bool = True,
    ) -> None:
        self._session_factory = session_factory
        self._proj_id = proj_id
        self._immediate = immediate
        self._active = False
        self.testpoints = testpoints
        self.history = history

    def __enter__(self) -> Self:
        if self._active:
            raise RuntimeError("同一个 UnitOfWork 不支持嵌套进入")
        self._session = self._session_factory()
        bind = self._session.get_bind()
        if self._immediate and bind is not None and bind.dialect.name == "sqlite":
            # SQLite 没有 FOR UPDATE；写事务在开始时就取写锁。
            self._session.execute(text("BEGIN IMMEDIATE"))
        self._active = True
        self.tasklists = SqlAlchemyTaskListRepository(self._session, self._proj_id)
        return super().__enter__()

    def __exit__(self, *args: object) -> None:
        try:
            self._session.expunge_all()
            super().__exit__(*args)
        finally:
            self._session.close()
            self._active = False

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

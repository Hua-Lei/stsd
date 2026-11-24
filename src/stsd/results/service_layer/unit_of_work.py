"""结果模块的工作单元：一个业务用例一个事务。"""

from __future__ import annotations

import abc
from typing import Self

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from ..adapters.repository import RunRepository, SqlAlchemyRunRepository


class AbstractUnitOfWork(abc.ABC):
    """服务层依赖的事务边界；具体实现负责会话和提交策略。"""

    runs: RunRepository

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.rollback()

    @abc.abstractmethod
    def commit(self) -> None: ...

    @abc.abstractmethod
    def rollback(self) -> None: ...


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    """SQLAlchemy 会话版 UoW；SQLite 下用 BEGIN IMMEDIATE 提前取写锁。"""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        proj_id: str,
        *,
        immediate: bool = True,
    ) -> None:
        self._session_factory = session_factory
        self._proj_id = proj_id
        self._immediate = immediate
        self._active = False

    def __enter__(self) -> Self:
        if self._active:
            raise RuntimeError("同一个 UnitOfWork 不支持嵌套进入")
        self._session = self._session_factory()
        bind = self._session.get_bind()
        if self._immediate and bind is not None and bind.dialect.name == "sqlite":
            # SQLite 没有行锁；写事务一开始就取写锁，避免读改写竞争。
            self._session.execute(text("BEGIN IMMEDIATE"))
        self._active = True
        self.runs = SqlAlchemyRunRepository(self._session, self._proj_id)
        return super().__enter__()

    def __exit__(self, *args: object) -> None:
        try:
            # 回滚会让对象过期；先分离，返回给调用方的结果仍可读。
            self._session.expunge_all()
            super().__exit__(*args)
        finally:
            self._session.close()
            self._active = False

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

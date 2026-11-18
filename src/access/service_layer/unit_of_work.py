'''Access 工作单元。

一次业务用例一个事务：进入时创建会话和仓储，退出时回滚未提交的改动，
提交必须显式调用 ``commit()``。服务层返回的都是读模型，不依赖会话关闭后
的实体状态。
'''

from __future__ import annotations

import abc
from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from ..adapters.repository import AccessRepository, SqlAlchemyAccessRepository


class AbstractUnitOfWork(abc.ABC):
    access: AccessRepository

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.rollback()

    @abc.abstractmethod
    def commit(self) -> None: ...

    @abc.abstractmethod
    def rollback(self) -> None: ...


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __enter__(self) -> Self:
        self._session = self._session_factory()
        self.access = SqlAlchemyAccessRepository(self._session)
        return super().__enter__()

    def __exit__(self, *args: object) -> None:
        super().__exit__(*args)
        self._session.close()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

'''用例库工作单元。

一次业务用例一个事务：进入时创建会话与仓储，退出时回滚未提交的改动，
提交必须显式调用 ``commit()``。

外部端口不放在工作单元里；它们通过服务层参数 ``dep``（``ProjectVersionLookup``）
显式传入。
'''

from __future__ import annotations

import abc
from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from stsd.library.adapters.repository import (
    LibraryRepository,
    SqlAlchemyLibraryRepository,
)


class AbstractUnitOfWork(abc.ABC):
    library: LibraryRepository

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
        self.library = SqlAlchemyLibraryRepository(self._session)
        return super().__enter__()

    def __exit__(self, *args: object) -> None:
        super().__exit__(*args)
        self._session.close()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

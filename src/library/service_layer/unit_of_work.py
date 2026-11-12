'''
工作单元：一个业务原子操作一个事务。
进入时开会话并建好仓储，退出时一律回滚未提交的改动，提交必须显式调用 commit()。
proj_id依赖注入
'''

import abc
from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from ..adapters.repository import LibraryRepository, SqlAlchemyLibraryRepository


class AbstractUnitOfWork(abc.ABC):
    library: LibraryRepository

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args) -> None:
        self.rollback()

    @abc.abstractmethod
    def commit(self) -> None: ...

    @abc.abstractmethod
    def rollback(self) -> None: ...


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session_factory: sessionmaker[Session],
                 proj_id: str) -> None:
        self._session_factory = session_factory
        self._proj_id = proj_id

    def __enter__(self) -> Self:
        self._session = self._session_factory()
        self.library = SqlAlchemyLibraryRepository(self._session, self._proj_id)
        return super().__enter__()

    def __exit__(self, *args) -> None:
        # 回滚会让会话里所有对象过期（expire_on_commit=False 对回滚不起作用），
        # 先分离再回滚，返回给调用方的实体才能在会话外继续读取。
        self._session.expunge_all()
        super().__exit__(*args)
        self._session.close()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

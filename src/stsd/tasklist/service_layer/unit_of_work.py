'''工作单元（Unit of Work）：一个业务用例一个事务。

与 ``src/library/service_layer/unit_of_work.py`` 保持同一套约定：

- 进入时从 ``sessionmaker`` 创建会话并建好仓储；
- 退出时先 ``expunge_all`` 再回滚，最后关闭会话，返回给调用方的实体在
  会话关闭后仍可读取；
- 提交必须显式调用 ``commit()``；仓储不 commit、不 rollback。

``cases`` / ``history`` 是任务清单的外部只读端口，和仓储一起放在 UoW 上，
服务函数的签名因此只需要一个上下文参数。
'''

from __future__ import annotations

import abc
from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from stsd.tasklist.adapters.repository import (
    SqlAlchemyTaskListRepository,
    TaskListRepository,
)
from stsd.tasklist.ports import CaseLibraryPort, RunHistoryPort


class AbstractUnitOfWork(abc.ABC):
    tasklists: TaskListRepository
    cases: CaseLibraryPort
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
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        proj_id: str,
        cases: CaseLibraryPort,
        history: RunHistoryPort | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._proj_id = proj_id
        self.cases = cases
        self.history = history

    def __enter__(self) -> Self:
        self._session = self._session_factory()
        self.tasklists = SqlAlchemyTaskListRepository(self._session, self._proj_id)
        return super().__enter__()

    def __exit__(self, *args: object) -> None:
        # 回滚会让会话里所有对象过期，先分离再回滚；
        # 返回给调用方的实体才能在会话外继续读取。
        self._session.expunge_all()
        super().__exit__(*args)
        self._session.close()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

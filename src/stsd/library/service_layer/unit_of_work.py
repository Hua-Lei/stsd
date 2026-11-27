'''用例库工作单元。

一次业务用例一个事务：进入时创建会话与仓储，退出时回滚未提交的改动，
提交必须显式调用 ``commit()``。``files`` 是实现文件内容的存储，和仓储
一起放在工作单元上，服务函数不必额外接收基础设施对象。
'''

from __future__ import annotations

import abc
from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from stsd.library.adapters.repository import (
    LibraryRepository,
    SqlAlchemyLibraryRepository,
)
from stsd.library.ports import ImplementationFileStore
from stsd.shared.events import EventPublisher, NullPublisher


class AbstractUnitOfWork(abc.ABC):
    library: LibraryRepository
    files: ImplementationFileStore

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
        publisher: EventPublisher | None = None,
        *,
        files: ImplementationFileStore,
    ) -> None:
        self._session_factory = session_factory
        self._publisher = publisher or NullPublisher()
        self.files = files

    def __enter__(self) -> Self:
        self._session = self._session_factory()
        self.library = SqlAlchemyLibraryRepository(self._session)
        return super().__enter__()

    def __exit__(self, *args: object) -> None:
        super().__exit__(*args)
        self._session.close()

    def commit(self) -> None:
        events = self._collect_events()
        self._session.commit()
        # 提交成功之后才发布：否则订阅者可能对随后被回滚的事实做出反应。
        for event in events:
            self._publisher.publish(event)

    def rollback(self) -> None:
        # 丢弃本次事务内积累的事件，它们对应的事实并未成立。
        self._collect_events()
        self._session.rollback()

    def _collect_events(self) -> list[object]:
        '''取走会话内各聚合记下的事件。
        '''
        events: list[object] = []
        for obj in self._session:
            pending = getattr(obj, 'events', None)
            if pending:
                events.extend(pending)
                pending.clear()
        return events

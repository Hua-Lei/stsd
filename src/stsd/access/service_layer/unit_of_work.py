'''Access 工作单元。

一次业务用例一个事务：进入时创建会话和仓储，退出时回滚未提交的改动，
提交必须显式调用 ``commit()``。服务层返回的都是读模型，不依赖会话关闭后
的实体状态。事件发布者放在这里，因为事件必须在 ``commit()`` 成功之后才发布。
'''

from __future__ import annotations

import abc
from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from stsd.access.adapters.repository import AccessRepository, SqlAlchemyAccessRepository
from stsd.shared.events import EventPublisher, NullPublisher


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
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        publisher: EventPublisher | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._publisher = publisher or NullPublisher()

    def __enter__(self) -> Self:
        self._session = self._session_factory()
        self.access = SqlAlchemyAccessRepository(self._session)
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

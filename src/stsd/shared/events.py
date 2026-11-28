'''事件发布端口、进程内消息总线，以及跨模块事件载荷。

模块只依赖 ``EventPublisher``；发布发生在发布方的数据提交之后。
'''

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

Handler = Callable[[object], None]

RevisionStatus = Literal['passed', 'failed', 'error', 'not_run']


@dataclass(frozen=True)
class RevisionResult:
    '''一次任务里某条修订的结论。'''

    testpoint_id: str
    revision_ver: int
    status: RevisionStatus
    detail: dict[str, Any]
    bindings: dict[str, str]


@dataclass(frozen=True)
class TaskExecCompleted:
    '''一个任务的全部修订都到终态之后发布一次。'''

    task_id: str
    task_run_id: str
    results: tuple[RevisionResult, ...]


@runtime_checkable
class EventPublisher(Protocol):
    def publish(self, event: object) -> None:
        '''发布一个已经发生的事实。

        在发布方的事务提交之后调用。返回时不保证订阅者已处理完成，也不保证
        处理成功，所以发布方不应依赖它的结果。
        '''
        ...


class NullPublisher:
    '''什么也不做的发布者。

    Access 与用例库目前都没有领域事件，默认装配用它。它也是测试里最省事的
    替身：需要断言事件内容时改用 ``RecordingPublisher``。
    '''

    def publish(self, event: object) -> None:
        return None


class RecordingPublisher:
    '''把事件记在列表里，供测试断言。'''

    def __init__(self) -> None:
        self.events: list[object] = []

    def publish(self, event: object) -> None:
        self.events.append(event)


class MessageBus:
    '''进程内同步总线。

    订阅者抛出异常时只记日志并继续：发布方的事务已经提交，不该因为下游失败
    而被判定为失败。需要“不丢事件”时的下一步是事务性发件箱（事件与业务数据
    同事务落库，提交后派发，失败可重试），而不是换一个总线实现。
    '''

    def __init__(
        self,
        handlers: Mapping[type, Sequence[Handler]] | None = None,
    ) -> None:
        self._handlers: dict[type, list[Handler]] = {
            event_type: list(hs) for event_type, hs in (handlers or {}).items()
        }

    def subscribe(self, event_type: type, handler: Handler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def publish(self, event: object) -> None:
        for handler in self._handlers.get(type(event), ()):
            try:
                handler(event)
            except Exception:
                logger.exception(
                    'event handler %r failed for %r', handler, event
                )

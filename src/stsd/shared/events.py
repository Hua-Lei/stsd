'''事件发布端口与进程内消息总线。

模块只依赖 ``EventPublisher``：它只能宣告“这件事发生了”，不知道谁在监听，
也接触不到处理器注册表。注册表归组装根（``stsd.bootstrap``）持有。

发布时机由工作单元保证：``commit()`` 成功之后才发布，否则订阅者可能对一个
随后被回滚的事实做出反应。``publish`` 不返回任何结果，因此以后改成异步派发
时调用方不需要改动。
'''

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

Handler = Callable[[object], None]


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

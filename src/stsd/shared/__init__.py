'''跨模块共用的最小设施。

这里只放不属于任何业务模块、且被多个模块共同需要的东西（目前是事件发布
端口与消息总线）。业务概念一律归各自模块，不往这里堆。
'''

from stsd.shared.events import EventPublisher, MessageBus, NullPublisher

__all__ = [
    'EventPublisher',
    'MessageBus',
    'NullPublisher',
]

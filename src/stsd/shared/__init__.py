'''跨模块共用的最小设施。

这里只放不属于任何业务模块、且被多个模块共同需要的东西：事件发布端口、
消息总线，以及 docs/contracts/ 里那些跨模块形状。业务概念一律归各自模块，
不往这里堆。
'''

from stsd.shared.events import (
    EventPublisher,
    MessageBus,
    NullPublisher,
    RevisionResult,
    TaskExecCompleted,
)
from stsd.shared.implementation import (
    File,
    Implementation,
    InvalidImplementation,
    Package,
    PytestRequirements,
    PytestRuntimeSpec,
    hash_content,
    package_from_files,
    validate_implementation,
)

__all__ = [
    'EventPublisher',
    'File',
    'Implementation',
    'InvalidImplementation',
    'MessageBus',
    'NullPublisher',
    'Package',
    'PytestRequirements',
    'PytestRuntimeSpec',
    'RevisionResult',
    'TaskExecCompleted',
    'hash_content',
    'package_from_files',
    'validate_implementation',
]

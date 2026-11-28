'''执行器：Job 队列、Worker、沙箱与平台适配器接缝。

执行器不建立领域聚合：队列状态、领取与完成由 ``ExecutionStore`` 的短事务
负责，单条修订的执行由 ``RevisionRunner`` 负责，执行结果只随
``TaskExecCompleted`` 事件交给下游。
'''

from .errors import (
    BindingUnavailable,
    EnvironmentBuildFailed,
    ExecError,
    ExecutionTimeout,
    ImplementationMissing,
    InvalidArgument,
    RevisionNotFound,
    RevisionNotFrozen,
    SandboxBroken,
    TaskNotExecutable,
    TaskNotFound,
)
from .executor import Executor
from .records import (
    PlatformResult,
    QueueEntry,
    RevisionOutcome,
    TaskDetail,
    TaskItem,
)
from .runner import RevisionRunner
from .store import ExecutionStore, exec_queue, metadata

__all__ = [
    'BindingUnavailable',
    'EnvironmentBuildFailed',
    'ExecError',
    'ExecutionStore',
    'ExecutionTimeout',
    'Executor',
    'ImplementationMissing',
    'InvalidArgument',
    'PlatformResult',
    'QueueEntry',
    'RevisionNotFound',
    'RevisionNotFrozen',
    'RevisionOutcome',
    'RevisionRunner',
    'SandboxBroken',
    'TaskDetail',
    'TaskItem',
    'TaskNotExecutable',
    'TaskNotFound',
    'exec_queue',
    'metadata',
]

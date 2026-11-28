'''执行器：Job 队列、Worker、沙箱与平台适配器接缝。

执行器不建立领域聚合：队列状态、领取与完成由 ``ExecutionStore`` 的短事务
负责，单条修订的执行由 ``RevisionRunner`` 负责，执行结果只随
``TaskExecCompleted`` 事件交给下游。

队列表一个任务一行，状态从待领取到执行中到终态。worker 数量固定，每个
循环领取、执行、产出结论；领取带租约，执行期间心跳续租，过期的行重新可
领取。SQLite 第一版是单 worker 轮询。

worker 领到任务后，把修订按环境签名（平台 kind、python 版本、规范化后的
依赖集合）排序，顺序执行。同签名的修订连续，保持当前沙箱复用；签名变化
就重建，不跨任务保活。每条修订新建工作目录和独立进程，单条超时强杀；
环境建不起来时该环境下的修订记 ``not_run``，杀不掉沙箱就丢弃换新。

沙箱端口只管生命周期、文件进出、执行命令和退出码输出，不知道 pytest；
平台适配器知道镜像或解释器、依赖安装、入口命令和 JUnit XML 解析。本地
子进程沙箱用于开发和测试，容器实现可以替换它。
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

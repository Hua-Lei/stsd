'''执行器错误。

用异常类型区分失败原因，不维护错误码字符串目录。调用方按类型捕获；
面向用户的错误映射留给入口层。
'''

from __future__ import annotations


class ExecError(Exception):
    '''执行器错误的基类。'''


class InvalidArgument(ExecError):
    '''参数形状或取值不合法。'''


class TaskNotFound(ExecError):
    '''任务清单不存在，或执行器读不到它。'''

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        super().__init__(f'task {task_id!r} not found')


class TaskNotExecutable(ExecError):
    '''任务当前状态不能执行，例如清单尚未锁定。'''

    def __init__(self, task_id: str, status: str) -> None:
        self.task_id = task_id
        self.status = status
        super().__init__(
            f'task {task_id!r} is not executable (status {status!r})'
        )


class RevisionNotFound(ExecError):
    '''任务引用的修订不存在，或读不到。'''

    def __init__(self, testpoint_id: str, revision_ver: int) -> None:
        self.testpoint_id = testpoint_id
        self.revision_ver = revision_ver
        super().__init__(
            f'revision {revision_ver} of testpoint {testpoint_id!r} '
            f'not found'
        )


class ImplementationMissing(ExecError):
    '''修订没有实现声明，或实现文件取不到。'''

    def __init__(self, testpoint_id: str, revision_ver: int) -> None:
        self.testpoint_id = testpoint_id
        self.revision_ver = revision_ver
        super().__init__(
            f'revision {revision_ver} of testpoint {testpoint_id!r} '
            f'has no implementation'
        )


class RevisionNotFrozen(ExecError):
    '''任务引用了未冻结的修订，执行器不运行它。'''

    def __init__(self, testpoint_id: str, revision_ver: int) -> None:
        self.testpoint_id = testpoint_id
        self.revision_ver = revision_ver
        super().__init__(
            f'revision {revision_ver} of testpoint {testpoint_id!r} '
            f'is not frozen'
        )


class BindingUnavailable(ExecError):
    '''实现声明的绑定名在当前项目配置里没有可用的值。'''


class EnvironmentBuildFailed(ExecError):
    '''沙箱或环境准备失败，该环境下的修订没有执行。'''


class SandboxBroken(ExecError):
    '''沙箱在运行中不可用，需要丢弃重建。'''


class ExecutionTimeout(ExecError):
    '''单条修订执行超时。'''

'''执行器内部传递的数据结构。

这些是排队、执行和事件组装之间传递的普通 DTO，不是领域聚合；没有业务
方法，不变量由 SQL 约束和调用方负责。
'''

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from stsd.shared.implementation import Implementation

QueueStatus = Literal['pending', 'running', 'done', 'failed']
RevisionStatus = Literal['passed', 'failed', 'error', 'not_run']
PlatformStatus = Literal['passed', 'failed', 'error']
RevisionKey = tuple[str, int]


@dataclass(frozen=True)
class EnvironmentSignature:
    '''决定沙箱能否复用的环境签名。'''

    kind: str
    python_version: str
    pip: tuple[str, ...]

    def sort_key(self) -> tuple[str, str, tuple[str, ...]]:
        return (self.kind, self.python_version, self.pip)


@dataclass(frozen=True)
class TaskItem:
    '''任务清单中的一条修订引用，seq 决定展示与结果顺序。'''

    seq: int
    testpoint_id: str
    revision_ver: int
    content_hash: str | None = None

    @property
    def key(self) -> RevisionKey:
        return (self.testpoint_id, self.revision_ver)


@dataclass(frozen=True)
class TaskDetail:
    '''执行器读取任务时需要的清单信息。'''

    task_id: str
    project_id: str
    project_version: str
    status: str
    items: tuple[TaskItem, ...]


@dataclass(frozen=True)
class RevisionDetail:
    '''一条修订的执行所需信息；实现声明不含文件内容。'''

    testpoint_id: str
    revision_ver: int
    project_id: str
    status: str
    implementation: Implementation | None
    testpoint_deleted: bool = False


@dataclass(frozen=True)
class RevisionInput:
    '''交给 Runner 的单条修订执行输入。'''

    testpoint_id: str
    revision_ver: int
    implementation: Implementation
    files: Mapping[str, str]
    bindings: Mapping[str, str]

    @property
    def key(self) -> RevisionKey:
        return (self.testpoint_id, self.revision_ver)


@dataclass(frozen=True)
class PlatformResult:
    '''平台适配器解析出的单条修订结论。'''

    status: PlatformStatus
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RevisionOutcome:
    '''单条修订的最终结论，内部用于组装事件。'''

    testpoint_id: str
    revision_ver: int
    status: RevisionStatus
    detail: dict[str, Any]
    bindings: dict[str, str]
    duration_ms: float = 0.0

    @property
    def key(self) -> RevisionKey:
        return (self.testpoint_id, self.revision_ver)


@dataclass(frozen=True)
class QueueEntry:
    '''队列表的一行；只描述调度状态，不携带执行结果。'''

    task_id: str
    task_run_id: str
    project_id: str
    status: QueueStatus
    worker_id: str | None
    lease_until: datetime | None
    heartbeat_at: datetime | None
    created_by: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    published_at: datetime | None
    last_error: str | None


@dataclass(frozen=True)
class CommandResult:
    '''沙箱里一次命令执行的原始结果。'''

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

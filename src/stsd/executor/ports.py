'''执行器依赖的端口。

Task、用例库、Access 的读取各是一个只读端口，由集成层实现；沙箱和平台
适配器是执行器自己的基础设施接缝。端口定义在这里，具体实现不反向进入
执行器的编排逻辑。
'''

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from stsd.shared.implementation import Implementation

from .records import (
    CommandResult,
    EnvironmentSignature,
    PlatformResult,
    RevisionDetail,
    TaskDetail,
)


class TaskReader(Protocol):
    def get_task(self, task_id: str) -> TaskDetail | None:
        '''读任务清单；不存在或不可读时返回 None。'''
        ...


class TestPointReader(Protocol):
    def get_revision(
        self, testpoint_id: str, revision_ver: int
    ) -> RevisionDetail | None:
        '''读一条修订及其实现声明。'''
        ...

    def get_files(
        self, testpoint_id: str, revision_ver: int
    ) -> Mapping[str, str] | None:
        '''读实现文件内容；声明或文件不存在时返回 None。'''
        ...


class BindingLookup(Protocol):
    def get_web_config(self, project_id: str) -> Mapping[str, Any] | None:
        '''读项目上的绑定配置；项目不存在时返回 None。'''
        ...


class Workspace(Protocol):
    def write_file(self, path: str, content: str) -> None: ...

    def read_file(self, path: str) -> str: ...

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> CommandResult: ...

    def cleanup(self) -> None: ...


class Sandbox(Protocol):
    def write_file(self, path: str, content: str) -> None: ...

    def read_file(self, path: str) -> str: ...

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> CommandResult: ...

    def new_workspace(self, name: str) -> Workspace: ...

    def close(self) -> None: ...


class SandboxFactory(Protocol):
    def create(self, environment: EnvironmentSignature) -> Sandbox:
        '''创建一个能运行该环境的沙箱；建不起来时抛异常。'''
        ...


class PlatformAdapter(Protocol):
    kind: str

    def environment_signature(
        self, implementation: Implementation
    ) -> EnvironmentSignature: ...

    def prepare(
        self, sandbox: Sandbox, implementation: Implementation
    ) -> None:
        '''在沙箱里装好该环境需要的工具和依赖。'''
        ...

    def run(
        self,
        workspace: Workspace,
        implementation: Implementation,
        files: Mapping[str, str],
        bindings: Mapping[str, str],
        timeout: float,
    ) -> PlatformResult:
        '''在独立工作目录里执行一条修订并解析结论。'''
        ...

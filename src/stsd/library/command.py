'''用例库服务层的命令与查询对象。

所有写操作使用 ``...Command`` 语义的命令类；读接口也使用同类请求对象。
需要 ``ProjectVersionLookup`` 的服务函数形状是 ``(uow, dep, command)``，
其余是 ``(uow, command)``。字段只放调用方必须提供的数据，不放仓储、会话
等基础设施对象。
'''

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from stsd.library.domain.model import RevisionDetail
from stsd.shared.implementation import Implementation


# ---------------------------------------------------------------------------
# 写命令
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CreateSection:
    actor_id: str
    project_id: str
    parent_id: str | None
    name: str


@dataclass(frozen=True)
class AddTestPoint:
    actor_id: str
    project_id: str
    section_id: str
    name: str
    proj_ver: str


@dataclass(frozen=True)
class DeleteNode:
    actor_id: str
    node_id: str


@dataclass(frozen=True)
class ReviseTestPoint:
    actor_id: str
    testpoint_id: str
    proj_ver: str
    revision_detail: RevisionDetail


@dataclass(frozen=True)
class SetImplementation:
    '''整包设置草稿修订的实现；files 是包内路径到文件内容。'''

    actor_id: str
    testpoint_id: str
    revision_ver: int
    implementation: Implementation
    files: Mapping[str, str]


@dataclass(frozen=True)
class AuditAndFreeze:
    actor_id: str
    testpoint_id: str
    revision_ver: int


# ---------------------------------------------------------------------------
# 读请求
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GetSectionTree:
    project_id: str
    section_id: str | None = None


@dataclass(frozen=True)
class GetTestPointDetail:
    testpoint_id: str
    revision_ver: int | None = None


@dataclass(frozen=True)
class GetImplementationFiles:
    testpoint_id: str
    revision_ver: int

'''Access 服务层的命令与查询对象。

所有写操作使用 ``...Command`` 语义的命令类；读接口也使用同类请求对象。
Access 没有外部端口，服务函数形状是 ``(uow, command)``。字段只放调用方
必须提供的数据，不放仓储、会话等基础设施对象。
'''

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from stsd.access.domain.model import Document, UserInfo


# ---------------------------------------------------------------------------
# 写命令
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CreateUser:
    actor_id: str
    user_info: UserInfo


@dataclass(frozen=True)
class CreateProject:
    actor_id: str
    project_name: str
    web_config: Mapping[str, Any]


@dataclass(frozen=True)
class AddProjectVersion:
    actor_id: str
    project_id: str
    proj_ver: str
    docs: Sequence[Document]


@dataclass(frozen=True)
class AddUserToProject:
    actor_id: str
    project_id: str
    target_user_id: str


# ---------------------------------------------------------------------------
# 读请求
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GetUserProjects:
    user_id: str


@dataclass(frozen=True)
class GetProject:
    project_id: str


@dataclass(frozen=True)
class GetProjectMembers:
    project_id: str


@dataclass(frozen=True)
class ListProjectVersions:
    project_id: str


@dataclass(frozen=True)
class GetProjectVersion:
    project_id: str
    proj_ver: str

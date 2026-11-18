'''Access 的读模型。
这些对象由服务层在事务内投影出来，调用方可以在会话关闭后继续使用。
'''

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..domain.model import DocumentKind


@dataclass(frozen=True)
class UserView:
    user_id: str
    name: str
    email: str | None


@dataclass(frozen=True)
class ProjectView:
    project_id: str
    name: str
    web_config: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class ProjectMemberView:
    project_id: str
    user_id: str
    name: str
    email: str | None
    added_by: str
    added_at: datetime


@dataclass(frozen=True)
class DocumentView:
    kind: DocumentKind
    text: str


@dataclass(frozen=True)
class ProjectVersionView:
    project_id: str
    proj_ver: str
    docs: tuple[DocumentView, ...]
    created_at: datetime

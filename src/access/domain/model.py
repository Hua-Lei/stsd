'''Access 领域模型。

Access 是平台的基础支撑：它持有用户、项目、项目版本及其文档、项目成员。

'''

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from .errors import InvalidArgument

DocumentKind = Literal['requirements', 'openapi']
DOCUMENT_KINDS: tuple[DocumentKind, ...] = ('requirements', 'openapi')


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class UserInfo:
    '''创建用户时提供的信息。'''

    name: str
    email: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise InvalidArgument('user name must not be empty')
        if self.email is not None and not isinstance(self.email, str):
            raise InvalidArgument('user email must be a string or None')


@dataclass(frozen=True)
class Document:
    '''项目版本附带的一份文档：需求文档或接口文档。'''

    kind: DocumentKind
    text: str

    def __post_init__(self) -> None:
        if self.kind not in DOCUMENT_KINDS:
            raise InvalidArgument(
                f'document kind must be one of {DOCUMENT_KINDS}, '
                f'got {self.kind!r}'
            )
        if not isinstance(self.text, str) or not self.text.strip():
            raise InvalidArgument('document text must not be empty')


@dataclass
class User:
    user_id: str
    name: str
    email: str | None
    created_by: str
    created_at: datetime


@dataclass
class Project:
    project_id: str
    name: str
    web_config: dict[str, Any]
    created_by: str
    created_at: datetime


@dataclass
class ProjectVersion:
    '''项目的一个版本；添加后不可修改，其文档在添加时一次性提供。'''

    project_id: str
    proj_ver: str
    docs: tuple[Document, ...]
    created_by: str
    created_at: datetime


@dataclass
class ProjectMember:
    project_id: str
    user_id: str
    added_by: str
    added_at: datetime

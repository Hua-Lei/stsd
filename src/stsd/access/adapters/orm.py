'''Access 的 SQLAlchemy ORM 映射。

Access 独占 ``users``、``projects``、``project_members``、
``project_versions`` 四张表。其他模块只通过 Access 的读接口取数据，不直接
查询这些表。
'''

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    MetaData,
    String,
    Table,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import clear_mappers, registry

from stsd.access.domain.model import (
    Document,
    Project,
    ProjectMember,
    ProjectVersion,
    User,
)

metadata = MetaData()
mapper_registry = registry(metadata=metadata)


class UTCDateTime(TypeDecorator):
    '''SQLite 不保存时区，读出来补回 UTC，保持领域层使用 aware datetime。'''

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        return value.astimezone(timezone.utc) if value is not None else None

    def process_result_value(self, value: datetime | None, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


class DocumentsJSON(TypeDecorator):
    '''项目版本的文档列表：值对象元组整体存成一列 JSON。'''

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: tuple[Document, ...] | None, dialect):
        return json.dumps(
            [{'kind': doc.kind, 'text': doc.text} for doc in value or ()],
            ensure_ascii=False,
        )

    def process_result_value(self, value: str | None, dialect):
        return tuple(
            Document(doc['kind'], doc['text'])
            for doc in json.loads(value or '[]')
        )


class WebConfigJSON(TypeDecorator):
    '''项目的 Web 配置由调用方定义结构，Access 原样保存为 JSON 对象。'''

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: dict | None, dialect):
        return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)

    def process_result_value(self, value: str | None, dialect):
        return json.loads(value or '{}')


users = Table(
    'users', metadata,
    Column('user_id', String, primary_key=True),
    Column('name', String, nullable=False),
    Column('email', String),
    Column('created_by', String, nullable=False),
    Column('created_at', UTCDateTime, nullable=False),
)

projects = Table(
    'projects', metadata,
    Column('project_id', String, primary_key=True),
    Column('name', String, nullable=False),
    Column('web_config', WebConfigJSON, nullable=False),
    Column('created_by', String, nullable=False),
    Column('created_at', UTCDateTime, nullable=False),
)

project_members = Table(
    'project_members', metadata,
    Column('project_id', String,
           ForeignKey('projects.project_id'), primary_key=True),
    Column('user_id', String,
           ForeignKey('users.user_id'), primary_key=True),
    Column('added_by', String, nullable=False),
    Column('added_at', UTCDateTime, nullable=False),
)

# 项目版本以 (project_id, proj_ver) 标识；同一项目内 proj_ver 唯一。
project_versions = Table(
    'project_versions', metadata,
    Column('project_id', String,
           ForeignKey('projects.project_id'), primary_key=True),
    Column('proj_ver', String, primary_key=True),
    Column('docs', DocumentsJSON, nullable=False),
    Column('created_by', String, nullable=False),
    Column('created_at', UTCDateTime, nullable=False),
)


def start_mappers() -> None:
    mapper_registry.map_imperatively(User, users)
    mapper_registry.map_imperatively(Project, projects)
    mapper_registry.map_imperatively(ProjectMember, project_members)
    mapper_registry.map_imperatively(ProjectVersion, project_versions)


def stop_mappers() -> None:
    clear_mappers()

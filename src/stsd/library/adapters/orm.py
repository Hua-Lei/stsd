'''用例库的 SQLAlchemy ORM 映射。

用例库只持有 ``project_id`` 和 ``proj_ver`` 的值，不复制 Access 的项目或
文档；项目版本是否存在通过 ``ProjectVersionLookup`` 端口确认，因此这里
没有指向 Access 表的外键。

节点使用单表继承：Section 与 TestPoint 共用 ``lib_nodes``，``name`` 列只
属于 Section；测试点的名称在修订里。
'''

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import clear_mappers, registry, relationship

from stsd.library.domain.model import LibNode, Section, TestPoint, TestPointVersion
from stsd.shared.implementation import Implementation

metadata = MetaData()
mapper_registry = registry(metadata=metadata)


class UTCDateTime(TypeDecorator):
    '''SQLite 不保存时区，读出来补回 UTC，保持领域层使用 aware datetime。'''

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        return value.astimezone(UTC) if value is not None else None

    def process_result_value(self, value: datetime | None, dialect):
        return value.replace(tzinfo=UTC) if value is not None else None


class ImplementationJSON(TypeDecorator):
    '''把实现声明序列化成 JSON 存在 TEXT 列里。

    物理列仍是 TEXT；领域层看到的是 ``Implementation`` 对象。旧库里如果
    还有原始的实现字符串，读取时会在这里报 JSON/形状错误。
    '''

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, Implementation):
            raise TypeError('implementation must be an Implementation')
        return json.dumps(
            value.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        )

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, Implementation):
            return value
        if not isinstance(value, str):
            raise TypeError('stored implementation must be JSON text')
        try:
            data = json.loads(value)
        except ValueError as exc:
            raise ValueError(
                'stored implementation is not valid JSON'
            ) from exc
        return Implementation.from_dict(data)


lib_nodes = Table(
    'lib_nodes', metadata,
    Column('node_id', String, primary_key=True),
    Column('kind', String, nullable=False),
    Column('project_id', String, nullable=False, index=True),
    Column('parent_id', String, ForeignKey('lib_nodes.node_id'), index=True),
    Column('name', String),
    Column('is_deleted', Boolean, nullable=False, default=False),
    Column('created_at', UTCDateTime, nullable=False),
    Column('updated_at', UTCDateTime, nullable=False),
    Column('created_by', String, nullable=False),
    Column('updated_by', String, nullable=False),
    CheckConstraint("kind IN ('section', 'testpoint')", name='ck_lib_nodes_kind'),
)

# 修订由 (testpoint_id, revision_ver) 标识；proj_ver 只是说明性信息。
testpoint_revisions = Table(
    'testpoint_revisions', metadata,
    Column('testpoint_id', String,
           ForeignKey('lib_nodes.node_id'), primary_key=True),
    Column('revision_ver', Integer, primary_key=True),
    Column('name', String, nullable=False),
    Column('description', Text, nullable=False),
    Column('implementation', ImplementationJSON),
    Column('proj_ver', String, nullable=False),
    Column('status', String, nullable=False),
    Column('created_at', UTCDateTime, nullable=False),
    Column('created_by', String, nullable=False),
    CheckConstraint("status IN ('draft', 'frozen')",
                    name='ck_testpoint_revisions_status'),
    CheckConstraint('revision_ver >= 1',
                    name='ck_testpoint_revisions_revision_ver'),
)


def start_mappers() -> None:
    '''装配映射。重复调用安全：已装配时直接返回。'''
    if mapper_registry.mappers:
        return
    mapper_registry.map_imperatively(TestPointVersion, testpoint_revisions)

    mapper_registry.map_imperatively(
        LibNode, lib_nodes,
        polymorphic_on=lib_nodes.c.kind,
        # 查询基类时一并加载子类的列（Section.name），否则会话关闭后访问会报错。
        with_polymorphic='*',
        # name 只属于 Section，不能挂到基类上，否则 TestPoint 也会有 name。
        exclude_properties=['name'],
    )
    mapper_registry.map_imperatively(
        Section, inherits=LibNode, polymorphic_identity='section',
        properties={'name': lib_nodes.c.name},
    )
    mapper_registry.map_imperatively(
        TestPoint, inherits=LibNode, polymorphic_identity='testpoint',
        exclude_properties=['name'],
        properties={
            'revisions': relationship(
                TestPointVersion,
                order_by=testpoint_revisions.c.revision_ver,
                cascade='all, delete-orphan',
                lazy='selectin',
            ),
        },
    )


def stop_mappers() -> None:
    clear_mappers()

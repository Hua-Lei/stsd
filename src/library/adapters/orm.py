'''
SQLAlchemy ORM Mapper
'''

import json
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer,
                        MetaData, String, Table, Text, TypeDecorator,
                        UniqueConstraint)
from sqlalchemy.orm import clear_mappers, composite, registry, relationship

from ..domain.model import (Actor, LibNode, Project, ProjectDoc,
                            ProjectVersion, Section, TestPoint,
                            TestPointVersion)

metadata = MetaData()
mapper_registry = registry(metadata=metadata)


class UTCDateTime(TypeDecorator):
    '''SQLite 不保存时区，读出来补回 UTC，保证和领域层的 aware datetime 一致。'''
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        return value.astimezone(timezone.utc) if value is not None else None

    def process_result_value(self, value: datetime | None, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


class DocsJSON(TypeDecorator):
    '''ProjectVersion.docs 是不可变的值对象元组，整体存成一列 JSON。'''
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: tuple[ProjectDoc, ...] | None, dialect):
        return json.dumps([asdict(d) for d in value or ()])

    def process_result_value(self, value: str | None, dialect):
        return tuple(ProjectDoc(**d) for d in json.loads(value or '[]'))


projects = Table(
    'projects', metadata,
    Column('proj_id', String, primary_key=True),
    Column('name', String, nullable=False),
)

project_versions = Table(
    'project_versions', metadata,
    Column('proj_id', String, ForeignKey('projects.proj_id'), primary_key=True),
    Column('proj_version', String, primary_key=True),
    Column('docs', DocsJSON, nullable=False),
)

# Section 和 TestPoint 共用一张表（单表继承），name 只有 Section 用。
lib_nodes = Table(
    'lib_nodes', metadata,
    Column('node_id', String, primary_key=True),
    Column('kind', String, nullable=False),
    Column('proj_id', String, ForeignKey('projects.proj_id'), nullable=False, index=True),
    Column('parent_id', String, ForeignKey('lib_nodes.node_id'), index=True),
    Column('name', String),
    Column('is_deleted', Boolean, nullable=False, default=False),
    Column('created_at', UTCDateTime, nullable=False),
    Column('updated_at', UTCDateTime, nullable=False),
    Column('updated_by_id', String, nullable=False),
    Column('updated_by_name', String, nullable=False),
    Column('updated_by_type', String, nullable=False),
)

testpoint_versions = Table(
    'testpoint_versions', metadata,
    Column('version_id', String, primary_key=True),
    Column('testpoint_id', String, ForeignKey('lib_nodes.node_id'), nullable=False, index=True),
    Column('version_no', String, nullable=False),
    Column('revision_no', Integer, nullable=False),
    Column('name', String, nullable=False),
    Column('desc', Text, nullable=False),
    Column('change_note', Text, nullable=False),
    Column('impl_ref', String),
    Column('created_at', UTCDateTime, nullable=False),
    Column('created_by_id', String, nullable=False),
    Column('created_by_name', String, nullable=False),
    Column('created_by_type', String, nullable=False),
    UniqueConstraint('testpoint_id', 'version_no', 'revision_no'),
)


def start_mappers() -> None:
    mapper_registry.map_imperatively(ProjectVersion, project_versions)
    mapper_registry.map_imperatively(Project, projects, properties={
        'versions': relationship(
            ProjectVersion,
            order_by=project_versions.c.proj_version,
            cascade='all, delete-orphan',
        ),
    })

    mapper_registry.map_imperatively(TestPointVersion, testpoint_versions, properties={
        'created_by': composite(
            Actor,
            testpoint_versions.c.created_by_id,
            testpoint_versions.c.created_by_name,
            testpoint_versions.c.created_by_type,
        ),
    })

    mapper_registry.map_imperatively(
        LibNode, lib_nodes,
        polymorphic_on=lib_nodes.c.kind,
        # 查询基类时一并加载子类的列（Section.name），否则会话关闭后访问会报错。
        with_polymorphic='*',
        properties={
            'updated_by': composite(
                Actor,
                lib_nodes.c.updated_by_id,
                lib_nodes.c.updated_by_name,
                lib_nodes.c.updated_by_type,
            ),
        },
        # name 只属于 Section，不能挂到基类上，否则 TestPoint 也会有 name 属性。
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
            'versions': relationship(
                TestPointVersion,
                order_by=testpoint_versions.c.created_at,
                cascade='all',
                lazy='selectin',  # 聚合查出来就带着版本历史，会话关闭后也能读
            ),
        },
    )


def stop_mappers() -> None:
    clear_mappers()

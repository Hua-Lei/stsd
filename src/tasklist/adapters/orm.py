'''SQLAlchemy ORM 映射。

与 ``src/library/adapters/orm.py`` 保持同一套约定：

- 领域对象仍是普通 dataclass，映射用 ``registry.map_imperatively``；
- 时间列统一用 ``UTCDateTime``，读出时补回 UTC；
- 表结构、外键、唯一约束表达领域不变量；
- ``start_mappers`` / ``stop_mappers`` 由组合根显式调用。

这里没有业务判断：状态迁移、去重、锁定校验都在 ``domain`` / ``service_layer``。
'''

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (Boolean, Column, DateTime, Enum, ForeignKey, Integer,
                        MetaData, String, Table, TypeDecorator, UniqueConstraint)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import clear_mappers, composite, registry, relationship

from ..domain.model import CaseRef, CopyMode, Status, TaskList, TaskListItem

metadata = MetaData()
mapper_registry = registry(metadata=metadata)


def _enum_values(enum_cls) -> list[str]:
    return [member.value for member in enum_cls]


class UTCDateTime(TypeDecorator):
    '''SQLite 不保存时区，读出来补回 UTC，保证和领域层的 aware datetime 一致。'''
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        return value.astimezone(timezone.utc) if value is not None else None

    def process_result_value(self, value: datetime | None, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


tasklists = Table(
    'tasklists', metadata,
    Column('tasklist_id', String, primary_key=True),
    Column('proj_id', String, nullable=False, index=True),
    Column('target_software_release_version', Integer, nullable=False),
    Column('status', Enum(
        Status, values_callable=_enum_values, native_enum=False,
        validate_strings=True, create_constraint=True, name='tasklist_status',
    ), nullable=False),
    Column('rev', Integer, nullable=False, default=0),
    Column('tasklist_title', String),
    Column('content_hash', String),
    Column('created_at', UTCDateTime, nullable=False),
    Column('updated_at', UTCDateTime, nullable=False),
    Column('source_tasklist_id', String),
    Column('copy_mode', Enum(
        CopyMode, values_callable=_enum_values, native_enum=False,
        validate_strings=True, create_constraint=True, name='tasklist_copy_mode',
    ), nullable=True),
)

tasklist_items = Table(
    'tasklist_items', metadata,
    Column('tasklist_id', String,
           ForeignKey('tasklists.tasklist_id', ondelete='CASCADE'),
           primary_key=True),
    # TaskListItem 上有同名的委托属性，映射键加 ref_ 前缀避免冲突；
    # 数据库列名仍是 use_case_id / use_case_version / content_hash。
    Column('use_case_id', String, key='ref_use_case_id', primary_key=True),
    Column('seq', Integer, nullable=False),
    Column('use_case_version', Integer, key='ref_use_case_version',
           nullable=False),
    Column('content_hash', String, key='ref_content_hash', nullable=False),
    Column('pinned', Boolean, nullable=False, default=False),
    UniqueConstraint('tasklist_id', 'seq', name='uq_tasklist_items_seq'),
)


def start_mappers() -> None:
    # 先映射子实体，TaskList 的 relationship 才能解析到它。
    mapper_registry.map_imperatively(
        TaskListItem, tasklist_items,
        properties={
            # CaseRef 是冻结值对象，四个字段作为组合列整体映射。
            'case_ref': composite(
                CaseRef,
                tasklist_items.c.ref_use_case_id,
                tasklist_items.c.ref_use_case_version,
                tasklist_items.c.ref_content_hash,
                tasklist_items.c.pinned,
            ),
        },
    )
    mapper_registry.map_imperatively(
        TaskList, tasklists,
        properties={
            'items': relationship(
                TaskListItem,
                order_by=tasklist_items.c.seq,
                cascade='all, delete-orphan',
                lazy='selectin',  # 聚合查出来就带着条目，会话关闭后也能读
            ),
        },
    )


def stop_mappers() -> None:
    clear_mappers()


def init_db(engine: Engine) -> None:
    '''建表；组合根在启动时调用一次。'''
    metadata.create_all(engine)

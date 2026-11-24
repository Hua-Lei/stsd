"""SQLAlchemy 映射：runs / testpoint_results。

与 tasklist、library 使用同一套 imperative mapping 约定。步骤证据是只读快照，
整体存 JSON；RunRecord 与 TestPointResult 的汇总字段单独列，列表查询不必加载全部步骤。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (Column, DateTime, Enum, Float, ForeignKey,
                        Integer, JSON, MetaData, String, Table, Text,
                        TypeDecorator, UniqueConstraint)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import clear_mappers, registry, relationship

from ..domain.model import (
    RunKind,
    RunRecord,
    RunStatus,
    StepResult,
    TestPointResult,
    TestPointStatus,
)

metadata = MetaData()
mapper_registry = registry(metadata=metadata)


def _enum_values(enum_cls) -> list[str]:
    return [member.value for member in enum_cls]


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        return value.astimezone(timezone.utc) if value is not None else None

    def process_result_value(self, value: datetime | None, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


class StepResultsJSON(TypeDecorator):
    """把 tuple[StepResult] 存成 JSON 列表，读回时还原为值对象。"""

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: tuple[StepResult, ...] | None, dialect):
        if value is None:
            return []
        return [step.to_dict() if isinstance(step, StepResult) else step for step in value]

    def process_result_value(self, value: list[dict[str, Any]] | None, dialect):
        return tuple(StepResult.from_dict(item) for item in (value or []))


runs = Table(
    'runs', metadata,
    Column('run_id', String, primary_key=True),
    Column('proj_id', String, nullable=False, index=True),
    Column('tasklist_id', String, nullable=False, index=True),
    Column('tasklist_rev', Integer, nullable=False),
    Column('tasklist_content_hash', String),
    Column('project_version', String, nullable=False),
    Column('kind', Enum(RunKind, values_callable=_enum_values, native_enum=False,
                        validate_strings=True, create_constraint=True,
                        name='run_kind'), nullable=False),
    Column('status', Enum(RunStatus, values_callable=_enum_values, native_enum=False,
                          validate_strings=True, create_constraint=True,
                          name='run_status'), nullable=False),
    Column('environment_name', String, nullable=False),
    Column('base_url', String, nullable=False),
    Column('timeout_seconds', Float, nullable=False),
    Column('executor_version', String, nullable=False),
    Column('source_run_id', String),
    Column('started_at', UTCDateTime, nullable=False),
    Column('finished_at', UTCDateTime),
    Column('summary', JSON, nullable=False),
    Column('error_message', Text),
)

testpoint_results = Table(
    'testpoint_results', metadata,
    Column('run_id', String, ForeignKey('runs.run_id', ondelete='CASCADE'),
           primary_key=True),
    Column('seq', Integer, primary_key=True),
    Column('testpoint_id', String, nullable=False),
    Column('revision_ver', Integer, nullable=False),
    Column('content_hash', String, nullable=False),
    Column('title', String, nullable=False),
    Column('status', Enum(TestPointStatus, values_callable=_enum_values, native_enum=False,
                          validate_strings=True, create_constraint=True,
                          name='testpoint_status'), nullable=False),
    Column('error_type', String),
    Column('message', Text),
    Column('duration_ms', Float, nullable=False),
    Column('testpoint_snapshot', JSON, nullable=False),
    Column('steps', StepResultsJSON, nullable=False),
    Column('started_at', UTCDateTime, nullable=False),
    Column('finished_at', UTCDateTime, nullable=False),
    UniqueConstraint('run_id', 'testpoint_id', name='uq_testpoint_results_run_testpoint'),
    UniqueConstraint('run_id', 'seq', name='uq_testpoint_results_run_seq'),
)


def start_mappers() -> None:
    """建立 RunRecord / TestPointResult 的 imperative mapping。

    步骤证据以 JSON 整体存入 testpoint_results.steps；列表查询只需 summary。
    """

    global _mappers_started
    if _mappers_started:
        return
    mapper_registry.map_imperatively(TestPointResult, testpoint_results)
    mapper_registry.map_imperatively(
        RunRecord, runs,
        properties={
            'results': relationship(
                TestPointResult,
                order_by=testpoint_results.c.seq,
                cascade='all, delete-orphan',
                lazy='selectin',
            ),
        },
    )
    _mappers_started = True


def stop_mappers() -> None:
    global _mappers_started
    clear_mappers()
    _mappers_started = False


def init_db(engine: Engine) -> None:
    """建表；旧库不会自动迁移，需要删除重建或手工加列。"""

    metadata.create_all(engine)


_mappers_started = False

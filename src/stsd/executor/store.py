'''Job 队列表与调度存储。

这里只保存排队和调度状态，不保存修订级执行结果。执行结论由 Worker 在
内存里收集，随 ``TaskExecCompleted`` 事件交给下游；进程崩溃后租约过期，
重新领取时整个任务重跑。
'''

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Engine,
    MetaData,
    String,
    Table,
    Text,
    TypeDecorator,
    and_,
    or_,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

from .records import QueueEntry

metadata = MetaData()


class UTCDateTime(TypeDecorator):
    '''SQLite 不保存时区，读出来补回 UTC。'''

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        return value.astimezone(UTC) if value is not None else None

    def process_result_value(self, value: datetime | None, dialect):
        return value.replace(tzinfo=UTC) if value is not None else None


exec_queue = Table(
    'exec_queue', metadata,
    Column('task_id', String, primary_key=True),
    Column('task_run_id', String, nullable=False, unique=True),
    Column('project_id', String, nullable=False, index=True),
    Column('status', String, nullable=False, index=True),
    Column('worker_id', String),
    Column('lease_until', UTCDateTime, index=True),
    Column('heartbeat_at', UTCDateTime),
    Column('created_by', String, nullable=False),
    Column('created_at', UTCDateTime, nullable=False),
    Column('started_at', UTCDateTime),
    Column('finished_at', UTCDateTime),
    Column('published_at', UTCDateTime),
    Column('last_error', Text),
    CheckConstraint(
        "status IN ('pending', 'running', 'done', 'failed')",
        name='ck_exec_queue_status',
    ),
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class ExecutionStore:
    '''队列表的读写；每个方法自己开短事务，不跨越执行过程。'''

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_schema(self) -> None:
        metadata.create_all(self._engine)

    def enqueue(
        self,
        *,
        task_id: str,
        task_run_id: str,
        project_id: str,
        created_by: str,
        now: datetime | None = None,
    ) -> QueueEntry:
        '''插入一行待领取任务；同一 task_id 已存在时返回已有行。'''
        current = self.get(task_id)
        if current is not None:
            return current

        created_at = now or utc_now()
        values: dict[str, Any] = {
            'task_id': task_id,
            'task_run_id': task_run_id,
            'project_id': project_id,
            'status': 'pending',
            'created_by': created_by,
            'created_at': created_at,
        }
        try:
            with self._engine.begin() as connection:
                connection.execute(exec_queue.insert().values(**values))
        except IntegrityError:
            current = self.get(task_id)
            if current is None:
                raise
            return current

        entry = self.get(task_id)
        if entry is None:  # pragma: no cover - 插入后必有一行
            raise RuntimeError(f'queue row for {task_id!r} vanished')
        return entry

    def get(self, task_id: str) -> QueueEntry | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(exec_queue).where(exec_queue.c.task_id == task_id)
            ).first()
        return None if row is None else _entry(row._mapping)

    def claim(
        self,
        *,
        worker_id: str,
        lease_seconds: float,
        now: datetime | None = None,
        project_id: str | None = None,
    ) -> QueueEntry | None:
        '''领取一条待执行或租约过期的任务，并写回新租约。'''
        current = now or utc_now()
        lease_until = current + timedelta(seconds=lease_seconds)
        conditions = [
            or_(
                exec_queue.c.status == 'pending',
                and_(
                    exec_queue.c.status == 'running',
                    or_(
                        exec_queue.c.lease_until.is_(None),
                        exec_queue.c.lease_until < current,
                    ),
                ),
            )
        ]
        if project_id is not None:
            conditions.append(exec_queue.c.project_id == project_id)
        claimable = and_(*conditions)

        with self._engine.begin() as connection:
            row = connection.execute(
                select(exec_queue)
                .where(claimable)
                .order_by(exec_queue.c.created_at, exec_queue.c.task_id)
                .limit(1)
            ).first()
            if row is None:
                return None

            mapping = row._mapping
            task_id = mapping['task_id']
            result = connection.execute(
                update(exec_queue)
                .where(exec_queue.c.task_id == task_id, claimable)
                .values(
                    status='running',
                    worker_id=worker_id,
                    lease_until=lease_until,
                    heartbeat_at=current,
                    started_at=mapping['started_at'] or current,
                    finished_at=None,
                    published_at=None,
                    last_error=None,
                )
            )
            if result.rowcount != 1:
                return None

        return self.get(task_id)

    def renew(
        self,
        *,
        task_id: str,
        worker_id: str,
        lease_seconds: float,
        now: datetime | None = None,
    ) -> bool:
        '''续租；任务已被别人领走或不在执行中时返回 False。'''
        current = now or utc_now()
        with self._engine.begin() as connection:
            result = connection.execute(
                update(exec_queue)
                .where(
                    exec_queue.c.task_id == task_id,
                    exec_queue.c.worker_id == worker_id,
                    exec_queue.c.status == 'running',
                )
                .values(
                    lease_until=current + timedelta(seconds=lease_seconds),
                    heartbeat_at=current,
                )
            )
        return result.rowcount == 1

    def mark_done(
        self,
        *,
        task_id: str,
        worker_id: str,
        now: datetime | None = None,
    ) -> bool:
        '''执行和事件都完成之后把任务标为 done，并记录发布时间。'''
        current = now or utc_now()
        with self._engine.begin() as connection:
            result = connection.execute(
                update(exec_queue)
                .where(
                    exec_queue.c.task_id == task_id,
                    exec_queue.c.worker_id == worker_id,
                    exec_queue.c.status == 'running',
                )
                .values(
                    status='done',
                    lease_until=None,
                    heartbeat_at=None,
                    finished_at=current,
                    published_at=current,
                    last_error=None,
                )
            )
        return result.rowcount == 1

    def mark_failed(
        self,
        *,
        task_id: str,
        worker_id: str,
        error: str,
        now: datetime | None = None,
    ) -> bool:
        '''任务级失败；没有可发布的修订结果。'''
        current = now or utc_now()
        with self._engine.begin() as connection:
            result = connection.execute(
                update(exec_queue)
                .where(
                    exec_queue.c.task_id == task_id,
                    exec_queue.c.worker_id == worker_id,
                    exec_queue.c.status == 'running',
                )
                .values(
                    status='failed',
                    lease_until=None,
                    heartbeat_at=None,
                    finished_at=current,
                    published_at=None,
                    last_error=str(error)[:2000],
                )
            )
        return result.rowcount == 1


def _entry(row: Any) -> QueueEntry:
    return QueueEntry(
        task_id=row['task_id'],
        task_run_id=row['task_run_id'],
        project_id=row['project_id'],
        status=row['status'],
        worker_id=row['worker_id'],
        lease_until=row['lease_until'],
        heartbeat_at=row['heartbeat_at'],
        created_by=row['created_by'],
        created_at=row['created_at'],
        started_at=row['started_at'],
        finished_at=row['finished_at'],
        published_at=row['published_at'],
        last_error=row['last_error'],
    )

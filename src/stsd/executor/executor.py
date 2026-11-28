'''执行器编排。

Executor 只做三件事：把任务放进队列、领取任务并跑完、同步试跑一条修订。
队列状态由 ``ExecutionStore`` 负责，单条修订的执行由 ``RevisionRunner``
负责；这里没有领域聚合。
'''

from __future__ import annotations

import logging
import os
import socket
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import uuid4

from stsd.shared.events import (
    EventPublisher,
    RevisionResult,
    TaskExecCompleted,
)

from .errors import (
    BindingUnavailable,
    ExecError,
    ImplementationMissing,
    InvalidArgument,
    RevisionNotFound,
    RevisionNotFrozen,
    TaskNotExecutable,
    TaskNotFound,
)
from .ports import BindingLookup, TaskReader, TestPointReader
from .records import (
    QueueEntry,
    RevisionInput,
    RevisionKey,
    RevisionOutcome,
    TaskDetail,
    TaskItem,
)
from .runner import RevisionRunner
from .store import ExecutionStore, utc_now

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]


class Executor:
    def __init__(
        self,
        *,
        store: ExecutionStore,
        task_reader: TaskReader,
        testpoint_reader: TestPointReader,
        binding_lookup: BindingLookup,
        runner: RevisionRunner,
        publisher: EventPublisher,
        clock: Clock = utc_now,
        worker_id: str | None = None,
        poll_interval: float = 1.0,
        lease_seconds: float = 60.0,
        heartbeat_interval: float | None = None,
        project_id: str | None = None,
    ) -> None:
        self._store = store
        self._task_reader = task_reader
        self._testpoint_reader = testpoint_reader
        self._binding_lookup = binding_lookup
        self._runner = runner
        self._publisher = publisher
        self._clock = clock
        self._worker_id = worker_id or _default_worker_id()
        self._poll_interval = max(poll_interval, 0.01)
        self._lease_seconds = lease_seconds
        self._heartbeat_interval = heartbeat_interval or max(
            0.1, lease_seconds / 3
        )
        self._project_id = project_id
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ 入队
    def exec_task(self, actor_id: str, task_id: str) -> QueueEntry:
        '''把已锁定的任务排入队列，不等它执行。'''
        _require_text(actor_id, 'actor_id')
        _require_text(task_id, 'task_id')
        task = self._task_reader.get_task(task_id)
        if task is None:
            raise TaskNotFound(task_id)
        if (
            self._project_id is not None
            and task.project_id != self._project_id
        ):
            raise TaskNotFound(task_id)
        if task.status != 'LOCKED':
            raise TaskNotExecutable(task_id, task.status)
        return self._store.enqueue(
            task_id=task_id,
            task_run_id=uuid4().hex,
            project_id=task.project_id,
            created_by=actor_id,
            now=self._clock(),
        )

    # ------------------------------------------------------------------ 同步试跑
    def exec_testcase_for_test(
        self, actor_id: str, testpoint_id: str, revision_ver: int
    ) -> RevisionOutcome:
        '''同步试跑一条修订；不入队、不写队列、不发事件。'''
        _require_text(actor_id, 'actor_id')
        _require_text(testpoint_id, 'testpoint_id')
        _require_revision_ver(revision_ver)

        revision = self._testpoint_reader.get_revision(
            testpoint_id, revision_ver
        )
        if revision is None:
            raise RevisionNotFound(testpoint_id, revision_ver)
        implementation = revision.implementation
        if implementation is None:
            raise ImplementationMissing(testpoint_id, revision_ver)
        files = self._testpoint_reader.get_files(
            testpoint_id, revision_ver
        )
        if files is None:
            raise ImplementationMissing(testpoint_id, revision_ver)

        web_config = self._binding_lookup.get_web_config(
            revision.project_id
        )
        try:
            bindings = _resolve_bindings(
                implementation.inputs, web_config
            )
        except BindingUnavailable as exc:
            return RevisionOutcome(
                testpoint_id=testpoint_id,
                revision_ver=revision_ver,
                status='not_run',
                detail=_error_detail(exc),
                bindings={},
            )
        return self._runner.run_one(
            RevisionInput(
                testpoint_id=testpoint_id,
                revision_ver=revision_ver,
                implementation=implementation,
                files=files,
                bindings=bindings,
            )
        )

    # ------------------------------------------------------------------ Worker
    def run_once(self) -> bool:
        '''领取并执行一条任务；没有可领取的任务时返回 False。'''
        entry = self._store.claim(
            worker_id=self._worker_id,
            lease_seconds=self._lease_seconds,
            now=self._clock(),
            project_id=self._project_id,
        )
        if entry is None:
            return False

        keeper = _LeaseKeeper(
            store=self._store,
            task_id=entry.task_id,
            worker_id=self._worker_id,
            lease_seconds=self._lease_seconds,
            interval=self._heartbeat_interval,
            clock=self._clock,
        )
        keeper.start()
        try:
            task = self._task_reader.get_task(entry.task_id)
            if task is None:
                raise TaskNotFound(entry.task_id)
            if task.status != 'LOCKED':
                raise TaskNotExecutable(entry.task_id, task.status)

            outcomes = self._execute_task(task)
            event = _build_event(task, entry.task_run_id, outcomes)
            # 先发布事件，再把队列行标为完成；重复执行是 at-least-once。
            self._publisher.publish(event)
            if not self._store.mark_done(
                task_id=entry.task_id,
                worker_id=self._worker_id,
                now=self._clock(),
            ):
                logger.warning(
                    'task %s finished but its lease was already lost',
                    entry.task_id,
                )
        except Exception as exc:
            logger.exception('execution of task %s failed', entry.task_id)
            try:
                self._store.mark_failed(
                    task_id=entry.task_id,
                    worker_id=self._worker_id,
                    error=f'{type(exc).__name__}: {exc}',
                    now=self._clock(),
                )
            except Exception:
                logger.exception(
                    'failed to mark task %s as failed', entry.task_id
                )
        finally:
            keeper.stop()
        return True

    def start(self) -> None:
        '''启动后台轮询线程；重复调用安全。'''
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name='stsd-executor', daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float | None = None) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                worked = self.run_once()
            except Exception:
                logger.exception('executor loop failed')
                worked = False
            if not worked:
                self._stop_event.wait(self._poll_interval)

    # ------------------------------------------------------------------ 执行
    def _execute_task(self, task: TaskDetail) -> list[RevisionOutcome]:
        web_config = self._binding_lookup.get_web_config(task.project_id)
        outcomes: dict[RevisionKey, RevisionOutcome] = {}
        inputs: list[RevisionInput] = []

        for item in task.items:
            try:
                revision = self._testpoint_reader.get_revision(
                    item.testpoint_id, item.revision_ver
                )
                if revision is None:
                    raise RevisionNotFound(
                        item.testpoint_id, item.revision_ver
                    )
                if revision.status != 'frozen':
                    raise RevisionNotFrozen(
                        item.testpoint_id, item.revision_ver
                    )
                implementation = revision.implementation
                if implementation is None:
                    raise ImplementationMissing(
                        item.testpoint_id, item.revision_ver
                    )
                files = self._testpoint_reader.get_files(
                    item.testpoint_id, item.revision_ver
                )
                if files is None:
                    raise ImplementationMissing(
                        item.testpoint_id, item.revision_ver
                    )
                bindings = _resolve_bindings(
                    implementation.inputs, web_config
                )
            except BindingUnavailable as exc:
                outcomes[item.key] = _not_run_outcome(item, exc)
                continue
            except ExecError as exc:
                outcomes[item.key] = _error_outcome(item, exc)
                continue

            inputs.append(
                RevisionInput(
                    testpoint_id=item.testpoint_id,
                    revision_ver=item.revision_ver,
                    implementation=implementation,
                    files=files,
                    bindings=bindings,
                )
            )

        for outcome in self._runner.run(inputs):
            outcomes[outcome.key] = outcome

        for item in task.items:
            outcomes.setdefault(
                item.key,
                _error_outcome(
                    item,
                    ExecError('execution produced no result for this revision'),
                ),
            )
        return [outcomes[item.key] for item in task.items]


class _LeaseKeeper:
    '''执行期间定期续租，避免长任务被误回收。'''

    def __init__(
        self,
        *,
        store: ExecutionStore,
        task_id: str,
        worker_id: str,
        lease_seconds: float,
        interval: float,
        clock: Clock,
    ) -> None:
        self._store = store
        self._task_id = task_id
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._interval = max(interval, 0.05)
        self._clock = clock
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._loop, name='stsd-executor-lease', daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(1.0, self._interval * 2))

    def _loop(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                if not self._store.renew(
                    task_id=self._task_id,
                    worker_id=self._worker_id,
                    lease_seconds=self._lease_seconds,
                    now=self._clock(),
                ):
                    return
            except Exception:
                logger.warning(
                    'failed to renew lease for task %s',
                    self._task_id,
                    exc_info=True,
                )


def _build_event(
    task: TaskDetail,
    task_run_id: str,
    outcomes: Sequence[RevisionOutcome],
) -> TaskExecCompleted:
    return TaskExecCompleted(
        task_id=task.task_id,
        task_run_id=task_run_id,
        results=tuple(
            RevisionResult(
                testpoint_id=outcome.testpoint_id,
                revision_ver=outcome.revision_ver,
                status=outcome.status,
                detail=dict(outcome.detail),
                bindings=dict(outcome.bindings),
            )
            for outcome in outcomes
        ),
    )


def _resolve_bindings(
    names: Sequence[str],
    web_config: Mapping[str, Any] | None,
) -> dict[str, str]:
    if not isinstance(web_config, Mapping):
        raise BindingUnavailable(
            'project web_config is missing or not a mapping'
        )
    bindings: dict[str, str] = {}
    for name in names:
        value = web_config.get(name)
        if not isinstance(value, str) or not value.strip():
            raise BindingUnavailable(
                f'binding {name!r} is missing from project web_config'
            )
        bindings[name] = value
    return bindings


def _not_run_outcome(
    item: TaskItem, error: Exception
) -> RevisionOutcome:
    return RevisionOutcome(
        testpoint_id=item.testpoint_id,
        revision_ver=item.revision_ver,
        status='not_run',
        detail=_error_detail(error),
        bindings={},
    )


def _error_outcome(
    item: TaskItem, error: Exception
) -> RevisionOutcome:
    return RevisionOutcome(
        testpoint_id=item.testpoint_id,
        revision_ver=item.revision_ver,
        status='error',
        detail=_error_detail(error),
        bindings={},
    )


def _error_detail(error: Exception) -> dict[str, Any]:
    return {
        'reason': str(error),
        'error_type': type(error).__name__,
    }


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidArgument(f'{field} must not be empty')
    return value


def _require_revision_ver(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidArgument('revision_ver must be a positive integer')
    return value


def _default_worker_id() -> str:
    return f'{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}'

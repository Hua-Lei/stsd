'''单条修订的执行逻辑。

Runner 只负责“给定声明、文件、绑定，建沙箱并跑出结论”。它不读数据库、
不写队列、不发事件，队列 Worker 和同步试跑共用这一段。
'''

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Any

from stsd.shared.implementation import Implementation

from .errors import (
    ExecutionTimeout,
    SandboxBroken,
)
from .ordering import group_by_environment
from .ports import (
    PlatformAdapter,
    Sandbox,
    SandboxFactory,
)
from .records import (
    EnvironmentSignature,
    RevisionInput,
    RevisionKey,
    RevisionOutcome,
)

logger = logging.getLogger(__name__)


class RevisionRunner:
    def __init__(
        self,
        sandbox_factory: SandboxFactory,
        platform: PlatformAdapter,
        *,
        revision_timeout: float = 300.0,
    ) -> None:
        self._sandbox_factory = sandbox_factory
        self._platform = platform
        self._revision_timeout = revision_timeout

    def run(
        self, inputs: Sequence[RevisionInput]
    ) -> list[RevisionOutcome]:
        '''按环境签名排序执行，返回与输入同序的结论列表。'''
        if not inputs:
            return []

        outcomes: dict[RevisionKey, RevisionOutcome] = {}
        for signature, group in group_by_environment(
            inputs, self._platform
        ):
            self._run_group(signature, group, outcomes)
        return [outcomes[item.key] for item in inputs]

    def run_one(self, item: RevisionInput) -> RevisionOutcome:
        return self.run([item])[0]

    # ------------------------------------------------------------------ 分组
    def _run_group(
        self,
        signature: EnvironmentSignature,
        group: list[RevisionInput],
        outcomes: dict[RevisionKey, RevisionOutcome],
    ) -> None:
        try:
            sandbox = self._create_prepared(
                signature, group[0].implementation
            )
        except Exception as exc:  # noqa: BLE001 - 建不起来一律记 not_run
            self._mark_not_run(group, outcomes, exc)
            return

        try:
            for index, item in enumerate(group):
                if sandbox is None:
                    try:
                        sandbox = self._create_prepared(
                            signature, item.implementation
                        )
                    except Exception as exc:  # noqa: BLE001
                        self._mark_not_run(
                            group[index:], outcomes, exc
                        )
                        return
                if not self._run_one(sandbox, item, outcomes):
                    self._close(sandbox)
                    sandbox = None
        finally:
            if sandbox is not None:
                self._close(sandbox)

    def _create_prepared(
        self,
        signature: EnvironmentSignature,
        implementation: Implementation,
    ) -> Sandbox:
        sandbox = self._sandbox_factory.create(signature)
        try:
            self._platform.prepare(sandbox, implementation)
        except Exception:
            self._close(sandbox)
            raise
        return sandbox

    # ------------------------------------------------------------------ 单条
    def _run_one(
        self,
        sandbox: Sandbox,
        item: RevisionInput,
        outcomes: dict[RevisionKey, RevisionOutcome],
    ) -> bool:
        '''返回沙箱是否还能继续使用。'''
        started = time.perf_counter()
        workspace = None
        try:
            workspace = sandbox.new_workspace(
                f'{item.testpoint_id}-{item.revision_ver}'
            )
            result = self._platform.run(
                workspace,
                item.implementation,
                item.files,
                item.bindings,
                self._revision_timeout,
            )
            outcomes[item.key] = RevisionOutcome(
                testpoint_id=item.testpoint_id,
                revision_ver=item.revision_ver,
                status=result.status,
                detail=dict(result.detail),
                bindings=dict(item.bindings),
                duration_ms=_elapsed_ms(started),
            )
        except SandboxBroken as exc:
            outcomes[item.key] = _error_outcome(item, exc, started)
            return False
        except ExecutionTimeout as exc:
            outcomes[item.key] = _error_outcome(item, exc, started)
        except Exception as exc:  # noqa: BLE001 - 平台错误也要落成结论
            outcomes[item.key] = _error_outcome(item, exc, started)
        finally:
            if workspace is not None:
                try:
                    workspace.cleanup()
                except Exception:
                    logger.warning(
                        'failed to clean workspace for %s/%s',
                        item.testpoint_id,
                        item.revision_ver,
                        exc_info=True,
                    )
        return True

    def _mark_not_run(
        self,
        group: Sequence[RevisionInput],
        outcomes: dict[RevisionKey, RevisionOutcome],
        error: Exception,
    ) -> None:
        detail = _error_detail(error)
        for item in group:
            outcomes[item.key] = RevisionOutcome(
                testpoint_id=item.testpoint_id,
                revision_ver=item.revision_ver,
                status='not_run',
                detail=dict(detail),
                bindings=dict(item.bindings),
            )

    def _close(self, sandbox: Sandbox) -> None:
        try:
            sandbox.close()
        except Exception:
            logger.warning('failed to close sandbox', exc_info=True)


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def _error_detail(error: Exception) -> dict[str, Any]:
    return {
        'reason': str(error),
        'error_type': type(error).__name__,
    }


def _error_outcome(
    item: RevisionInput, error: Exception, started: float
) -> RevisionOutcome:
    return RevisionOutcome(
        testpoint_id=item.testpoint_id,
        revision_ver=item.revision_ver,
        status='error',
        detail=_error_detail(error),
        bindings=dict(item.bindings),
        duration_ms=_elapsed_ms(started),
    )

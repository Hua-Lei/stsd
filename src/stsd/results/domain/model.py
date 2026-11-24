"""测试结果领域模型：RunRecord / TestPointResult / StepResult。

约束：
- RunRecord 是一次执行，不是任务清单；同一清单可以有多次 RunRecord；
- 结果写入后不可修改；用例内容快照跟随结果保存；
- StepResult 只在步骤层表达 skipped，不制造用例级 skipped。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from stsd.shared.execution_contract import (
    AssertionRecord,
    TestPointOutcome,
    ExecutionOutcome,
    RequestRecord,
    ResponseRecord,
    StepOutcome,
)


class RunStatus(StrEnum):
    """一次执行的生命周期；FAILED 既可能是断言失败，也可能是执行错误。"""

    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class RunKind(StrEnum):
    """执行用途，便于基线/变体/回归结果分组统计。"""

    MANUAL = "MANUAL"
    BASELINE = "BASELINE"
    VARIANT = "VARIANT"
    REGRESSION = "REGRESSION"
    SUPPLEMENT = "SUPPLEMENT"


class TestPointStatus(StrEnum):
    """用例级只有三类结论；跳过只在步骤层统计。"""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class StepStatus(StrEnum):
    """步骤级状态；SKIPPED 表示前一步未通过，不能算通过。"""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


def utc_now() -> datetime:
    """结果时间统一使用 aware UTC。"""

    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds") if value else None


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _request_dict(request: RequestRecord | None) -> dict[str, Any] | None:
    """把执行器 DTO 转成可 JSON 存储的请求快照。"""

    if request is None:
        return None
    return {
        "method": request.method,
        "url": request.url,
        "headers": dict(request.headers),
        "query": dict(request.query),
        "body": request.body,
    }


def _response_dict(response: ResponseRecord | None) -> dict[str, Any] | None:
    """把执行器 DTO 转成可 JSON 存储的响应快照。"""

    if response is None:
        return None
    return {
        "status": response.status,
        "headers": dict(response.headers),
        "body": response.body,
        "elapsed_ms": response.elapsed_ms,
    }


def _assertion_dict(assertion: AssertionRecord) -> dict[str, Any]:
    """断言结果直接落 JSON，保留 expected/actual/missing 三者的区别。"""

    return {
        "source": assertion.source,
        "op": assertion.op,
        "path": assertion.path,
        "expected": assertion.expected,
        "actual": assertion.actual,
        "actual_missing": assertion.actual_missing,
        "passed": assertion.passed,
        "message": assertion.message,
    }


@dataclass(frozen=True)
class StepResult:
    """步骤级不可变证据：请求、响应、断言、提取变量和错误类型。"""

    index: int
    name: str
    status: StepStatus
    error_type: str | None = None
    message: str = ""
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    assertions: tuple[dict[str, Any], ...] = ()
    extracted: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

    @classmethod
    def from_outcome(cls, outcome: StepOutcome) -> "StepResult":
        return cls(
            index=outcome.index,
            name=outcome.name,
            status=StepStatus(outcome.status),
            error_type=outcome.error_type,
            message=outcome.message,
            request=_request_dict(outcome.request),
            response=_response_dict(outcome.response),
            assertions=tuple(_assertion_dict(item) for item in outcome.assertions),
            extracted=dict(outcome.extracted),
            duration_ms=outcome.duration_ms,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StepResult":
        return cls(
            index=int(data["index"]),
            name=str(data["name"]),
            status=StepStatus(data["status"]),
            error_type=data.get("error_type"),
            message=data.get("message", ""),
            request=data.get("request"),
            response=data.get("response"),
            assertions=tuple(data.get("assertions", ())),
            extracted=dict(data.get("extracted", {})),
            duration_ms=float(data.get("duration_ms", 0.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "status": self.status.value,
            "error_type": self.error_type,
            "message": self.message,
            "request": self.request,
            "response": self.response,
            "assertions": list(self.assertions),
            "extracted": self.extracted,
            "duration_ms": self.duration_ms,
        }


@dataclass
class TestPointResult:
    """一条用例在一次 RunRecord 中的不可变结果。

    ``testpoint_snapshot`` 是执行时的用例正文快照；之后用例库修改也不影响历史。
    """

    seq: int
    testpoint_id: str
    revision_ver: int
    content_hash: str
    title: str
    status: TestPointStatus
    error_type: str | None
    message: str
    steps: tuple[StepResult, ...]
    testpoint_snapshot: Any
    duration_ms: float
    started_at: datetime
    finished_at: datetime

    @classmethod
    def from_outcome(
        cls,
        outcome: TestPointOutcome,
        snapshot: Any,
    ) -> "TestPointResult":
        """把执行器 DTO 映射成领域结果，并保留执行时的用例快照。"""

        return cls(
            seq=outcome.seq,
            testpoint_id=outcome.testpoint_id,
            revision_ver=outcome.revision_ver,
            content_hash=outcome.content_hash,
            title=outcome.title,
            status=TestPointStatus(outcome.status),
            error_type=outcome.error_type,
            message=outcome.message,
            steps=tuple(StepResult.from_outcome(step) for step in outcome.steps),
            testpoint_snapshot=snapshot,
            duration_ms=outcome.duration_ms,
            started_at=outcome.started_at,
            finished_at=outcome.finished_at,
        )

    @property
    def passed(self) -> bool:
        return self.status is TestPointStatus.PASSED

    def to_dict(self) -> dict[str, Any]:
        """完整结果视图，包含逐步骤证据和用例快照。"""

        return {
            "seq": self.seq,
            "testpoint_id": self.testpoint_id,
            "revision_ver": self.revision_ver,
            "content_hash": self.content_hash,
            "title": self.title,
            "status": self.status.value,
            "error_type": self.error_type,
            "message": self.message,
            "steps": [step.to_dict() for step in self.steps],
            "testpoint_snapshot": self.testpoint_snapshot,
            "duration_ms": self.duration_ms,
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
        }


@dataclass
class RunRecord:
    """一次执行记录（聚合根）。

    RunRecord 引用锁定清单的 id / rev / content_hash，并保存目标软件版本、
    执行环境和逐条 TestPointResult；同一 TaskList 可以产生多个 RunRecord。
    """

    run_id: str
    proj_id: str
    tasklist_id: str
    tasklist_rev: int
    tasklist_content_hash: str | None
    project_version: str
    kind: RunKind
    status: RunStatus
    environment_name: str
    base_url: str
    timeout_seconds: float
    executor_version: str
    source_run_id: str | None
    started_at: datetime
    finished_at: datetime | None
    summary: dict[str, Any]
    error_message: str | None = None
    results: list[TestPointResult] = field(default_factory=list)

    # ------------------------------------------------------------------ 工厂
    @classmethod
    def create(
        cls,
        *,
        proj_id: str,
        tasklist_id: str,
        tasklist_rev: int,
        tasklist_content_hash: str | None,
        project_version: str,
        kind: RunKind,
        environment_name: str,
        base_url: str,
        timeout_seconds: float,
        executor_version: str,
        source_run_id: str | None = None,
    ) -> "RunRecord":
        """创建一个 RUNNING 状态的 RunRecord；结果由 complete/abort 写入。"""

        return cls(
            run_id=_new_id("run"),
            proj_id=proj_id,
            tasklist_id=tasklist_id,
            tasklist_rev=tasklist_rev,
            tasklist_content_hash=tasklist_content_hash,
            project_version=project_version,
            kind=kind,
            status=RunStatus.RUNNING,
            environment_name=environment_name,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            executor_version=executor_version,
            source_run_id=source_run_id,
            started_at=utc_now(),
            finished_at=None,
            summary={"total": 0, "passed": 0, "failed": 0, "error": 0,
                     "skipped_steps": 0, "duration_ms": 0.0},
        )

    # ------------------------------------------------------------------ 行为
    def complete(self, results: list[TestPointResult]) -> None:
        """写入完整结果并结束 RunRecord；任一条 failed/error 即整次 FAILED。"""

        if self.status is not RunStatus.RUNNING:
            raise ValueError(f"RunRecord {self.run_id} 已结束，不能重复写入")
        self._validate_results(results)
        self.results = list(results)
        self.finished_at = utc_now()
        self.summary = self._summarize(results)
        self.status = (
            RunStatus.SUCCEEDED
            if self.summary["failed"] == 0 and self.summary["error"] == 0
            else RunStatus.FAILED
        )

    def abort(self, message: str) -> None:
        """执行器整体失败或结果不匹配时结束 RunRecord，保留 error_message。"""

        if self.status is not RunStatus.RUNNING:
            raise ValueError(f"RunRecord {self.run_id} 已结束，不能中止")
        self.status = RunStatus.ABORTED
        self.error_message = message
        self.finished_at = utc_now()

    @staticmethod
    def _validate_results(results: list[TestPointResult]) -> None:
        """同一 RunRecord 内用例 id 和 seq 都必须唯一。"""

        ids = [item.testpoint_id for item in results]
        seqs = [item.seq for item in results]
        if len(ids) != len(set(ids)):
            raise ValueError("同一 RunRecord 中不能出现重复 testpoint_id")
        if len(seqs) != len(set(seqs)):
            raise ValueError("同一 RunRecord 中不能出现重复 seq")

    @staticmethod
    def _summarize(results: list[TestPointResult]) -> dict[str, Any]:
        """汇总计数；skipped 只统计步骤级，不产生用例级 skipped。"""

        return {
            "total": len(results),
            "passed": sum(1 for item in results if item.status is TestPointStatus.PASSED),
            "failed": sum(1 for item in results if item.status is TestPointStatus.FAILED),
            "error": sum(1 for item in results if item.status is TestPointStatus.ERROR),
            "skipped_steps": sum(
                1
                for item in results
                for step in item.steps
                if step.status is StepStatus.SKIPPED
            ),
            "duration_ms": round(sum(item.duration_ms for item in results), 1),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "proj_id": self.proj_id,
            "tasklist_id": self.tasklist_id,
            "tasklist_rev": self.tasklist_rev,
            "tasklist_content_hash": self.tasklist_content_hash,
            "project_version": self.project_version,
            "kind": self.kind.value,
            "status": self.status.value,
            "environment_name": self.environment_name,
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "executor_version": self.executor_version,
            "source_run_id": self.source_run_id,
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            "summary": dict(self.summary),
            "error_message": self.error_message,
        }

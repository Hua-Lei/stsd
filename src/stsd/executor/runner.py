"""HTTP 执行器：逐条用例、逐步请求、确定性断言。

执行器不知道任务清单、数据库或结果报告；它只接收 ``ExecutionPlan``，
返回 ``ExecutionOutcome``。存储和展示由 results 模块负责。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import httpx
from pydantic import ValidationError

from stsd.shared.execution_contract import (
    AssertionRecord,
    TestPointOutcome,
    Environment,
    ExecutionTestPoint,
    ExecutionOutcome,
    ExecutionPlan,
    RequestRecord,
    ResponseRecord,
    StepOutcome,
)

from .assertions import judge
from .case import Step, TestCase
from .errors import ExtractError, RenderError
from .jsonpath import MISSING, get as jsonpath_get
from .render import bind


def utc_now() -> datetime:
    """执行结果统一使用 aware UTC 时间。"""

    return datetime.now(timezone.utc)


class CaseExecutor:
    """用外部注入的 ``httpx.Client`` 执行一组用例。

    执行器只负责执行：不读数据库、不创建 RunRecord、不写结果。
    """

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def execute(self, plan: ExecutionPlan) -> ExecutionOutcome:
        """按计划顺序执行所有用例；单条用例失败不影响其他用例。"""

        started = utc_now()
        cases = tuple(
            self._run_case(case, plan.environment) for case in plan.testpoints
        )
        return ExecutionOutcome(
            status="completed",
            started_at=started,
            finished_at=utc_now(),
            testpoints=cases,
        )

    # ------------------------------------------------------------------ 用例
    def _run_case(self, case: ExecutionTestPoint, environment: Environment) -> TestPointOutcome:
        """执行一条用例。

        步骤状态遵循快速失败：前一步未通过，后续步骤记为 skipped；
        用例状态由步骤集合归并成 passed / failed / error。
        """

        started = utc_now()
        try:
            test_case = TestCase.model_validate(case.payload)
        except ValidationError as exc:
            # 用例格式错误属于执行错误，但不应中断整批执行。
            return TestPointOutcome(
                seq=case.seq,
                testpoint_id=case.testpoint_id,
                revision_ver=case.revision_ver,
                content_hash=case.content_hash,
                title=case.title,
                status="error",
                error_type="invalid_case",
                message=str(exc),
                steps=(),
                duration_ms=0.0,
                started_at=started,
                finished_at=utc_now(),
            )

        variables = dict(environment.variables)
        steps: list[StepOutcome] = []
        for index, step in enumerate(test_case.steps, 1):
            if steps and steps[-1].status != "passed":
                steps.append(
                    StepOutcome(
                        index=index,
                        name=step.name,
                        status="skipped",
                        message="前一步未通过",
                    )
                )
                continue
            result = self._run_step(index, step, variables, environment)
            variables.update(result.extracted)
            steps.append(result)

        # 用例级只保留三类状态；skipped 只出现在步骤级。
        statuses = {step.status for step in steps}
        if "error" in statuses:
            status = "error"
        elif "failed" in statuses:
            status = "failed"
        else:
            status = "passed"

        first_bad = next(
            (step for step in steps if step.status in ("error", "failed")), None
        )
        return TestPointOutcome(
            seq=case.seq,
            testpoint_id=case.testpoint_id,
            revision_ver=case.revision_ver,
            content_hash=case.content_hash,
            title=test_case.title,
            status=status,
            error_type=first_bad.error_type if first_bad else None,
            message=first_bad.message if first_bad else "",
            steps=tuple(steps),
            duration_ms=_elapsed_ms(started),
            started_at=started,
            finished_at=utc_now(),
        )

    # ------------------------------------------------------------------ 步骤
    def _run_step(
        self, index: int, step: Step, variables: dict[str, Any], environment: Environment
    ) -> StepOutcome:
        """执行一个步骤，并把所有运行时错误转换成 StepOutcome.error。"""

        started = time.perf_counter()
        request: RequestRecord | None = None
        try:
            bound = bind(step, variables)
            # 环境 headers 先放，用例 headers 可以覆盖；变量绑定后的 query/body 原样发出。
            headers = {**environment.headers, **bound.headers}
            url = _join_url(environment.base_url, bound.path)
            request = RequestRecord(
                method=bound.method,
                url=url,
                headers=headers,
                query=bound.query,
                body=bound.body,
            )
            response = self._send(request, environment.timeout_seconds)
            assertions = judge(bound.assertions, response)
            failed = [item for item in assertions if not item.passed]
            if failed:
                # 断言失败是正常结论，不是异常；保留证据供结果模块展示。
                return StepOutcome(
                    index=index,
                    name=step.name,
                    status="failed",
                    error_type="assertion_failed",
                    message="; ".join(item.message for item in failed),
                    request=request,
                    response=response,
                    assertions=assertions,
                    duration_ms=_elapsed_ms(started),
                )

            extracted = _extract(step.extract, response)
            return StepOutcome(
                index=index,
                name=step.name,
                status="passed",
                request=request,
                response=response,
                assertions=assertions,
                extracted=extracted,
                duration_ms=_elapsed_ms(started),
            )
        except RenderError as exc:
            return _failed_step(index, step, "render_error", str(exc), request, started)
        except httpx.TimeoutException as exc:
            return _failed_step(index, step, "timeout", str(exc), request, started)
        except httpx.HTTPError as exc:
            return _failed_step(index, step, "transport_error", str(exc), request, started)
        except ExtractError as exc:
            return _failed_step(index, step, "extract_error", str(exc), request, started)
        except Exception as exc:  # 执行器兜底：单条用例失败不打断整批
            return _failed_step(index, step, "executor_error", str(exc), request, started)

    def _send(self, request: RequestRecord, timeout: float) -> ResponseRecord:
        """发送请求并记录状态、头、body 和耗时；HTTP 错误交给上层分类。"""

        started = time.perf_counter()
        response = self.client.request(
            request.method,
            request.url,
            headers=request.headers,
            params=request.query,
            json=request.body,
            timeout=timeout,
        )
        elapsed = (time.perf_counter() - started) * 1000
        try:
            body = response.json()
        except ValueError:
            body = response.text
        return ResponseRecord(
            status=response.status_code,
            headers={key.lower(): value for key, value in response.headers.items()},
            body=body,
            elapsed_ms=round(elapsed, 1),
        )


def _extract(rules: dict[str, str], response: ResponseRecord) -> dict[str, Any]:
    """按 JSONPath 提取变量；字段不存在是执行错误，不提取 None。"""

    values: dict[str, Any] = {}
    for name, path in rules.items():
        value = jsonpath_get(response.body, path)
        if value is MISSING:
            raise ExtractError(f"从 {path} 提取 {name} 失败：字段不存在")
        values[name] = value
    return values


def _failed_step(
    index: int,
    step: Step,
    error_type: str,
    message: str,
    request: RequestRecord | None,
    started: float,
) -> StepOutcome:
    """构造 error 步骤；保留已发出的 request，便于排查网络问题。"""

    return StepOutcome(
        index=index,
        name=step.name,
        status="error",
        error_type=error_type,
        message=message,
        request=request,
        duration_ms=_elapsed_ms(started),
    )


def _join_url(base_url: str, path: str) -> str:
    """拼出完整 URL；base_url 可以带路径前缀，path 可以带前导斜杠。"""

    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _elapsed_ms(started: datetime | float) -> float:
    """同时支持用例级（datetime）和步骤级（perf_counter）计时。"""

    if isinstance(started, datetime):
        return round((utc_now() - started).total_seconds() * 1000, 1)
    return round((time.perf_counter() - started) * 1000, 1)

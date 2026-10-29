"""执行器：解释用例这门小语言。

每条用例有自己的变量环境；每一步是一条快速失败的流水线：
  绑定变量 → 发送请求 → 断言 → 提取变量

绑定、发送、提取失败属于运行时错误（用例没能跑完），走 StepError 异常；
断言不通过是正常的结论，由断言结果算出。
无论哪种情况，已经产生的请求、响应、断言结果都保留在 StepResult 里，供分析使用。
"""
import time
from typing import Any

import httpx

from demo.executor.assertions import describe, judge
from demo.executor.errors import ExtractError, StepError, TransportError
from demo.executor.render import bind
from demo.models import CaseResult, RenderedRequest, ResponseRecord, Step, StepResult, TestCase
from demo.utils import jsonpath
from demo.utils.jsonpath import MISSING


class CaseExecutor:
    def __init__(self, client: httpx.Client):
        # 客户端由外部注入：CLI 传真实的 httpx.Client，评估时传进程内的 TestClient
        self.client = client

    def run_all(self, cases: list[TestCase]) -> list[CaseResult]:
        return [self.run_case(case) for case in cases]

    def run_case(self, case: TestCase) -> CaseResult:
        variables: dict[str, Any] = {}
        steps: list[StepResult] = []
        for i, step in enumerate(case.steps, 1):
            if steps and steps[-1].status != "passed":
                steps.append(StepResult(index=i, name=step.name, status="skipped"))
                continue
            result = self._run_step(i, step, variables)
            variables.update(result.extracted)
            steps.append(result)

        statuses = {s.status for s in steps}
        status = "error" if "error" in statuses else "failed" if "failed" in statuses else "passed"
        return CaseResult(case_id=case.id, title=case.title, status=status, steps=steps, variables=variables)

    def _run_step(self, index: int, step: Step, variables: dict[str, Any]) -> StepResult:
        request = response = None
        assertions, extracted = [], {}
        try:
            bound = bind(step, variables)
            request = bound.request
            response = self._send(request)
            assertions = judge(bound.assertions, response)
            # 先断言后提取：状态码不对时，报告“期望 201 实际 500”比“取不到 id”更有用
            if all(a.passed for a in assertions):
                extracted = extract(step.extract, response)
        except StepError as e:
            return StepResult(index=index, name=step.name, status="error", error_type=e.error_type,
                              message=str(e), request=request, response=response, assertions=assertions)

        failed = [a for a in assertions if not a.passed]
        if failed:
            return StepResult(index=index, name=step.name, status="failed", error_type="assertion_failed",
                              message="; ".join(describe(a) for a in failed),
                              request=request, response=response, assertions=assertions)
        return StepResult(index=index, name=step.name, status="passed",
                          request=request, response=response, assertions=assertions, extracted=extracted)

    def _send(self, req: RenderedRequest) -> ResponseRecord:
        start = time.perf_counter()
        try:
            resp = self.client.request(
                req.method, req.path, headers=req.headers, params=req.query,
                json=req.body,  # None 时 httpx 不发送 body
            )
        except httpx.HTTPError as e:
            raise TransportError(f"{type(e).__name__}: {e}") from e
        elapsed = (time.perf_counter() - start) * 1000
        try:
            body = resp.json()
        except ValueError:
            body = resp.text
        return ResponseRecord(
            status=resp.status_code,
            headers={k.lower(): v for k, v in resp.headers.items()},
            body=body,
            elapsed_ms=round(elapsed, 1),
        )


def extract(rules: dict[str, str], response: ResponseRecord) -> dict[str, Any]:
    values = {}
    for name, path in rules.items():
        value = jsonpath.get(response.body, path)
        if value is MISSING:
            raise ExtractError(f"want 从 {path} 提取 {name}, result 字段不存在")
        values[name] = value
    return values

"""人类读模型：RunRecord 汇总、用例列表、证据详情、RunRecord 对比。"""

from __future__ import annotations

from typing import Any

from ..domain.model import TestPointResult, RunRecord, StepResult


def run_summary(run: RunRecord) -> dict[str, Any]:
    """RunRecord 元数据 + 汇总，不含逐条结果。"""

    return run.to_dict()


def case_summary(case: TestPointResult) -> dict[str, Any]:
    """用例列表行：状态、首个失败步骤、耗时。"""

    first_bad = _first_bad_step(case)
    return {
        "seq": case.seq,
        "testpoint_id": case.testpoint_id,
        "revision_ver": case.revision_ver,
        "content_hash": case.content_hash,
        "title": case.title,
        "status": case.status.value,
        "error_type": case.error_type,
        "message": case.message,
        "duration_ms": case.duration_ms,
        "failed_step": _step_brief(first_bad) if first_bad else None,
    }


def run_detail(run: RunRecord, *, include_steps: bool = True) -> dict[str, Any]:
    """人类结果页：默认带逐步骤证据和测试点快照。"""

    testpoints = [
        (
            {**case_summary(case), "steps": [step.to_dict() for step in case.steps],
             "testpoint_snapshot": case.testpoint_snapshot}
            if include_steps
            else case_summary(case)
        )
        for case in run.results
    ]
    return {**run_summary(run), "testpoints": testpoints}


def run_list_item(run: RunRecord) -> dict[str, Any]:
    return run_summary(run)


def compare_runs(base: RunRecord, variant: RunRecord) -> dict[str, Any]:
    """按 testpoint_id 对齐两次 RunRecord，比较状态和修订版本。"""

    base_map = {case.testpoint_id: case for case in base.results}
    variant_map = {case.testpoint_id: case for case in variant.results}
    ids = list(dict.fromkeys([*base_map, *variant_map]))
    rows = []
    for testpoint_id in ids:
        left = base_map.get(testpoint_id)
        right = variant_map.get(testpoint_id)
        rows.append({
            "testpoint_id": testpoint_id,
            "base_status": left.status.value if left else None,
            "variant_status": right.status.value if right else None,
            "base_version": left.revision_ver if left else None,
            "variant_version": right.revision_ver if right else None,
            "changed": (
                (left.status if left else None) != (right.status if right else None)
                or (left.revision_ver if left else None)
                != (right.revision_ver if right else None)
            ),
            "base_error_type": left.error_type if left else None,
            "variant_error_type": right.error_type if right else None,
        })
    return {
        "base_run_id": base.run_id,
        "variant_run_id": variant.run_id,
        "base_summary": dict(base.summary),
        "variant_summary": dict(variant.summary),
        "testpoints": rows,
    }


def _first_bad_step(case: TestPointResult) -> StepResult | None:
    return next(
        (step for step in case.steps if step.status.value in ("failed", "error")),
        None,
    )


def _step_brief(step: StepResult) -> dict[str, Any]:
    return {
        "index": step.index,
        "name": step.name,
        "status": step.status.value,
        "error_type": step.error_type,
        "message": step.message,
    }

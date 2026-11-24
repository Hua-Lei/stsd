"""读模型（read model）：把清单里的裸引用投影成人和 LLM 能判断的视图。

这是 CQRS 思路的轻量版本：写模型是 ``TaskList`` 聚合，读模型是这里的 dict。
投影只读、不写库，``preview`` 与 ``get_tasklist`` 共用同一份逻辑，避免两者
慢慢漂移；以后换一种展示格式（HTTP/HTML/CLI 表格）也只需要改这一处。

职责边界：
- 不做业务判断，不改变清单；
- 只调用端口取展示信息，并计算“当前处境”的 flags / diagnostics；
- 返回可直接 JSON 序列化的 dict。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..domain.hashing import compute_testpoint_content_hash
from ..domain.model import TaskList, TaskListItem
from ..domain.errors import ErrorCode, REJECT_MESSAGES
from ..ports import TestPointLibraryPort, DurationStat, RunHistoryPort

# 提示 flag（读取时计算，不入库）
FLAG_PINNED = "PINNED"
FLAG_SUPERSEDED = "SUPERSEDED"
FLAG_STALE = "STALE_EXPERIENCE"
FLAG_DURATION_UNKNOWN = "DURATION_UNKNOWN"
FLAG_CONTENT_CHANGED = "TESTPOINT_CONTENT_CHANGED"
FLAG_REVISION_MISSING = "REVISION_NOT_FOUND"


def project_items(
    tasklist: TaskList,
    items: Sequence[TaskListItem],
    testpoints: TestPointLibraryPort,
    history: RunHistoryPort | None,
    *,
    diagnostic: bool,
    resolve: bool,
) -> tuple[
    list[dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    dict[str, DurationStat],
]:
    """preview 与 get_tasklist 共用的条目投影。

    共同部分：seq / testpoint_ref / title。
    ``resolve=True`` 时额外计算 latest_frozen_revision（仅 preview 的诊断使用）；
    get_tasklist 不传 resolve，条目里只有清单冻结的修订。
    ``diagnostic=True`` 时再附加 last_run、flags 与诊断。
    """

    ids = [item.testpoint_id for item in items]
    refs = [item.revision_key for item in items]
    briefs = testpoints.get_testpoint_briefs(ids) if ids else {}
    outcomes = (
        testpoints.resolve_revisions(ids, tasklist.project_version)
        if resolve and ids
        else {}
    )
    versions = testpoints.get_revisions(refs) if refs else {}

    last_results: dict[str, Any] = {}
    durations: dict[str, DurationStat] = {}
    if diagnostic and history is not None and ids:
        last_results = history.get_last_results(ids)
        durations = history.get_duration_stats(ids)

    views: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for item in items:
        stored = versions.get(item.revision_key)
        outcome = outcomes.get(item.testpoint_id)
        latest_frozen_revision = (
            outcome.revision.revision_ver
            if outcome is not None and outcome.ok
            else None
        )
        brief = briefs.get(item.testpoint_id)

        view: dict[str, Any] = {
            "seq": item.seq,
            "testpoint_ref": item.testpoint_ref.to_dict(),
            "title": brief.title
            if brief is not None
            else (
                stored.title
                if stored is not None
                else item.testpoint_ref.title
            ),
        }
        if resolve:
            view["latest_frozen_revision"] = latest_frozen_revision

        if not diagnostic:
            views.append(view)
            continue

        flags: list[str] = []
        if item.testpoint_ref.pinned:
            flags.append(FLAG_PINNED)

        if stored is None:
            flags.append(FLAG_REVISION_MISSING)
            errors.append(
                {
                    "code": ErrorCode.REVISION_NOT_FOUND.value,
                    "testpoint_id": item.testpoint_id,
                    "message": "清单引用的修订在用例库中不存在",
                }
            )
        else:
            payload = testpoints.get_testpoint_payload(
                item.testpoint_id, item.revision_ver
            )
            current_hash = (
                compute_testpoint_content_hash(payload)
                if payload is not None
                else None
            )
            if current_hash is None:
                flags.append(FLAG_REVISION_MISSING)
                errors.append(
                    {
                        "code": ErrorCode.REVISION_NOT_FOUND.value,
                        "testpoint_id": item.testpoint_id,
                        "message": "无法读取该修订的实现正文",
                    }
                )
            elif current_hash != item.content_hash:
                flags.append(FLAG_CONTENT_CHANGED)
                errors.append(
                    {
                        "code": ErrorCode.TESTPOINT_CONTENT_CHANGED.value,
                        "testpoint_id": item.testpoint_id,
                        "message": "同修订内容指纹已变化，锁定会被拒绝",
                    }
                )

        if outcome is not None and not outcome.ok:
            code = outcome.code or ErrorCode.NO_APPLICABLE_REVISION.value
            flags.append(code)
            errors.append(
                {
                    "code": code,
                    "testpoint_id": item.testpoint_id,
                    "message": REJECT_MESSAGES.get(code, "目标版本下无法解析该测试点"),
                }
            )
        elif (
            latest_frozen_revision is not None
            and latest_frozen_revision != item.revision_ver
        ):
            # 解析结果与清单记录不一致就提示；
            # PINNED 条目同样提示，只是额外带 PINNED 标记供审核区分
            flags.append(FLAG_SUPERSEDED)
            warnings.append(
                {
                    "code": ErrorCode.SUPERSEDED.value,
                    "testpoint_id": item.testpoint_id,
                    "message": f"存在更新的适用修订 r{latest_frozen_revision}",
                }
            )

        last_run = last_results.get(item.testpoint_id)
        if last_run is not None:
            stale = (
                last_run.revision_ver != item.revision_ver
                or (
                    last_run.content_hash is not None
                    and last_run.content_hash != item.content_hash
                )
            )
            if stale:
                flags.append(FLAG_STALE)
                warnings.append(
                    {
                        "code": FLAG_STALE,
                        "testpoint_id": item.testpoint_id,
                        "message": "上次结果来自不同版本，不能作为跳过依据",
                    }
                )
            view["last_run"] = {
                "revision_ver": last_run.revision_ver,
                "status": last_run.status,
                "run_at": last_run.run_at,
                "stale": stale,
            }
        else:
            view["last_run"] = None

        stat = durations.get(item.testpoint_id)
        if stat is None or stat.samples <= 0:
            flags.append(FLAG_DURATION_UNKNOWN)
            view["duration_median_ms"] = None
        else:
            view["duration_median_ms"] = stat.median_ms

        view["flags"] = flags
        views.append(view)

    return views, {"errors": errors, "warnings": warnings}, durations


def summarize(
    items: Sequence[TaskListItem], durations: dict[str, DurationStat]
) -> dict[str, Any]:
    """条目数 / 预计总耗时 / 耗时未知条目数；不修改清单。"""

    total_ms = 0.0
    unknown = 0
    for item in items:
        stat = durations.get(item.testpoint_id)
        if stat is None or stat.samples <= 0:
            unknown += 1
        else:
            total_ms += stat.median_ms
    return {
        "item_count": len(items),
        "est_total_sec": round(total_ms / 1000, 2),
        "duration_unknown_count": unknown,
    }

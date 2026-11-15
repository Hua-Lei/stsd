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

from ..domain.model import TaskList, TaskListItem
from ..errors import ErrorCode, REJECT_MESSAGES
from ..ports import CaseLibraryPort, DurationStat, RunHistoryPort

# 提示 flag（读取时计算，不入库）
FLAG_PINNED = "PINNED"
FLAG_SUPERSEDED = "SUPERSEDED"
FLAG_DEPRECATED = "DEPRECATED_REF"
FLAG_STALE = "STALE_EXPERIENCE"
FLAG_DURATION_UNKNOWN = "DURATION_UNKNOWN"
FLAG_CONTENT_CHANGED = "CASE_CONTENT_CHANGED"
FLAG_VERSION_MISSING = "VERSION_NOT_FOUND"


def project_items(
    tasklist: TaskList,
    items: Sequence[TaskListItem],
    cases: CaseLibraryPort,
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

    共同部分：seq / case_ref / title / requirement_ids / risk_level。
    ``resolve=True`` 时额外计算 resolved_version（preview 的诊断需要）；
    get_tasklist 也带上它，但只作为读取时的展示信息，不写回清单。
    ``diagnostic=True`` 时再附加 last_run、flags 与诊断。
    """

    ids = [item.use_case_id for item in items]
    refs = [(item.use_case_id, item.use_case_version) for item in items]
    briefs = cases.get_case_briefs(ids) if ids else {}
    outcomes = (
        cases.resolve_versions(ids, tasklist.target_software_release_version)
        if resolve and ids
        else {}
    )
    versions = cases.get_versions(refs) if refs else {}

    last_results: dict[str, Any] = {}
    durations: dict[str, DurationStat] = {}
    if diagnostic and history is not None and ids:
        last_results = history.get_last_results(ids)
        durations = history.get_duration_stats(ids)

    views: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for item in items:
        stored = versions.get((item.use_case_id, item.use_case_version))
        outcome = outcomes.get(item.use_case_id)
        resolved_version = (
            outcome.version.use_case_version
            if outcome is not None and outcome.ok
            else None
        )
        brief = briefs.get(item.use_case_id)

        view: dict[str, Any] = {
            "seq": item.seq,
            "case_ref": item.case_ref.to_dict(),
            "title": brief.title
            if brief is not None
            else (stored.title if stored is not None else None),
            "requirement_ids": list(brief.requirement_ids)
            if brief is not None
            else (list(stored.requirement_ids) if stored is not None else []),
            "risk_level": brief.risk_level
            if brief is not None
            else (stored.risk_level if stored is not None else None),
        }
        if resolve:
            view["resolved_version"] = resolved_version

        if not diagnostic:
            views.append(view)
            continue

        flags: list[str] = []
        if item.case_ref.pinned:
            flags.append(FLAG_PINNED)

        if stored is None:
            flags.append(FLAG_VERSION_MISSING)
            errors.append(
                {
                    "code": ErrorCode.VERSION_NOT_FOUND.value,
                    "use_case_id": item.use_case_id,
                    "message": "清单引用的版本在用例库中不存在",
                }
            )
        else:
            if stored.status == "deprecated":
                flags.append(FLAG_DEPRECATED)
                warnings.append(
                    {
                        "code": ErrorCode.DEPRECATED_REF.value,
                        "use_case_id": item.use_case_id,
                        "message": REJECT_MESSAGES[ErrorCode.DEPRECATED_REF.value],
                    }
                )
            if stored.content_hash != item.content_hash:
                flags.append(FLAG_CONTENT_CHANGED)
                errors.append(
                    {
                        "code": ErrorCode.CASE_CONTENT_CHANGED.value,
                        "use_case_id": item.use_case_id,
                        "message": "同版本用例内容指纹已变化，锁定会被拒绝",
                    }
                )

        if outcome is not None and not outcome.ok:
            code = outcome.code or ErrorCode.NO_APPLICABLE_VERSION.value
            flags.append(code)
            errors.append(
                {
                    "code": code,
                    "use_case_id": item.use_case_id,
                    "message": REJECT_MESSAGES.get(code, "目标版本下无法解析该用例"),
                }
            )
        elif (
            resolved_version is not None
            and resolved_version != item.use_case_version
        ):
            # design.md 第四节：resolved_version 与 usecase_version 不相等就提示，
            # PINNED 条目同样提示，只是额外带 PINNED 标记供审核区分
            flags.append(FLAG_SUPERSEDED)
            warnings.append(
                {
                    "code": ErrorCode.SUPERSEDED.value,
                    "use_case_id": item.use_case_id,
                    "message": f"存在更新的适用版本 v{resolved_version}",
                }
            )

        last_run = last_results.get(item.use_case_id)
        if last_run is not None:
            stale = (
                last_run.use_case_version != item.use_case_version
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
                        "use_case_id": item.use_case_id,
                        "message": "上次结果来自不同版本，不能作为跳过依据",
                    }
                )
            view["last_run"] = {
                "use_case_version": last_run.use_case_version,
                "status": last_run.status,
                "run_at": last_run.run_at,
                "stale": stale,
            }
        else:
            view["last_run"] = None

        stat = durations.get(item.use_case_id)
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
    total_ms = 0.0
    unknown = 0
    for item in items:
        stat = durations.get(item.use_case_id)
        if stat is None or stat.samples <= 0:
            unknown += 1
        else:
            total_ms += stat.median_ms
    return {
        "item_count": len(items),
        "est_total_sec": round(total_ms / 1000, 2),
        "duration_unknown_count": unknown,
    }

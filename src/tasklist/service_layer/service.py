"""应用层（Service Layer）：一个函数就是一个业务用例。

沿用参考实现 ``src/library/service_layer/service.py`` 的风格：

- 服务函数无状态，只负责开事务、取聚合、调用领域规则、写回；
- 实体自己的规则在 ``domain/model.py``；
- 需要查仓储/端口才能判断的跨聚合规则（目标版本下是否还有适用版本、
  同版本内容指纹是否漂移）留在这一层；
- 仓储与外部端口都从 ``uow`` 上取，测试可以整体替换。

返回值为 JSON 可序列化的 read model（dict），写操作返回结构化结果而不是
只给成功/失败，让 LLM 与人工看到同样的反馈。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..domain.model import (
    CaseRef,
    CopyMode,
    Status,
    TaskList,
    validate_target,
)
from ..errors import (
    ErrorCode,
    EmptyList,
    InvalidArgument,
    ListLocked,
    ListNotFound,
    ListNotLocked,
    ExportUnsupported,
    TaskListError,
    rejection,
)
from . import views
from .unit_of_work import AbstractUnitOfWork


# ===========================================================================
# 生命周期
# ===========================================================================
def create_list(
    uow: AbstractUnitOfWork,
    target_software_release_version: int | None,
    tasklist_title: str | None = None,
) -> dict[str, Any]:
    with uow:
        tasklist = TaskList.create(
            uow.tasklists.proj_id, target_software_release_version, tasklist_title
        )
        uow.tasklists.save(tasklist)
        uow.commit()
        return {
            "tasklist_id": tasklist.tasklist_id,
            "status": Status.DRAFT.value,
        }


def copy_list(
    uow: AbstractUnitOfWork,
    source_tasklist_id: str,
    target_software_release_version: int | None,
    mode: str | CopyMode = CopyMode.RERESOLVE,
) -> dict[str, Any]:
    target = validate_target(target_software_release_version)
    copy_mode = _normalize_mode(mode)

    with uow:
        source = _require(uow, source_tasklist_id, for_update=True)
        accepted, rejected, warnings = _copy_refs(uow, source, target, copy_mode)

        tasklist = TaskList.create(
            uow.tasklists.proj_id,
            target,
            source.tasklist_title,
            case_refs=accepted,
            source_tasklist_id=source.tasklist_id,
            copy_mode=copy_mode,
        )
        uow.tasklists.save(tasklist)
        uow.commit()

        return {
            "tasklist_id": tasklist.tasklist_id,
            "status": Status.DRAFT.value,
            "source_tasklist_id": source.tasklist_id,
            "mode": copy_mode.value,
            "item_count": len(accepted),
            "rejected": rejected,
            "warnings": warnings,
        }


def lock_list(
    uow: AbstractUnitOfWork, tasklist_id: str
) -> dict[str, Any]:
    with uow:
        tasklist = _require(uow, tasklist_id, for_update=True)
        if not tasklist.is_editable:
            raise ListLocked(
                "清单已锁定，不能重复锁定", tasklist_id=tasklist_id
            )
        if not tasklist.items:
            raise EmptyList(tasklist_id=tasklist_id)

        items = tasklist.items
        refs = [(item.use_case_id, item.use_case_version) for item in items]
        version_map = uow.cases.get_versions(refs)

        missing: list[dict[str, Any]] = []
        changed: list[dict[str, Any]] = []
        for item in items:
            found = version_map.get((item.use_case_id, item.use_case_version))
            if found is None:
                missing.append(
                    {
                        "use_case_id": item.use_case_id,
                        "use_case_version": item.use_case_version,
                        "code": ErrorCode.VERSION_NOT_FOUND.value,
                    }
                )
            elif found.content_hash != item.content_hash:
                # 已发布版本应当永久只读；同版本指纹变化说明前提被破坏
                changed.append(
                    {
                        "use_case_id": item.use_case_id,
                        "use_case_version": item.use_case_version,
                        "stored_content_hash": item.content_hash,
                        "current_content_hash": found.content_hash,
                    }
                )

        if missing:
            raise TaskListError(
                ErrorCode.VERSION_NOT_FOUND,
                "清单中存在用例库已找不到的版本，不能锁定",
                tasklist_id=tasklist_id,
                details={"items": missing},
            )
        if changed:
            raise TaskListError(
                ErrorCode.CASE_CONTENT_CHANGED,
                "同版本用例内容指纹发生变化（违反已发布版本只读前提），不能锁定",
                tasklist_id=tasklist_id,
                details={"items": changed},
            )

        content_hash = tasklist.lock()
        uow.tasklists.save(tasklist)
        uow.commit()

        return {
            "tasklist_id": tasklist_id,
            "content_hash": content_hash,
            "item_count": len(items),
        }


# ===========================================================================
# 编辑（仅 DRAFT）
# ===========================================================================
def add_items(
    uow: AbstractUnitOfWork,
    tasklist_id: str,
    use_case_ids: Sequence[str] | str,
    pin_versions: dict[str, int] | None = None,
) -> dict[str, Any]:
    ids = _normalize_ids(use_case_ids)
    pins = _normalize_pins(pin_versions)

    with uow:
        tasklist = _require(uow, tasklist_id, for_update=True)
        tasklist.ensure_draft()

        accepted, rejected, warnings = _collect_new_refs(uow, tasklist, ids, pins)
        if accepted:
            tasklist.add_case_refs(accepted)
            uow.tasklists.save(tasklist)
            uow.commit()

        return {
            "tasklist_id": tasklist_id,
            "rev": tasklist.rev,
            "added": [ref.to_dict() for ref in accepted],
            "rejected": rejected,
            "warnings": warnings,
        }


def remove_items(
    uow: AbstractUnitOfWork,
    tasklist_id: str,
    use_case_ids: Sequence[str] | str,
) -> dict[str, Any]:
    ids = _normalize_ids(use_case_ids)

    with uow:
        tasklist = _require(uow, tasklist_id, for_update=True)
        tasklist.ensure_draft()

        existing = {item.use_case_id for item in tasklist.items}
        removed = tasklist.remove_case_refs(ids)
        not_found = [
            case_id for case_id in dict.fromkeys(ids) if case_id not in existing
        ]

        if removed:
            uow.tasklists.save(tasklist)
            uow.commit()

        return {
            "tasklist_id": tasklist_id,
            "rev": tasklist.rev,
            "removed": removed,
            "not_found": not_found,
        }


def rename_list(
    uow: AbstractUnitOfWork, tasklist_id: str, tasklist_title: str | None
) -> dict[str, Any]:
    """元数据修改：锁定后仍可改，且不影响 content_hash / rev。"""

    with uow:
        tasklist = _require(uow, tasklist_id, for_update=True)
        tasklist.rename(tasklist_title)
        uow.tasklists.save(tasklist)
        uow.commit()
        return {
            "tasklist_id": tasklist_id,
            "tasklist_title": tasklist.tasklist_title,
        }


# ===========================================================================
# 读取
# ===========================================================================
def get_tasklist(
    uow: AbstractUnitOfWork, tasklist_id: str
) -> dict[str, Any]:
    """只读接口：与 preview 共用条目投影。

    resolved_version 是读取时关联出的展示信息，不写回清单；
    清单的权威版本始终是 case_ref 里的 (use_case_id, use_case_version)。
    """

    with uow:
        tasklist = _require(uow, tasklist_id)
        item_views, _, _ = views.project_items(
            tasklist,
            tasklist.items,
            uow.cases,
            uow.history,
            diagnostic=False,
            resolve=True,
        )
        return {
            **tasklist.to_dict(),
            "item_count": tasklist.item_count,
            "items": item_views,
        }


# design_1.md 沿用了 get_list 这个名字；保留别名，两个名字行为一致
get_list = get_tasklist


def preview(
    uow: AbstractUnitOfWork,
    tasklist_id: str,
    view: str = "full",
    page: int = 1,
    page_size: int | None = None,
) -> dict[str, Any]:
    """只报告问题、不拦截；拦截留给 lock_list。无副作用，可反复调用。"""

    if view not in ("full", "summary"):
        raise InvalidArgument("view 只能是 full 或 summary")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise InvalidArgument("page 必须是 >= 1 的整数")
    if page_size is not None and (
        isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or page_size < 1
    ):
        raise InvalidArgument("page_size 必须是 >= 1 的整数")

    with uow:
        tasklist = _require(uow, tasklist_id)
        items = tasklist.items
        item_views, diagnostics, durations = views.project_items(
            tasklist,
            items,
            uow.cases,
            uow.history,
            diagnostic=True,
            resolve=True,
        )

        if not items:
            diagnostics["errors"].insert(
                0,
                {
                    "code": ErrorCode.EMPTY_LIST.value,
                    "use_case_id": None,
                    "message": "空清单不允许锁定",
                },
            )

        result: dict[str, Any] = {
            "tasklist_id": tasklist.tasklist_id,
            "status": tasklist.status.value,
            "target_software_release_version": (
                tasklist.target_software_release_version
            ),
            "tasklist_title": tasklist.tasklist_title,
            "rev": tasklist.rev,
            "summary": views.summarize(items, durations),
            "diagnostics": diagnostics,
        }

        if view == "summary":
            return result

        start = (page - 1) * page_size if page_size else 0
        page_items = item_views[start : start + page_size] if page_size else item_views
        result.update(
            {
                "page": page,
                "page_size": page_size,
                "items": page_items,
            }
        )
        return result


def list_tasklists(
    uow: AbstractUnitOfWork, status: str | None = None
) -> list[dict[str, Any]]:
    with uow:
        records = uow.tasklists.list_all()
        if status is not None:
            wanted = str(status).upper()
            records = [record for record in records if record.status.value == wanted]
        return [record.to_dict() for record in records]


# ===========================================================================
# 与执行器协作：把锁定清单导出为 TestCase JSON（可选能力）
# ===========================================================================
def export_cases(
    uow: AbstractUnitOfWork, tasklist_id: str
) -> list[dict[str, Any]]:
    """按 seq 顺序返回用例正文，可直接交给 ``demo.executor.CaseExecutor``。

    只要求锁定清单：状态一旦 LOCKED，条目与指纹都不会再变，
    执行的就是被审核过的那一份内容。
    """

    with uow:
        tasklist = _require(uow, tasklist_id)
        if tasklist.status is not Status.LOCKED:
            raise ListNotLocked(tasklist_id)

        getter = getattr(uow.cases, "get_case_payload", None)
        if not callable(getter):
            raise ExportUnsupported(tasklist_id)

        payloads: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        for item in tasklist.items:
            payload = getter(item.use_case_id, item.use_case_version)
            if payload is None:
                missing.append(
                    {
                        "use_case_id": item.use_case_id,
                        "use_case_version": item.use_case_version,
                    }
                )
            else:
                payloads.append(payload)

        if missing:
            raise TaskListError(
                ErrorCode.VERSION_NOT_FOUND,
                "清单中部分用例在用例库适配器里没有正文，无法导出",
                tasklist_id=tasklist_id,
                details={"items": missing},
            )
        return payloads


# ===========================================================================
# 内部：跨聚合规则与参数规范化
# ===========================================================================
def _copy_refs(
    uow: AbstractUnitOfWork,
    source: TaskList,
    target: int,
    copy_mode: CopyMode,
) -> tuple[list[CaseRef], list[dict[str, str]], list[dict[str, str]]]:
    """复制时把来源条目转换成新草稿的引用。

    RERESOLVE 必须在复制这一刻完成解析并写入草稿，不能推迟到锁定：
    否则人工审核看到的是版本 4，锁定后变成版本 6。
    """

    accepted: list[CaseRef] = []
    rejected: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    source_items = source.items

    if copy_mode is CopyMode.RERESOLVE:
        ids = [item.use_case_id for item in source_items]
        outcomes = uow.cases.resolve_versions(ids, target)
        for item in source_items:
            outcome = outcomes.get(item.use_case_id)
            if outcome is None or not outcome.ok:
                code = (
                    outcome.code
                    if outcome is not None
                    else ErrorCode.CASE_NOT_FOUND.value
                )
                rejected.append(rejection(item.use_case_id, code))
            else:
                version = outcome.version
                accepted.append(
                    CaseRef(
                        use_case_id=item.use_case_id,
                        use_case_version=version.use_case_version,
                        content_hash=version.content_hash,
                        pinned=False,
                    )
                )
        return accepted, rejected, warnings

    refs = [
        (item.use_case_id, item.use_case_version) for item in source_items
    ]
    version_map = uow.cases.get_versions(refs)
    briefs = uow.cases.get_case_briefs(
        [item.use_case_id for item in source_items]
    )
    for item in source_items:
        if item.use_case_id not in briefs:
            rejected.append(
                rejection(item.use_case_id, ErrorCode.CASE_NOT_FOUND.value)
            )
            continue
        found = version_map.get((item.use_case_id, item.use_case_version))
        if found is None:
            rejected.append(
                rejection(item.use_case_id, ErrorCode.VERSION_NOT_FOUND.value)
            )
            continue
        accepted.append(
            CaseRef(
                use_case_id=item.use_case_id,
                use_case_version=item.use_case_version,
                content_hash=found.content_hash,
                pinned=True,
            )
        )

    if target != source.target_software_release_version:
        warnings.append(
            {
                "code": "TARGET_CHANGED",
                "message": (
                    "PINNED 复制保留了原版本，但目标版本与来源清单不同；"
                    "请确认这是有意为之"
                ),
            }
        )
    return accepted, rejected, warnings


def _collect_new_refs(
    uow: AbstractUnitOfWork,
    tasklist: TaskList,
    ids: list[str],
    pins: dict[str, int],
) -> tuple[list[CaseRef], list[dict[str, str]], list[dict[str, str]]]:
    """逐条判断能否加入；失败的放进 rejected，不抛异常。"""

    existing = {item.use_case_id for item in tasklist.items}
    briefs = uow.cases.get_case_briefs(ids) if ids else {}
    resolve_ids = [
        case_id for case_id in ids if case_id not in existing and case_id not in pins
    ]
    outcomes = (
        uow.cases.resolve_versions(
            resolve_ids, tasklist.target_software_release_version
        )
        if resolve_ids
        else {}
    )
    pin_refs = [
        (case_id, pins[case_id])
        for case_id in ids
        if case_id not in existing and case_id in pins
    ]
    pinned_versions = (
        uow.cases.get_versions(pin_refs) if pin_refs else {}
    )

    accepted: list[CaseRef] = []
    rejected: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    seen: set[str] = set()

    for case_id in ids:
        if case_id in seen or case_id in existing:
            rejected.append(rejection(case_id, ErrorCode.DUPLICATE.value))
        elif case_id not in briefs:
            rejected.append(rejection(case_id, ErrorCode.CASE_NOT_FOUND.value))
        elif case_id in pins:
            found = pinned_versions.get((case_id, pins[case_id]))
            if found is None:
                rejected.append(
                    rejection(
                        case_id,
                        ErrorCode.VERSION_NOT_FOUND.value,
                        f"指定版本 v{pins[case_id]} 不存在",
                    )
                )
            else:
                accepted.append(
                    CaseRef(
                        use_case_id=case_id,
                        use_case_version=found.use_case_version,
                        content_hash=found.content_hash,
                        pinned=True,
                    )
                )
                if found.status == "deprecated":
                    warnings.append(
                        rejection(case_id, ErrorCode.DEPRECATED_REF.value)
                    )
        else:
            outcome = outcomes.get(case_id)
            if outcome is None or not outcome.ok:
                code = (
                    outcome.code
                    if outcome is not None
                    else ErrorCode.CASE_NOT_FOUND.value
                )
                rejected.append(rejection(case_id, code))
            else:
                version = outcome.version
                accepted.append(
                    CaseRef(
                        use_case_id=case_id,
                        use_case_version=version.use_case_version,
                        content_hash=version.content_hash,
                        pinned=False,
                    )
                )
        seen.add(case_id)

    return accepted, rejected, warnings


def _require(
    uow: AbstractUnitOfWork, tasklist_id: str, *, for_update: bool = False
) -> TaskList:
    tasklist = (
        uow.tasklists.get_for_update(tasklist_id)
        if for_update
        else uow.tasklists.get(tasklist_id)
    )
    if tasklist is None:
        raise ListNotFound(tasklist_id)
    return tasklist


def _normalize_mode(mode: str | CopyMode) -> CopyMode:
    try:
        return CopyMode(str(mode).upper())
    except ValueError as exc:
        raise InvalidArgument(
            f"mode 只能是 RERESOLVE 或 PINNED，得到 {mode!r}"
        ) from exc


def _normalize_ids(use_case_ids: Sequence[str] | str) -> list[str]:
    raw = [use_case_ids] if isinstance(use_case_ids, str) else list(use_case_ids)
    ids: list[str] = []
    for case_id in raw:
        if not isinstance(case_id, str) or not case_id:
            raise InvalidArgument("use_case_id 必须是非空字符串")
        ids.append(case_id)
    return ids


def _normalize_pins(pin_versions: dict[str, int] | None) -> dict[str, int]:
    if pin_versions is None:
        return {}
    if not isinstance(pin_versions, dict):
        raise InvalidArgument("pin_versions 必须是 {use_case_id: version}")

    pins: dict[str, int] = {}
    for case_id, version in pin_versions.items():
        if not isinstance(case_id, str) or not case_id:
            raise InvalidArgument("pin_versions 的键必须是非空字符串")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise InvalidArgument(
                f"pin_versions[{case_id!r}] 必须是 >= 1 的整数"
            )
        pins[case_id] = version
    return pins

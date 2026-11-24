"""应用层（Service Layer）：一个函数就是一个业务用例。

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
    CopyMode,
    Status,
    TaskList,
    TestPointRef,
    validate_project_version,
)
from ..domain.hashing import compute_testpoint_content_hash
from ..domain.errors import (
    ErrorCode,
    EmptyList,
    InvalidArgument,
    ListLocked,
    ListNotFound,
    ListNotLocked,
    ProjectVersionNotFound,
    TaskListError,
    rejection,
)
from ..ports import ProjectVersionLookup
from . import views
from .unit_of_work import AbstractUnitOfWork
from ..command import (
    AddItems,
    CopyTaskList,
    CreateTaskList,
    ExportTestPoints,
    GetTaskList,
    ListTaskLists,
    LockTaskList,
    PreviewTaskList,
    RemoveItems,
    RenameTaskList,
)


# ===========================================================================
# 生命周期
# ===========================================================================
def create_tasklist(
    uow: AbstractUnitOfWork,
    project_versions: ProjectVersionLookup,
    command: CreateTaskList,
) -> dict[str, Any]:
    """创建 DRAFT 清单；先向 Access 确认项目版本存在。"""

    project_version = validate_project_version(command.project_version)

    with uow:
        _require_project_version(
            project_versions, uow.tasklists.proj_id, project_version
        )
        tasklist = TaskList.create(
            uow.tasklists.proj_id,
            project_version,
            command.tasklist_title,
        )
        uow.tasklists.save(tasklist)
        uow.commit()
        return {
            "tasklist_id": tasklist.tasklist_id,
            "status": Status.DRAFT.value,
        }


def copy_tasklist(
    uow: AbstractUnitOfWork,
    project_versions: ProjectVersionLookup,
    command: CopyTaskList,
) -> dict[str, Any]:
    """从已有清单复制一份新草稿。

    RERESOLVE 在复制这一刻按新项目版本重新解析；PINNED 保留来源引用。
    新项目版本同样要先向 Access 确认存在。
    """

    project_version = validate_project_version(command.project_version)
    copy_mode = _normalize_mode(command.mode)

    with uow:
        _require_project_version(
            project_versions, uow.tasklists.proj_id, project_version
        )
        source = _require(uow, command.source_tasklist_id, for_update=True)
        accepted, rejected, warnings = _copy_refs(
            uow, source, project_version, copy_mode
        )

        tasklist = TaskList.create(
            uow.tasklists.proj_id,
            project_version,
            source.tasklist_title,
            testpoint_refs=accepted,
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


def lock_tasklist(
    uow: AbstractUnitOfWork, command: LockTaskList
) -> dict[str, Any]:
    """锁定清单：校验 DRAFT、非空、引用可查且内容指纹未漂移。"""

    tasklist_id = command.tasklist_id
    with uow:
        tasklist = _require(uow, tasklist_id, for_update=True)
        if not tasklist.is_editable:
            raise ListLocked(
                "清单已锁定，不能重复锁定", tasklist_id=tasklist_id
            )
        if not tasklist.items:
            raise EmptyList(tasklist_id=tasklist_id)

        items = tasklist.items
        refs = [item.revision_key for item in items]
        version_map = uow.testpoints.get_revisions(refs)

        missing: list[dict[str, Any]] = []
        changed: list[dict[str, Any]] = []
        for item in items:
            found = version_map.get(item.revision_key)
            if found is None:
                missing.append(
                    {
                        "testpoint_id": item.testpoint_id,
                        "revision_ver": item.revision_ver,
                        "code": ErrorCode.REVISION_NOT_FOUND.value,
                    }
                )
                continue
            current_hash = _payload_hash(
                uow, item.testpoint_id, item.revision_ver
            )
            if current_hash is None:
                missing.append(
                    {
                        "testpoint_id": item.testpoint_id,
                        "revision_ver": item.revision_ver,
                        "code": ErrorCode.REVISION_NOT_FOUND.value,
                    }
                )
            elif current_hash != item.content_hash:
                # 已发布版本应当永久只读；同版本指纹变化说明前提被破坏
                changed.append(
                    {
                        "testpoint_id": item.testpoint_id,
                        "revision_ver": item.revision_ver,
                        "stored_content_hash": item.content_hash,
                        "current_content_hash": current_hash,
                    }
                )

        if missing:
            raise TaskListError(
                ErrorCode.REVISION_NOT_FOUND,
                "清单中存在用例库已找不到的修订，不能锁定",
                tasklist_id=tasklist_id,
                details={"items": missing},
            )
        if changed:
            raise TaskListError(
                ErrorCode.TESTPOINT_CONTENT_CHANGED,
                "同修订内容指纹发生变化（违反已发布修订只读前提），不能锁定",
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
    uow: AbstractUnitOfWork, command: AddItems
) -> dict[str, Any]:
    """批量加入测试点；条目级失败进 rejected，不中断整批。

    ``pin_versions`` 可选指定修订号；修订号在用例库中全局唯一。
    """

    tasklist_id = command.tasklist_id
    ids = _normalize_ids(command.testpoint_ids)
    pins = _normalize_pins(command.pin_versions)

    with uow:
        tasklist = _require(uow, tasklist_id, for_update=True)
        tasklist.ensure_draft()

        accepted, rejected, warnings = _collect_new_refs(uow, tasklist, ids, pins)
        if accepted:
            tasklist.add_testpoint_refs(accepted)
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
    uow: AbstractUnitOfWork, command: RemoveItems
) -> dict[str, Any]:
    """按 testpoint_id 删除；真实删除的进 removed，其余进 not_found。"""

    tasklist_id = command.tasklist_id
    ids = _normalize_ids(command.testpoint_ids)

    with uow:
        tasklist = _require(uow, tasklist_id, for_update=True)
        tasklist.ensure_draft()

        existing = {item.testpoint_id for item in tasklist.items}
        removed = tasklist.remove_testpoint_refs(ids)
        not_found = [
            testpoint_id for testpoint_id in dict.fromkeys(ids) if testpoint_id not in existing
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


def rename_tasklist(
    uow: AbstractUnitOfWork, command: RenameTaskList
) -> dict[str, Any]:
    """元数据修改：锁定后仍可改，且不影响 content_hash / rev。"""

    tasklist_id = command.tasklist_id
    with uow:
        tasklist = _require(uow, tasklist_id, for_update=True)
        tasklist.rename(command.tasklist_title)
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
    uow: AbstractUnitOfWork, command: GetTaskList
) -> dict[str, Any]:
    """只读接口：返回清单冻结的内容，不做版本解析。

    条目的权威版本始终是 testpoint_ref 里的 (testpoint_id, revision_ver)；
    “当前最新已冻结修订”只在 preview 的诊断里出现，不写回清单。
    """

    with uow:
        tasklist = _require(uow, command.tasklist_id)
        item_views, _, _ = views.project_items(
            tasklist,
            tasklist.items,
            uow.testpoints,
            uow.history,
            diagnostic=False,
            resolve=False,
        )
        return {
            **tasklist.to_dict(),
            "item_count": tasklist.item_count,
            "items": item_views,
        }


def preview_tasklist(
    uow: AbstractUnitOfWork, command: PreviewTaskList
) -> dict[str, Any]:
    """只报告问题、不拦截；拦截留给 lock_tasklist。无副作用，可反复调用。"""

    view = command.view
    page = command.page
    page_size = command.page_size
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
        tasklist = _require(uow, command.tasklist_id)
        items = tasklist.items
        item_views, diagnostics, durations = views.project_items(
            tasklist,
            items,
            uow.testpoints,
            uow.history,
            diagnostic=True,
            resolve=True,
        )

        if not items:
            diagnostics["errors"].insert(
                0,
                {
                    "code": ErrorCode.EMPTY_LIST.value,
                    "testpoint_id": None,
                    "message": "空清单不允许锁定",
                },
            )

        result: dict[str, Any] = {
            "tasklist_id": tasklist.tasklist_id,
            "status": tasklist.status.value,
            "project_version": (
                tasklist.project_version
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
    uow: AbstractUnitOfWork, command: ListTaskLists
) -> list[dict[str, Any]]:
    """列出当前项目的清单摘要，可按 DRAFT/LOCKED 过滤。"""

    status = command.status
    with uow:
        records = uow.tasklists.list_all()
        if status is not None:
            wanted = str(status).upper()
            records = [record for record in records if record.status.value == wanted]
        return [record.to_dict() for record in records]


# ===========================================================================
# 与执行器协作：把锁定清单导出为 TestCase JSON（可选能力）
# ===========================================================================
def export_testpoints(
    uow: AbstractUnitOfWork, command: ExportTestPoints
) -> list[Any]:
    """按 seq 顺序返回测试点实现正文，可直接交给执行器。

    只要求锁定清单：状态一旦 LOCKED，条目与指纹都不会再变，
    执行的就是被审核过的那一份内容。
    """

    tasklist_id = command.tasklist_id
    with uow:
        tasklist = _require(uow, tasklist_id)
        if tasklist.status is not Status.LOCKED:
            raise ListNotLocked(tasklist_id)

        payloads: list[Any] = []
        missing: list[dict[str, Any]] = []
        for item in tasklist.items:
            payload = uow.testpoints.get_testpoint_payload(
                item.testpoint_id, item.revision_ver
            )
            if payload is None:
                missing.append(
                    {
                        "testpoint_id": item.testpoint_id,
                        "revision_ver": item.revision_ver,
                    }
                )
            else:
                payloads.append(payload)

        if missing:
            raise TaskListError(
                ErrorCode.REVISION_NOT_FOUND,
                "清单中部分测试点在用例库适配器里没有正文，无法导出",
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
    project_version: str,
    copy_mode: CopyMode,
) -> tuple[list[TestPointRef], list[dict[str, str]], list[dict[str, str]]]:
    """复制时把来源条目转换成新草稿的引用。

    RERESOLVE 必须在复制这一刻完成解析并写入草稿，不能推迟到锁定：
    否则人工审核看到的是版本 4，锁定后变成版本 6。
    """

    accepted: list[TestPointRef] = []
    rejected: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    source_items = source.items

    if copy_mode is CopyMode.RERESOLVE:
        ids = [item.testpoint_id for item in source_items]
        outcomes = uow.testpoints.resolve_revisions(ids, project_version)
        for item in source_items:
            outcome = outcomes.get(item.testpoint_id)
            if outcome is None or not outcome.ok:
                code = (
                    outcome.code
                    if outcome is not None
                    else ErrorCode.TESTPOINT_NOT_FOUND.value
                )
                rejected.append(rejection(item.testpoint_id, code))
            else:
                revision = outcome.revision
                content_hash = _payload_hash(
                    uow, item.testpoint_id, revision.revision_ver
                )
                if content_hash is None:
                    rejected.append(
                        rejection(
                            item.testpoint_id,
                            ErrorCode.REVISION_NOT_FOUND.value,
                        )
                    )
                    continue
                accepted.append(
                    TestPointRef(
                        testpoint_id=item.testpoint_id,
                        revision_ver=revision.revision_ver,
                        content_hash=content_hash,
                        pinned=False,
                        title=revision.title,
                    )
                )
        return accepted, rejected, warnings

    refs = [item.revision_key for item in source_items]
    version_map = uow.testpoints.get_revisions(refs)
    for item in source_items:
        found = version_map.get(item.revision_key)
        if found is None:
            rejected.append(
                rejection(item.testpoint_id, ErrorCode.REVISION_NOT_FOUND.value)
            )
            continue
        content_hash = _payload_hash(
            uow, item.testpoint_id, item.revision_ver
        )
        if content_hash is None:
            rejected.append(
                rejection(item.testpoint_id, ErrorCode.REVISION_NOT_FOUND.value)
            )
            continue
        accepted.append(
            TestPointRef(
                testpoint_id=item.testpoint_id,
                revision_ver=item.revision_ver,
                content_hash=content_hash,
                pinned=True,
                title=found.title,
            )
        )

    if project_version != source.project_version:
        warnings.append(
            {
                "code": "PROJECT_VERSION_CHANGED",
                "message": (
                    "PINNED 复制保留了原修订，但项目版本与来源清单不同；"
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
) -> tuple[list[TestPointRef], list[dict[str, str]], list[dict[str, str]]]:
    """逐条判断能否加入；失败的放进 rejected，不抛异常。"""

    existing = {item.testpoint_id for item in tasklist.items}
    briefs = uow.testpoints.get_testpoint_briefs(ids) if ids else {}
    resolve_ids = [
        testpoint_id for testpoint_id in ids if testpoint_id not in existing and testpoint_id not in pins
    ]
    outcomes = (
        uow.testpoints.resolve_revisions(
            resolve_ids, tasklist.project_version
        )
        if resolve_ids
        else {}
    )
    pin_refs = [
        (testpoint_id, pins[testpoint_id])
        for testpoint_id in ids
        if testpoint_id not in existing and testpoint_id in pins
    ]
    pinned_revisions = (
        uow.testpoints.get_revisions(pin_refs) if pin_refs else {}
    )

    accepted: list[TestPointRef] = []
    rejected: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    seen: set[str] = set()

    for testpoint_id in ids:
        if testpoint_id in seen or testpoint_id in existing:
            rejected.append(rejection(testpoint_id, ErrorCode.DUPLICATE.value))
        elif testpoint_id not in briefs:
            rejected.append(rejection(testpoint_id, ErrorCode.TESTPOINT_NOT_FOUND.value))
        elif testpoint_id in pins:
            found = pinned_revisions.get((testpoint_id, pins[testpoint_id]))
            if found is None:
                rejected.append(
                    rejection(
                        testpoint_id,
                        ErrorCode.REVISION_NOT_FOUND.value,
                        f"指定修订 r{pins[testpoint_id]} 不存在",
                    )
                )
            else:
                content_hash = _payload_hash(
                    uow, testpoint_id, found.revision_ver
                )
                if content_hash is None:
                    rejected.append(
                        rejection(
                            testpoint_id,
                            ErrorCode.REVISION_NOT_FOUND.value,
                        )
                    )
                else:
                    accepted.append(
                        TestPointRef(
                            testpoint_id=testpoint_id,
                            revision_ver=found.revision_ver,
                            content_hash=content_hash,
                            pinned=True,
                            title=found.title,
                        )
                    )
        else:
            outcome = outcomes.get(testpoint_id)
            if outcome is None or not outcome.ok:
                code = (
                    outcome.code
                    if outcome is not None
                    else ErrorCode.TESTPOINT_NOT_FOUND.value
                )
                rejected.append(rejection(testpoint_id, code))
            else:
                revision = outcome.revision
                content_hash = _payload_hash(
                    uow, testpoint_id, revision.revision_ver
                )
                if content_hash is None:
                    rejected.append(
                        rejection(
                            testpoint_id,
                            ErrorCode.REVISION_NOT_FOUND.value,
                        )
                    )
                else:
                    accepted.append(
                        TestPointRef(
                            testpoint_id=testpoint_id,
                            revision_ver=revision.revision_ver,
                            content_hash=content_hash,
                            pinned=False,
                            title=revision.title,
                        )
                    )
        seen.add(testpoint_id)

    return accepted, rejected, warnings


def _require(
    uow: AbstractUnitOfWork, tasklist_id: str, *, for_update: bool = False
) -> TaskList:
    """取清单；不存在统一翻译成 ListNotFound。"""

    tasklist = (
        uow.tasklists.get_for_update(tasklist_id)
        if for_update
        else uow.tasklists.get(tasklist_id)
    )
    if tasklist is None:
        raise ListNotFound(tasklist_id)
    return tasklist


def _payload_hash(
    uow: AbstractUnitOfWork, testpoint_id: str, revision_ver: int
) -> str | None:
    """TaskList 自己计算内容指纹；用例库只提供实现正文。"""

    payload = uow.testpoints.get_testpoint_payload(testpoint_id, revision_ver)
    if payload is None:
        return None
    return compute_testpoint_content_hash(payload)


def _require_project_version(
    dep: ProjectVersionLookup, project_id: str, proj_ver: str
) -> None:
    """端口只读不可变事实；必须在写操作之前调用。"""

    if not dep.project_version_exists(project_id, proj_ver):
        raise ProjectVersionNotFound(project_id, proj_ver)


def _normalize_mode(mode: str | CopyMode) -> CopyMode:
    """复制模式只接受 RERESOLVE / PINNED，大小写不敏感。"""

    try:
        return CopyMode(str(mode).upper())
    except ValueError as exc:
        raise InvalidArgument(
            f"mode 只能是 RERESOLVE 或 PINNED，得到 {mode!r}"
        ) from exc


def _normalize_ids(testpoint_ids: Sequence[str] | str) -> list[str]:
    """允许单字符串或序列；拒绝空 id。"""

    raw = [testpoint_ids] if isinstance(testpoint_ids, str) else list(testpoint_ids)
    ids: list[str] = []
    for testpoint_id in raw:
        if not isinstance(testpoint_id, str) or not testpoint_id:
            raise InvalidArgument("testpoint_id 必须是非空字符串")
        ids.append(testpoint_id)
    return ids


def _normalize_pins(pin_versions: dict[str, int] | None) -> dict[str, int]:
    if pin_versions is None:
        return {}
    if not isinstance(pin_versions, dict):
        raise InvalidArgument("pin_versions 必须是 {testpoint_id: 修订号}")

    pins: dict[str, int] = {}
    for testpoint_id, value in pin_versions.items():
        if not isinstance(testpoint_id, str) or not testpoint_id:
            raise InvalidArgument("pin_versions 的键必须是非空字符串")
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise InvalidArgument(
                f"pin_versions[{testpoint_id!r}] 的修订号必须 >= 1"
            )
        pins[testpoint_id] = value
    return pins

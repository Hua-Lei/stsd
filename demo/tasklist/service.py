"""服务层：无状态函数式的用例编排。

职责边界：
- 开事务、取数据、调用领域规则、写回；
- 不实现存储细节（repo 负责），不实现版本规则（用例库 Port 负责）。

所有方法第一个参数都是 ``tasklist_id``（create 除外），因为调用方
（无论 LLM 还是前端）不会长期持有对象引用，只能凭标识定位。
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from .errors import ErrorCode, TaskListError
from .hashing import compute_list_content_hash
from .models import CaseRef, CopyMode, ItemRecord, Status, TaskListRecord
from .ports import CaseLibraryPort, DurationStat, RunHistoryPort
from .repo import TaskListRepo, utc_now

# 提示 flag
FLAG_PINNED = "PINNED"
FLAG_SUPERSEDED = "SUPERSEDED"
FLAG_DEPRECATED = "DEPRECATED_REF"
FLAG_STALE = "STALE_EXPERIENCE"
FLAG_DURATION_UNKNOWN = "DURATION_UNKNOWN"
FLAG_CONTENT_CHANGED = "CASE_CONTENT_CHANGED"
FLAG_VERSION_MISSING = "VERSION_NOT_FOUND"

_REJECT_MESSAGES = {
    ErrorCode.DUPLICATE.value: "该用例已在清单中",
    ErrorCode.CASE_NOT_FOUND.value: "用例库中无此用例",
    ErrorCode.NO_APPLICABLE_VERSION.value: "目标版本下无适用版本",
    ErrorCode.VERSION_NOT_FOUND.value: "指定版本不存在",
    ErrorCode.DEPRECATED_REF.value: "引用了已废弃版本",
}


def _reject(case_id: str, code: str, message: str | None = None) -> dict[str, str]:
    return {
        "use_case_id": case_id,
        "code": code,
        "message": message or _REJECT_MESSAGES.get(code, code),
    }


class TaskListService:
    def __init__(
        self,
        repo: TaskListRepo,
        case_library: CaseLibraryPort,
        run_history: RunHistoryPort | None = None,
    ) -> None:
        self.repo = repo
        self.case_library = case_library
        self.run_history = run_history

    # ==================================================================
    # 生命周期
    # ==================================================================
    def create_list(
        self,
        target_software_release_version: int | None,
        tasklist_title: str | None = None,
    ) -> dict[str, Any]:
        target = self._check_target(target_software_release_version)
        title = self._normalize_title(tasklist_title)
        now = utc_now()
        record = TaskListRecord(
            tasklist_id=self._new_id(),
            target_software_release_version=target,
            status=Status.DRAFT,
            rev=0,
            tasklist_title=title,
            content_hash=None,
            created_at=now,
            updated_at=now,
        )
        self.repo.insert_tasklist(record)
        return {"tasklist_id": record.tasklist_id, "status": Status.DRAFT.value}

    def copy_list(
        self,
        source_tasklist_id: str,
        target_software_release_version: int | None,
        mode: str | CopyMode = CopyMode.RERESOLVE,
    ) -> dict[str, Any]:
        target = self._check_target(target_software_release_version)
        try:
            copy_mode = CopyMode(str(mode).upper())
        except ValueError as exc:
            raise TaskListError(
                ErrorCode.INVALID_ARGUMENT,
                f"mode 只能是 RERESOLVE 或 PINNED，得到 {mode!r}",
            ) from exc

        with self.repo.transaction():
            source = self._require(source_tasklist_id, for_update=True)
            source_items = self.repo.list_items(source_tasklist_id)
            accepted: list[CaseRef] = []
            rejected: list[dict[str, str]] = []
            warnings: list[dict[str, str]] = []

            if copy_mode is CopyMode.RERESOLVE:
                # 必须在复制这一刻解析并写入草稿，不能推迟到锁定
                ids = [item.use_case_id for item in source_items]
                outcomes = self.case_library.resolve_versions(ids, target)
                for item in source_items:
                    outcome = outcomes.get(item.use_case_id)
                    if outcome is None or not outcome.ok:
                        code = outcome.code if outcome is not None else ErrorCode.CASE_NOT_FOUND.value
                        rejected.append(_reject(item.use_case_id, code))
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
            else:
                refs = [(item.use_case_id, item.use_case_version) for item in source_items]
                version_map = self.case_library.get_versions(refs)
                briefs = self.case_library.get_case_briefs(
                    [item.use_case_id for item in source_items]
                )
                for item in source_items:
                    if item.use_case_id not in briefs:
                        rejected.append(_reject(item.use_case_id, ErrorCode.CASE_NOT_FOUND.value))
                        continue
                    found = version_map.get((item.use_case_id, item.use_case_version))
                    if found is None:
                        rejected.append(_reject(item.use_case_id, ErrorCode.VERSION_NOT_FOUND.value))
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

            now = utc_now()
            new_record = TaskListRecord(
                tasklist_id=self._new_id(),
                target_software_release_version=target,
                status=Status.DRAFT,
                rev=0,
                tasklist_title=source.tasklist_title,
                content_hash=None,
                created_at=now,
                updated_at=now,
                source_tasklist_id=source.tasklist_id,
                copy_mode=copy_mode,
            )
            self.repo.insert_tasklist(new_record)
            self.repo.bulk_insert_items(new_record.tasklist_id, accepted, start_seq=1)

        return {
            "tasklist_id": new_record.tasklist_id,
            "status": Status.DRAFT.value,
            "source_tasklist_id": source.tasklist_id,
            "mode": copy_mode.value,
            "item_count": len(accepted),
            "rejected": rejected,
            "warnings": warnings,
        }

    def lock_list(self, tasklist_id: str) -> dict[str, Any]:
        with self.repo.transaction():
            record = self._require(tasklist_id, for_update=True)
            if not record.is_editable:
                raise TaskListError(
                    ErrorCode.LIST_LOCKED, "清单已锁定，不能重复锁定",
                    tasklist_id=tasklist_id,
                )

            items = self.repo.list_items(tasklist_id)
            if not items:
                raise TaskListError(
                    ErrorCode.EMPTY_LIST, "空清单不允许锁定",
                    tasklist_id=tasklist_id,
                )

            refs = [(item.use_case_id, item.use_case_version) for item in items]
            version_map = self.case_library.get_versions(refs)

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

            content_hash = compute_list_content_hash(
                record.target_software_release_version,
                [(item.use_case_id, item.use_case_version, item.content_hash) for item in items],
            )
            self.repo.save_status(tasklist_id, Status.LOCKED)
            self.repo.save_content_hash(tasklist_id, content_hash)

        return {
            "tasklist_id": tasklist_id,
            "content_hash": content_hash,
            "item_count": len(items),
        }

    # ==================================================================
    # 编辑（仅 DRAFT）
    # ==================================================================
    def add_items(
        self,
        tasklist_id: str,
        use_case_ids: Sequence[str] | str,
        pin_versions: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        ids = self._normalize_ids(use_case_ids)
        pins = self._normalize_pins(pin_versions)

        with self.repo.transaction():
            record = self._require(tasklist_id, for_update=True)
            self._require_draft(record)
            if not ids:
                return {"tasklist_id": tasklist_id, "rev": record.rev,
                        "added": [], "rejected": [], "warnings": []}

            existing = {item.use_case_id for item in self.repo.list_items(tasklist_id)}
            briefs = self.case_library.get_case_briefs(ids)
            resolve_ids = [cid for cid in ids if cid not in existing and cid not in pins]
            outcomes = self.case_library.resolve_versions(
                resolve_ids, record.target_software_release_version
            )
            pin_refs = [(cid, pins[cid]) for cid in ids
                        if cid not in existing and cid in pins]
            pinned_versions = self.case_library.get_versions(pin_refs)

            accepted: list[CaseRef] = []
            rejected: list[dict[str, str]] = []
            warnings: list[dict[str, str]] = []
            seen: set[str] = set()

            for case_id in ids:
                if case_id in seen or case_id in existing:
                    rejected.append(_reject(case_id, ErrorCode.DUPLICATE.value))
                elif case_id not in briefs:
                    rejected.append(_reject(case_id, ErrorCode.CASE_NOT_FOUND.value))
                elif case_id in pins:
                    found = pinned_versions.get((case_id, pins[case_id]))
                    if found is None:
                        rejected.append(
                            _reject(
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
                                {
                                    "use_case_id": case_id,
                                    "code": ErrorCode.DEPRECATED_REF.value,
                                    "message": _REJECT_MESSAGES[ErrorCode.DEPRECATED_REF.value],
                                }
                            )
                else:
                    outcome = outcomes.get(case_id)
                    if outcome is None or not outcome.ok:
                        code = outcome.code if outcome is not None else ErrorCode.CASE_NOT_FOUND.value
                        rejected.append(_reject(case_id, code))
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

            rev = record.rev
            if accepted:
                self.repo.bulk_insert_items(
                    tasklist_id, accepted, start_seq=self.repo.next_seq(tasklist_id)
                )
                rev = self.repo.bump_rev(tasklist_id)

        return {
            "tasklist_id": tasklist_id,
            "rev": rev,
            "added": [ref.to_dict() for ref in accepted],
            "rejected": rejected,
            "warnings": warnings,
        }

    def remove_items(
        self, tasklist_id: str, use_case_ids: Sequence[str] | str
    ) -> dict[str, Any]:
        ids = self._normalize_ids(use_case_ids)
        with self.repo.transaction():
            record = self._require(tasklist_id, for_update=True)
            self._require_draft(record)
            existing = {item.use_case_id for item in self.repo.list_items(tasklist_id)}
            removed = list(dict.fromkeys(cid for cid in ids if cid in existing))
            not_found = list(dict.fromkeys(cid for cid in ids if cid not in existing))
            rev = record.rev
            if removed:
                self.repo.delete_items(tasklist_id, removed)
                rev = self.repo.bump_rev(tasklist_id)

        return {
            "tasklist_id": tasklist_id,
            "rev": rev,
            "removed": removed,
            "not_found": not_found,
        }

    def rename_list(self, tasklist_id: str, tasklist_title: str | None) -> dict[str, Any]:
        """元数据修改：锁定后仍可改，且不影响 content_hash / rev。"""

        self._require(tasklist_id)
        title = self._normalize_title(tasklist_title)
        self.repo.update_title(tasklist_id, title)
        return {"tasklist_id": tasklist_id, "tasklist_title": title}

    # ==================================================================
    # 读取
    # ==================================================================
    def get_tasklist(self, tasklist_id: str) -> dict[str, Any]:
        """只读接口（design.md 第四节）：与 preview 共用条目投影。

        resolved_version 是读取时关联出的展示信息，不写回清单；
        清单的权威版本始终是 case_ref 里的 (use_case_id, use_case_version)。
        """

        record = self._require(tasklist_id)
        items = self.repo.list_items(tasklist_id)
        views, _, _ = self._project(record, items, diagnostic=False, resolve=True)
        return {
            **record.to_dict(),
            "item_count": len(items),
            "items": views,
        }

    # design_1.md 沿用了 get_list 这个名字；保留别名，两个名字行为一致
    get_list = get_tasklist

    def preview(
        self,
        tasklist_id: str,
        view: str = "full",
        page: int = 1,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        """只报告问题、不拦截；拦截留给 lock_list。无副作用，可反复调用。"""

        if view not in ("full", "summary"):
            raise TaskListError(
                ErrorCode.INVALID_ARGUMENT, "view 只能是 full 或 summary"
            )
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise TaskListError(ErrorCode.INVALID_ARGUMENT, "page 必须是 >= 1 的整数")
        if page_size is not None and (
            isinstance(page_size, bool) or not isinstance(page_size, int) or page_size < 1
        ):
            raise TaskListError(ErrorCode.INVALID_ARGUMENT, "page_size 必须是 >= 1 的整数")

        record = self._require(tasklist_id)
        items = self.repo.list_items(tasklist_id)
        views, diagnostics, durations = self._project(
            record, items, diagnostic=True, resolve=True
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

        summary = self._summary(items, durations)
        result: dict[str, Any] = {
            "tasklist_id": record.tasklist_id,
            "status": record.status.value,
            "target_software_release_version": record.target_software_release_version,
            "tasklist_title": record.tasklist_title,
            "rev": record.rev,
            "summary": summary,
            "diagnostics": diagnostics,
        }

        if view == "summary":
            return result

        start = (page - 1) * page_size if page_size else 0
        page_items = views[start:start + page_size] if page_size else views
        result.update({
            "page": page,
            "page_size": page_size,
            "items": page_items,
        })
        return result

    def list_lists(self, status: str | None = None) -> list[dict[str, Any]]:
        records = self.repo.list_tasklists()
        if status is not None:
            wanted = str(status).upper()
            records = [r for r in records if r.status.value == wanted]
        return [r.to_dict() for r in records]

    # ==================================================================
    # 与执行器协作：把锁定清单导出为 TestCase JSON（可选能力）
    # ==================================================================
    def export_cases(self, tasklist_id: str) -> list[dict[str, Any]]:
        """按 seq 顺序返回用例正文，可直接交给 ``demo.executor.CaseExecutor``。

        只要求锁定清单：状态一旦 LOCKED，条目与指纹都不会再变，
        执行的就是被审核过的那一份内容。
        """

        record = self._require(tasklist_id)
        if record.status is not Status.LOCKED:
            raise TaskListError(
                ErrorCode.LIST_NOT_LOCKED, "只有锁定后的清单才能导出执行",
                tasklist_id=tasklist_id,
            )

        getter = getattr(self.case_library, "get_case_payload", None)
        if not callable(getter):
            raise TaskListError(
                ErrorCode.EXPORT_UNSUPPORTED,
                "当前用例库适配器不提供用例正文，无法导出执行输入",
                tasklist_id=tasklist_id,
            )

        payloads: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        for item in self.repo.list_items(tasklist_id):
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

    # ==================================================================
    # 内部：投影、汇总、校验
    # ==================================================================
    def _project(
        self,
        record: TaskListRecord,
        items: Sequence[ItemRecord],
        *,
        diagnostic: bool,
        resolve: bool,
    ) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, DurationStat]]:
        """preview 与 get_list 共用的条目投影。

        共同部分：seq / case_ref / title / requirement_ids / risk_level。
        ``resolve=True`` 时额外计算 resolved_version（preview 的诊断需要）；
        get_list 不解析版本，只读回已固定的引用。
        ``diagnostic=True`` 时再附加 last_run、flags 与诊断。
        """

        ids = [item.use_case_id for item in items]
        refs = [(item.use_case_id, item.use_case_version) for item in items]
        briefs = self.case_library.get_case_briefs(ids) if ids else {}
        outcomes = (
            self.case_library.resolve_versions(ids, record.target_software_release_version)
            if resolve and ids else {}
        )
        versions = self.case_library.get_versions(refs) if refs else {}

        last_results: dict[str, Any] = {}
        durations: dict[str, DurationStat] = {}
        if diagnostic and self.run_history is not None and ids:
            last_results = self.run_history.get_last_results(ids)
            durations = self.run_history.get_duration_stats(ids)

        views: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        for item in items:
            stored = versions.get((item.use_case_id, item.use_case_version))
            outcome = outcomes.get(item.use_case_id)
            resolved_version = (
                outcome.version.use_case_version
                if outcome is not None and outcome.ok else None
            )
            brief = briefs.get(item.use_case_id)

            view: dict[str, Any] = {
                "seq": item.seq,
                "case_ref": item.case_ref.to_dict(),
                "title": brief.title if brief is not None
                         else (stored.title if stored is not None else None),
                "requirement_ids": list(brief.requirement_ids) if brief is not None
                                   else (list(stored.requirement_ids) if stored is not None else []),
                "risk_level": brief.risk_level if brief is not None
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
                errors.append({
                    "code": ErrorCode.VERSION_NOT_FOUND.value,
                    "use_case_id": item.use_case_id,
                    "message": "清单引用的版本在用例库中不存在",
                })
            else:
                if stored.status == "deprecated":
                    flags.append(FLAG_DEPRECATED)
                    warnings.append({
                        "code": ErrorCode.DEPRECATED_REF.value,
                        "use_case_id": item.use_case_id,
                        "message": _REJECT_MESSAGES[ErrorCode.DEPRECATED_REF.value],
                    })
                if stored.content_hash != item.content_hash:
                    flags.append(FLAG_CONTENT_CHANGED)
                    errors.append({
                        "code": ErrorCode.CASE_CONTENT_CHANGED.value,
                        "use_case_id": item.use_case_id,
                        "message": "同版本用例内容指纹已变化，锁定会被拒绝",
                    })

            if outcome is not None and not outcome.ok:
                flags.append(outcome.code or ErrorCode.NO_APPLICABLE_VERSION.value)
                errors.append({
                    "code": outcome.code or ErrorCode.NO_APPLICABLE_VERSION.value,
                    "use_case_id": item.use_case_id,
                    "message": _REJECT_MESSAGES.get(
                        outcome.code or "", "目标版本下无法解析该用例"
                    ),
                })
            elif (
                resolved_version is not None
                and resolved_version != item.use_case_version
            ):
                # design.md 第四节：resolved_version 与 usecase_version 不相等就提示，
                # PINNED 条目同样提示，只是额外带 PINNED 标记供审核区分
                flags.append(FLAG_SUPERSEDED)
                warnings.append({
                    "code": ErrorCode.SUPERSEDED.value,
                    "use_case_id": item.use_case_id,
                    "message": f"存在更新的适用版本 v{resolved_version}",
                })

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
                    warnings.append({
                        "code": FLAG_STALE,
                        "use_case_id": item.use_case_id,
                        "message": "上次结果来自不同版本，不能作为跳过依据",
                    })
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

    @staticmethod
    def _summary(
        items: Sequence[ItemRecord], durations: dict[str, DurationStat]
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

    # ------------------------------------------------------------------ 校验
    def _require(
        self, tasklist_id: str, *, for_update: bool = False
    ) -> TaskListRecord:
        record = (
            self.repo.get_for_update(tasklist_id)
            if for_update else self.repo.get_tasklist(tasklist_id)
        )
        if record is None:
            raise TaskListError(
                ErrorCode.LIST_NOT_FOUND, "清单不存在", tasklist_id=tasklist_id
            )
        return record

    @staticmethod
    def _require_draft(record: TaskListRecord) -> None:
        if not record.is_editable:
            raise TaskListError(
                ErrorCode.LIST_LOCKED, "清单已锁定，不能编辑用例",
                tasklist_id=record.tasklist_id,
            )

    @staticmethod
    def _check_target(target: int | None) -> int:
        if target is None:
            raise TaskListError(
                ErrorCode.TARGET_MISSING, "创建清单时必须指定目标软件版本"
            )
        if isinstance(target, bool) or not isinstance(target, int) or target < 1:
            raise TaskListError(
                ErrorCode.INVALID_ARGUMENT, "目标软件版本必须是 >= 1 的整数"
            )
        return target

    @staticmethod
    def _normalize_title(title: str | None) -> str | None:
        if title is None:
            return None
        if not isinstance(title, str):
            raise TaskListError(ErrorCode.INVALID_ARGUMENT, "清单名称必须是字符串")
        stripped = title.strip()
        return stripped or None

    @staticmethod
    def _normalize_ids(use_case_ids: Sequence[str] | str) -> list[str]:
        raw = [use_case_ids] if isinstance(use_case_ids, str) else list(use_case_ids)
        ids: list[str] = []
        for case_id in raw:
            if not isinstance(case_id, str) or not case_id:
                raise TaskListError(
                    ErrorCode.INVALID_ARGUMENT, "use_case_id 必须是非空字符串"
                )
            ids.append(case_id)
        return ids

    @staticmethod
    def _normalize_pins(pin_versions: dict[str, int] | None) -> dict[str, int]:
        if pin_versions is None:
            return {}
        if not isinstance(pin_versions, dict):
            raise TaskListError(
                ErrorCode.INVALID_ARGUMENT, "pin_versions 必须是 {use_case_id: version}"
            )
        pins: dict[str, int] = {}
        for case_id, version in pin_versions.items():
            if not isinstance(case_id, str) or not case_id:
                raise TaskListError(ErrorCode.INVALID_ARGUMENT, "pin_versions 的键必须是非空字符串")
            if isinstance(version, bool) or not isinstance(version, int) or version < 1:
                raise TaskListError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"pin_versions[{case_id!r}] 必须是 >= 1 的整数",
                )
            pins[case_id] = version
        return pins

    @staticmethod
    def _new_id() -> str:
        return "tl_" + uuid.uuid4().hex[:16]

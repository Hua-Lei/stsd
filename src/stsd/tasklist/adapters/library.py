"""把“字典/JSON 形式”的用例库适配成 ``TestPointLibraryPort``。

真实用例库只需要返回结构数据；本适配器在 TaskList 这一侧把它们转换成
``RevisionRecord``、``TestPointBrief`` 和 ``RevisionOutcome``。
``content_hash`` 不在这里计算，由 TaskList 在拿到 payload 后自行计算。
"""

from __future__ import annotations

import copy
from typing import Any, Mapping, Protocol, Sequence

from ..ports import (
    TestPointBrief,
    RevisionKey,
    RevisionOutcome,
    RevisionRecord,
)


class DictLibraryBackend(Protocol):
    """字典形式用例库需要提供的原始数据接口。"""

    def get_testpoint_briefs(
        self, testpoint_ids: Sequence[str]
    ) -> Mapping[str, Mapping[str, Any]]: ...

    def resolve_revisions(
        self, testpoint_ids: Sequence[str], project_version: str
    ) -> Mapping[str, Mapping[str, Any]]: ...

    def get_revisions(
        self, refs: Sequence[RevisionKey]
    ) -> Mapping[RevisionKey, Mapping[str, Any] | None]: ...

    def get_testpoint_payload(
        self, testpoint_id: str, revision_ver: int
    ) -> Any | None: ...


class DictTestPointLibraryAdapter:
    """实现 ``TestPointLibraryPort``，把后端字典转换成 TaskList 的 DTO。"""

    def __init__(self, backend: DictLibraryBackend) -> None:
        self._backend = backend

    # ------------------------------------------------------------------ Port
    def get_testpoint_briefs(
        self, testpoint_ids: Sequence[str]
    ) -> dict[str, TestPointBrief]:
        raw = self._backend.get_testpoint_briefs(testpoint_ids)
        return {
            str(testpoint_id): TestPointBrief(
                testpoint_id=str(testpoint_id),
                title=str(data["title"]),
            )
            for testpoint_id, data in raw.items()
        }

    def resolve_revisions(
        self, testpoint_ids: Sequence[str], project_version: str
    ) -> dict[str, RevisionOutcome]:
        raw = self._backend.resolve_revisions(
            testpoint_ids, project_version
        )
        outcomes: dict[str, RevisionOutcome] = {}
        for testpoint_id in dict.fromkeys(testpoint_ids):
            data = raw.get(testpoint_id)
            if data is None:
                outcomes[testpoint_id] = RevisionOutcome(
                    code="TESTPOINT_NOT_FOUND"
                )
                continue
            if not self._is_achieved(data):
                outcomes[testpoint_id] = RevisionOutcome(
                    code=str(data.get("code") or "TESTPOINT_NOT_FOUND")
                )
                continue
            outcomes[testpoint_id] = RevisionOutcome(
                revision=self._revision_from_dict(testpoint_id, data)
            )
        return outcomes

    def get_revisions(
        self, refs: Sequence[RevisionKey]
    ) -> dict[RevisionKey, RevisionRecord | None]:
        raw = self._backend.get_revisions(refs)
        result: dict[RevisionKey, RevisionRecord | None] = {}
        for ref in refs:
            data = raw.get(ref)
            if data is None or not self._is_achieved(data):
                result[ref] = None
                continue
            result[ref] = self._revision_from_dict(ref[0], data, ref[1])
        return result

    def get_testpoint_payload(
        self, testpoint_id: str, revision_ver: int
    ) -> Any | None:
        payload = self._backend.get_testpoint_payload(
            testpoint_id, revision_ver
        )
        return copy.deepcopy(payload) if payload is not None else None

    # ---------------------------------------------------------------- 内部
    @staticmethod
    def _is_achieved(data: Mapping[str, Any]) -> bool:
        if "is_achieved" not in data:
            raise ValueError("用例库返回缺少 is_achieved")
        return bool(data["is_achieved"])

    @staticmethod
    def _revision_from_dict(
        testpoint_id: str,
        data: Mapping[str, Any],
        revision: int | None = None,
    ) -> RevisionRecord:
        try:
            revision_ver = (
                int(data["revision_ver"])
                if revision is None
                else int(revision)
            )
            title = str(data["title"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"测试点 {testpoint_id!r} 的修订数据不完整: {data!r}"
            ) from exc
        return RevisionRecord(
            testpoint_id=str(testpoint_id),
            revision_ver=revision_ver,
            title=title,
        )

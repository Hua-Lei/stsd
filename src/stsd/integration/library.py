'''用例库读接口的跨模块适配。

一份适配给 TaskList（``TestPointLibraryPort``），一份给执行器（修订与
文件读取）。两边都只调用用例库的公开读接口，不引用它的聚合或仓储。
'''

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from stsd.executor.records import RevisionDetail
from stsd.library import (
    GetImplementationFiles,
    GetTestPointDetail,
    LibraryApp,
    LibraryError,
    RevisionNotFound,
)
from stsd.tasklist.ports import (
    RevisionKey,
    RevisionOutcome,
    RevisionRecord,
    TestPointBrief,
    TestPointLibraryPort,
)


class LibraryTestPointAdapter(TestPointLibraryPort):
    def __init__(self, library: LibraryApp) -> None:
        self._library = library

    def resolve_revisions(
        self, testpoint_ids: Sequence[str], project_version: str
    ) -> dict[str, RevisionOutcome]:
        outcomes: dict[str, RevisionOutcome] = {}
        for testpoint_id in dict.fromkeys(testpoint_ids):
            try:
                detail = self._library.get_testpoint_detail(
                    GetTestPointDetail(testpoint_id=testpoint_id)
                )
            except RevisionNotFound:
                outcomes[testpoint_id] = RevisionOutcome(
                    code='NO_APPLICABLE_REVISION'
                )
                continue
            except LibraryError:
                outcomes[testpoint_id] = RevisionOutcome(
                    code='TESTPOINT_NOT_FOUND'
                )
                continue
            if detail.testpoint_deleted:
                outcomes[testpoint_id] = RevisionOutcome(
                    code='TESTPOINT_NOT_FOUND'
                )
                continue
            outcomes[testpoint_id] = RevisionOutcome(
                revision=RevisionRecord(
                    testpoint_id=detail.testpoint_id,
                    revision_ver=detail.revision_ver,
                    title=detail.name,
                )
            )
        return outcomes

    def get_revisions(
        self, refs: Sequence[RevisionKey]
    ) -> dict[RevisionKey, RevisionRecord | None]:
        revisions: dict[RevisionKey, RevisionRecord | None] = {}
        for testpoint_id, revision_ver in refs:
            try:
                detail = self._library.get_testpoint_detail(
                    GetTestPointDetail(
                        testpoint_id=testpoint_id,
                        revision_ver=revision_ver,
                    )
                )
            except LibraryError:
                revisions[(testpoint_id, revision_ver)] = None
                continue
            revisions[(testpoint_id, revision_ver)] = RevisionRecord(
                testpoint_id=detail.testpoint_id,
                revision_ver=detail.revision_ver,
                title=detail.name,
            )
        return revisions

    def get_testpoint_briefs(
        self, testpoint_ids: Sequence[str]
    ) -> dict[str, TestPointBrief]:
        briefs: dict[str, TestPointBrief] = {}
        for testpoint_id in dict.fromkeys(testpoint_ids):
            try:
                detail = self._library.get_testpoint_detail(
                    GetTestPointDetail(testpoint_id=testpoint_id)
                )
            except LibraryError:
                continue
            if detail.testpoint_deleted:
                continue
            briefs[testpoint_id] = TestPointBrief(
                testpoint_id=detail.testpoint_id,
                title=detail.name,
            )
        return briefs

    def get_testpoint_payload(
        self, testpoint_id: str, revision_ver: int
    ) -> Any | None:
        try:
            detail = self._library.get_testpoint_detail(
                GetTestPointDetail(
                    testpoint_id=testpoint_id, revision_ver=revision_ver
                )
            )
        except LibraryError:
            return None
        if detail.implementation is None:
            return None
        return detail.implementation.to_dict()


class LibraryRevisionReader:
    '''执行器读取修订声明和实现文件。'''

    def __init__(self, library: LibraryApp) -> None:
        self._library = library

    def get_revision(
        self, testpoint_id: str, revision_ver: int
    ) -> RevisionDetail | None:
        try:
            detail = self._library.get_testpoint_detail(
                GetTestPointDetail(
                    testpoint_id=testpoint_id, revision_ver=revision_ver
                )
            )
        except LibraryError:
            return None
        return RevisionDetail(
            testpoint_id=detail.testpoint_id,
            revision_ver=detail.revision_ver,
            project_id=detail.project_id,
            status=detail.status,
            implementation=detail.implementation,
            testpoint_deleted=detail.testpoint_deleted,
        )

    def get_files(
        self, testpoint_id: str, revision_ver: int
    ) -> Mapping[str, str] | None:
        try:
            return self._library.get_implementation_files(
                GetImplementationFiles(
                    testpoint_id=testpoint_id, revision_ver=revision_ver
                )
            )
        except LibraryError:
            return None

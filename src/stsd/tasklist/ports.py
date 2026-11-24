"""任务清单依赖的外部端口（Port）。

任务清单不直连用例库或执行结果表，只认接口。这里使用用例库的术语：
TestPoint / Revision；软件发布版本统一称为 ``project_version``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

# 测试点修订的完整标识：(testpoint_id, revision_ver)
RevisionKey = tuple[str, int]


# ---------------------------------------------------------------------------
# Access 端口
# ---------------------------------------------------------------------------
class ProjectVersionLookup(Protocol):
    """向 Access 确认“某项目有没有某个 proj_ver”。

    端口只读不可变事实，必须在任务清单写操作之前调用；实现方自持只读
    事务，不参与任务清单的事务。
    """

    def project_version_exists(self, project_id: str, proj_ver: str) -> bool:
        '''项目版本存在返回 True，否则返回 False。'''
        ...


# ---------------------------------------------------------------------------
# 用例库端口
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RevisionRecord:
    """某个测试点的一条修订。"""

    testpoint_id: str
    revision_ver: int
    title: str

    @property
    def revision_key(self) -> RevisionKey:
        return (self.testpoint_id, self.revision_ver)


@dataclass(frozen=True)
class TestPointBrief:
    """测试点的展示信息。"""

    testpoint_id: str
    title: str


@dataclass(frozen=True)
class RevisionOutcome:
    """修订解析结果：要么拿到修订，要么拿到失败码。"""

    revision: RevisionRecord | None = None
    code: str | None = None  # TESTPOINT_NOT_FOUND | NO_APPLICABLE_REVISION

    @property
    def ok(self) -> bool:
        return self.revision is not None


class TestPointLibraryPort(Protocol):
    """用例库对外提供的只读查询能力。"""

    def resolve_revisions(
        self, testpoint_ids: Sequence[str], project_version: str
    ) -> dict[str, RevisionOutcome]:
        """解析每个测试点应使用的修订。

        真实用例库当前返回最新已冻结修订；不存在返回 ``TESTPOINT_NOT_FOUND``，
        没有可用修订返回 ``NO_APPLICABLE_REVISION``。
        """
        ...

    def get_revisions(
        self, refs: Sequence[RevisionKey]
    ) -> dict[RevisionKey, RevisionRecord | None]:
        """按 ``(testpoint_id, revision_ver)`` 精确取修订；不存在返回 None。"""
        ...

    def get_testpoint_briefs(
        self, testpoint_ids: Sequence[str]
    ) -> dict[str, TestPointBrief]:
        """返回存在的测试点的展示信息；不存在的 id 不放入结果。"""
        ...

    def get_testpoint_payload(
        self, testpoint_id: str, revision_ver: int
    ) -> Any | None:
        """按 ``testpoint_id + revision_ver`` 取实现正文。

        返回 None 表示测试点或修订不存在。正文的格式暂不约定；TaskList
        只负责取回并计算内容指纹，执行器是否能执行由执行器适配层决定。
        """
        ...


# ---------------------------------------------------------------------------
# 执行结果端口
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LastRun:
    """某个测试点最近一次执行结果。"""

    revision_ver: int
    content_hash: str | None
    status: str  # 与执行器一致：passed | failed | error
    run_at: str
    duration_ms: int | None = None


@dataclass(frozen=True)
class DurationStat:
    """窗口内的耗时统计，用于 preview.summary.est_total_sec。"""

    median_ms: float
    samples: int = 0


class RunHistoryPort(Protocol):
    """执行结果只读端口。任务清单永远不写它。"""

    def get_last_results(
        self, testpoint_ids: Sequence[str]
    ) -> dict[str, LastRun | None]:
        ...

    def get_duration_stats(
        self, testpoint_ids: Sequence[str], window_days: int = 30
    ) -> dict[str, DurationStat]:
        ...

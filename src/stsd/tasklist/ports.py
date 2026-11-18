"""任务清单依赖的外部端口（Port）。

任务清单不直连用例库或执行结果表，只认接口。因此这里只定义 ``Protocol``
与 DTO，不包含任何存储实现；真实实现放在 ``tasklist.adapters`` 或其它模块，
任务清单不需要知道对面是 JSON、SQLite 还是 HTTP。

依赖方向（与控制流相反）：

    用例库 / 执行结果  ──实现──>  Port  <──调用──  任务清单

端口是“应用层拥有的接口”，不是适配器定义的接口。服务层只依赖这里的形状，
测试因此可以直接注入内存实现，而不用启动数据库或网络。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Sequence

CaseStatus = Literal["active", "deprecated"]


# ---------------------------------------------------------------------------
# 用例库端口
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class VersionRecord:
    """某个用例某个版本的完整坐标。

    ``release_order`` 是软件版本的单调递增整数；``use_case_version`` 是
    用例自身的版本号。多数情况下两者相同，但分开保存可以让“同一版本
    在不同软件版本下可用”这类扩展不必改协议。
    """

    use_case_id: str
    use_case_version: int
    release_order: int
    content_hash: str
    title: str
    requirement_ids: tuple[str, ...] = ()
    risk_level: str | None = None
    status: CaseStatus = "active"


@dataclass(frozen=True)
class CaseBrief:
    """用例的展示信息（人工/LLM 决策时需要的最小描述）。"""

    use_case_id: str
    title: str
    requirement_ids: tuple[str, ...] = ()
    risk_level: str | None = None


@dataclass(frozen=True)
class ResolveOutcome:
    """版本解析结果：要么拿到版本，要么拿到失败码。"""

    version: VersionRecord | None = None
    code: str | None = None  # CASE_NOT_FOUND | NO_APPLICABLE_VERSION

    @property
    def ok(self) -> bool:
        return self.version is not None


class CaseLibraryPort(Protocol):
    """用例库只暴露任务清单真正需要的三个能力。"""

    def resolve_versions(
        self, case_ids: Sequence[str], target_order: int
    ) -> dict[str, ResolveOutcome]:
        """按 design 第四节规则批量解析版本。

        规则：在 ``status == "active"`` 且 ``release_order <= target`` 的版本中取
        ``release_order`` 最大者；集合为空返回 ``NO_APPLICABLE_VERSION``，
        用例不存在返回 ``CASE_NOT_FOUND``。不得回退到最早版本。
        """
        ...

    def get_versions(
        self, refs: Sequence[tuple[str, int]]
    ) -> dict[tuple[str, int], VersionRecord | None]:
        """按 ``(use_case_id, use_case_version)`` 精确取版本；不存在返回 None。"""
        ...

    def get_case_briefs(self, case_ids: Sequence[str]) -> dict[str, CaseBrief]:
        """返回存在的用例的展示信息；不存在的 id 不出现在结果里。"""
        ...


# ---------------------------------------------------------------------------
# 执行结果端口
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LastRun:
    """某条用例最近一次执行结果。

    必须带 ``use_case_version`` 与 ``content_hash``：否则“上次通过了”会被
    错误地当作“本轮可以不测”。判定跳过依据是“同版本或内容未变且通过”。
    """

    use_case_version: int
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
        self, case_ids: Sequence[str]
    ) -> dict[str, LastRun | None]:
        ...

    def get_duration_stats(
        self, case_ids: Sequence[str], window_days: int = 30
    ) -> dict[str, DurationStat]:
        ...

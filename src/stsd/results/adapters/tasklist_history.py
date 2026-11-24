"""把结果库适配成任务清单的 RunHistoryPort。"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from stsd.tasklist import DurationStat, LastRun

from ..service_layer.unit_of_work import AbstractUnitOfWork as ResultUoW


class TaskListHistoryAdapter:
    """把 Results 的最近结果适配成 TaskList 的 RunHistoryPort。

    只读：tasklist preview 调用时不能写结果库。
    """

    def __init__(self, uow_factory: Callable[[], ResultUoW]) -> None:
        self._uow_factory = uow_factory

    def get_last_results(
        self, testpoint_ids: Sequence[str]
    ) -> dict[str, LastRun | None]:
        """每个 case 的最近一次结果；没有执行记录返回 None。"""

        with self._uow_factory() as uow:
            latest = uow.runs.latest_results(testpoint_ids)
        return {
            testpoint_id: (
                LastRun(
                    revision_ver=case.revision_ver,
                    content_hash=case.content_hash,
                    status=case.status.value,
                    run_at=case.finished_at.isoformat(),
                    duration_ms=int(case.duration_ms),
                )
                if (case := latest.get(testpoint_id)) is not None
                else None
            )
            for testpoint_id in dict.fromkeys(testpoint_ids)
        }

    def get_duration_stats(
        self, testpoint_ids: Sequence[str], window_days: int = 30
    ) -> dict[str, DurationStat]:
        """用最近一次执行耗时作为简单统计；没有记录时 samples=0。"""

        with self._uow_factory() as uow:
            latest = uow.runs.latest_results(testpoint_ids)
        return {
            testpoint_id: (
                DurationStat(median_ms=float(case.duration_ms), samples=1)
                if (case := latest.get(testpoint_id)) is not None
                else DurationStat(median_ms=0.0, samples=0)
            )
            for testpoint_id in dict.fromkeys(testpoint_ids)
        }

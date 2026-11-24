"""RunRecord / TestPointResult 仓储。"""

from __future__ import annotations

from typing import Protocol, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, lazyload

from ..domain.model import RunRecord, TestPointResult
from ..domain.errors import RunNotFound
from .orm import runs, testpoint_results


class RunRepository(Protocol):
    """结果模块需要的读写接口；具体实现见 SqlAlchemyRunRepository。"""

    @property
    def proj_id(self) -> str: ...

    def get(self, run_id: str) -> RunRecord | None: ...
    def add(self, run: RunRecord) -> None: ...
    def list_runs(self, *, tasklist_id: str | None = None, limit: int = 50) -> list[RunRecord]: ...
    def latest_results(self, testpoint_ids: Sequence[str]) -> dict[str, TestPointResult]: ...


class SqlAlchemyRunRepository:
    """按 proj_id 隔离的 RunRecord 仓储；不 commit，事务由 UoW 负责。"""

    def __init__(self, session: Session, proj_id: str) -> None:
        self._session = session
        self._proj_id = proj_id

    @property
    def proj_id(self) -> str:
        return self._proj_id

    # ------------------------------------------------------------------ RunRecord
    def get(self, run_id: str) -> RunRecord | None:
        """读取 RunRecord 及完整结果；不属于当前项目视为不存在。"""

        run = self._session.get(RunRecord, run_id)
        if run is None or run.proj_id != self._proj_id:
            return None
        return run

    def add(self, run: RunRecord) -> None:
        if run.proj_id != self._proj_id:
            raise RunNotFound(run.run_id)
        self._session.add(run)
        self._session.flush()

    def list_runs(self, *, tasklist_id: str | None = None, limit: int = 50) -> list[RunRecord]:
        """按开始时间倒序列出 RunRecord；默认不加载逐条结果。"""

        stmt = select(RunRecord).where(runs.c.proj_id == self._proj_id)
        if tasklist_id is not None:
            stmt = stmt.where(runs.c.tasklist_id == tasklist_id)
        stmt = stmt.order_by(runs.c.started_at.desc()).limit(max(1, limit))
        # 列表页只读 summary，不主动加载逐条结果和步骤证据。
        stmt = stmt.options(lazyload(RunRecord.results))
        return list(self._session.scalars(stmt))

    # ------------------------------------------------------------ 结果查询
    def latest_results(self, testpoint_ids: Sequence[str]) -> dict[str, TestPointResult]:
        """每个 testpoint_id 取最近一次结果，供 tasklist preview/回归建议。"""

        ids = list(dict.fromkeys(testpoint_ids))
        if not ids:
            return {}
        stmt = (
            select(TestPointResult)
            .join(runs, testpoint_results.c.run_id == runs.c.run_id)
            .where(runs.c.proj_id == self._proj_id,
                   testpoint_results.c.testpoint_id.in_(ids))
            .order_by(runs.c.started_at.desc(), testpoint_results.c.seq)
        )
        latest: dict[str, TestPointResult] = {}
        for result in self._session.scalars(stmt):
            latest.setdefault(result.testpoint_id, result)
        return latest

"""SQLite 持久化层：

这一层只做存取，不做业务判断（判重、resolve、锁定时校验都在 service）。
写操作由 service 用 ``with repo.transaction():`` 包起来，保证锁定时
“校验 + 写状态 + 写指纹”是一个原子动作。

SQLite 没有 ``SELECT ... FOR UPDATE``，这里用 ``BEGIN IMMEDIATE``
在事务开始时就拿到写锁，语义上等价于“读清单时加锁”。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .models import CaseRef, CopyMode, ItemRecord, Status, TaskListRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasklists (
    tasklist_id                     TEXT PRIMARY KEY,
    target_software_release_version INTEGER NOT NULL,
    status                          TEXT NOT NULL CHECK (status IN ('DRAFT', 'LOCKED')),
    rev                             INTEGER NOT NULL DEFAULT 0,
    tasklist_title                  TEXT,
    content_hash                    TEXT,
    created_at                      TEXT NOT NULL,
    updated_at                      TEXT NOT NULL,
    source_tasklist_id              TEXT,
    copy_mode                       TEXT
);

CREATE TABLE IF NOT EXISTS tasklist_items (
    tasklist_id      TEXT NOT NULL,
    seq              INTEGER NOT NULL,
    use_case_id      TEXT NOT NULL,
    use_case_version INTEGER NOT NULL,
    content_hash     TEXT NOT NULL,
    pinned           INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tasklist_id, use_case_id),
    UNIQUE (tasklist_id, seq),
    FOREIGN KEY (tasklist_id) REFERENCES tasklists (tasklist_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tasklist_items_list_seq
    ON tasklist_items (tasklist_id, seq);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _tasklist_from_row(row: sqlite3.Row) -> TaskListRecord:
    return TaskListRecord(
        tasklist_id=row["tasklist_id"],
        target_software_release_version=row["target_software_release_version"],
        status=Status(row["status"]),
        rev=row["rev"],
        tasklist_title=row["tasklist_title"],
        content_hash=row["content_hash"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        source_tasklist_id=row["source_tasklist_id"],
        copy_mode=CopyMode(row["copy_mode"]) if row["copy_mode"] else None,
    )


def _item_from_row(row: sqlite3.Row) -> ItemRecord:
    return ItemRecord(
        seq=row["seq"],
        case_ref=CaseRef(
            use_case_id=row["use_case_id"],
            use_case_version=row["use_case_version"],
            content_hash=row["content_hash"],
            pinned=bool(row["pinned"]),
        ),
    )


class TaskListRepo:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(str(path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._tx_depth = 0

    # ------------------------------------------------------------------ 事务
    @contextmanager
    def transaction(self) -> Iterator[None]:
        """写事务。嵌套调用复用外层事务，不会提前提交。"""

        if self._tx_depth > 0:
            self._tx_depth += 1
            try:
                yield
            finally:
                self._tx_depth -= 1
            return

        self._conn.execute("BEGIN IMMEDIATE")
        self._tx_depth = 1
        try:
            yield
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")
        finally:
            self._tx_depth = 0

    def _require_tx(self) -> None:
        if self._tx_depth == 0:
            raise RuntimeError("get_for_update 必须在 transaction() 内调用")

    # ------------------------------------------------------------------ 清单
    def insert_tasklist(self, record: TaskListRecord) -> None:
        sql = """
        INSERT INTO tasklists (
            tasklist_id, target_software_release_version, status, rev,
            tasklist_title, content_hash, created_at, updated_at,
            source_tasklist_id, copy_mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self.transaction():
            self._conn.execute(
                sql,
                (
                    record.tasklist_id,
                    record.target_software_release_version,
                    record.status.value,
                    record.rev,
                    record.tasklist_title,
                    record.content_hash,
                    record.created_at,
                    record.updated_at,
                    record.source_tasklist_id,
                    record.copy_mode.value if record.copy_mode else None,
                ),
            )

    def get_tasklist(self, tasklist_id: str) -> TaskListRecord | None:
        row = self._conn.execute(
            "SELECT * FROM tasklists WHERE tasklist_id = ?", (tasklist_id,)
        ).fetchone()
        return _tasklist_from_row(row) if row is not None else None

    def get_for_update(self, tasklist_id: str) -> TaskListRecord | None:
        self._require_tx()
        return self.get_tasklist(tasklist_id)

    def list_tasklists(self) -> list[TaskListRecord]:
        rows = self._conn.execute(
            "SELECT * FROM tasklists ORDER BY created_at, tasklist_id"
        ).fetchall()
        return [_tasklist_from_row(r) for r in rows]

    def update_title(self, tasklist_id: str, title: str | None) -> None:
        with self.transaction():
            self._conn.execute(
                "UPDATE tasklists SET tasklist_title = ?, updated_at = ? WHERE tasklist_id = ?",
                (title, utc_now(), tasklist_id),
            )

    def bump_rev(self, tasklist_id: str) -> int:
        with self.transaction():
            self._conn.execute(
                "UPDATE tasklists SET rev = rev + 1, updated_at = ? WHERE tasklist_id = ?",
                (utc_now(), tasklist_id),
            )
            row = self._conn.execute(
                "SELECT rev FROM tasklists WHERE tasklist_id = ?", (tasklist_id,)
            ).fetchone()
        return int(row["rev"]) if row is not None else 0

    def save_status(self, tasklist_id: str, status: Status) -> None:
        with self.transaction():
            self._conn.execute(
                "UPDATE tasklists SET status = ?, updated_at = ? WHERE tasklist_id = ?",
                (status.value, utc_now(), tasklist_id),
            )

    def save_content_hash(self, tasklist_id: str, content_hash: str) -> None:
        with self.transaction():
            self._conn.execute(
                "UPDATE tasklists SET content_hash = ?, updated_at = ? WHERE tasklist_id = ?",
                (content_hash, utc_now(), tasklist_id),
            )

    # ------------------------------------------------------------------ 条目
    def list_items(self, tasklist_id: str) -> list[ItemRecord]:
        rows = self._conn.execute(
            "SELECT * FROM tasklist_items WHERE tasklist_id = ? ORDER BY seq",
            (tasklist_id,),
        ).fetchall()
        return [_item_from_row(r) for r in rows]

    def count_items(self, tasklist_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM tasklist_items WHERE tasklist_id = ?",
            (tasklist_id,),
        ).fetchone()
        return int(row["n"]) if row is not None else 0

    def next_seq(self, tasklist_id: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM tasklist_items WHERE tasklist_id = ?",
            (tasklist_id,),
        ).fetchone()
        return int(row["n"]) if row is not None else 1

    def bulk_insert_items(
        self,
        tasklist_id: str,
        items: Sequence[CaseRef],
        start_seq: int,
    ) -> None:
        if not items:
            return
        rows = [
            (
                tasklist_id,
                start_seq + offset,
                ref.use_case_id,
                ref.use_case_version,
                ref.content_hash,
                int(ref.pinned),
            )
            for offset, ref in enumerate(items)
        ]
        with self.transaction():
            self._conn.executemany(
                """
                INSERT INTO tasklist_items
                    (tasklist_id, seq, use_case_id, use_case_version, content_hash, pinned)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def delete_items(self, tasklist_id: str, case_ids: Sequence[str]) -> int:
        if not case_ids:
            return 0
        placeholders = ",".join("?" for _ in case_ids)
        with self.transaction():
            cursor = self._conn.execute(
                f"DELETE FROM tasklist_items WHERE tasklist_id = ? AND use_case_id IN ({placeholders})",
                (tasklist_id, *case_ids),
            )
            self._conn.execute(
                "UPDATE tasklists SET updated_at = ? WHERE tasklist_id = ?",
                (utc_now(), tasklist_id),
            )
        return cursor.rowcount

    # ------------------------------------------------------------------ 生命周期
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "TaskListRepo":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

import sqlite3
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")

# 表结构 = 查询列 + data 列（完整对象的 JSON），对象结构只由 pydantic 模型定义
SCHEMA = """
CREATE TABLE IF NOT EXISTS test_cases (
    id         TEXT PRIMARY KEY,
    category   TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    data       TEXT NOT NULL
);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    """创建连接并建表。连接配置只在这里做，repo 只使用连接。"""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


class SQLiteRepoBase:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def _execute(self, sql: str, params: Sequence[Any] | Mapping[str, Any] = ()) -> sqlite3.Cursor:
        """单条写操作，自成一个事务：成功 commit，异常 rollback。"""
        with self._conn:
            return self._conn.execute(sql, params)

    def _query_one(
        self,
        sql: str,
        params: Sequence[Any] | Mapping[str, Any],
        mapper: Callable[[sqlite3.Row], T],
    ) -> T | None:
        row = self._conn.execute(sql, params).fetchone()
        return mapper(row) if row is not None else None

    def _query_all(
        self,
        sql: str,
        params: Sequence[Any] | Mapping[str, Any],
        mapper: Callable[[sqlite3.Row], T],
    ) -> list[T]:
        return [mapper(r) for r in self._conn.execute(sql, params)]

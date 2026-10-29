import sqlite3

from demo.models import TestCase
from demo.persistence.db import SQLiteRepoBase


def _row_to_case(row: sqlite3.Row) -> TestCase:
    return TestCase.model_validate_json(row["data"])


class CaseRepo(SQLiteRepoBase):
    def add(self, case: TestCase) -> None:
        sql = "INSERT INTO test_cases (id, category, data) VALUES (?, ?, ?)"
        self._execute(sql, (case.id, case.category, case.model_dump_json()))

    def get(self, case_id: str) -> TestCase | None:
        sql = "SELECT data FROM test_cases WHERE id = ?"
        return self._query_one(sql, (case_id,), _row_to_case)

    def get_all(self) -> list[TestCase]:
        sql = "SELECT data FROM test_cases ORDER BY created_at, id"
        return self._query_all(sql, (), _row_to_case)

    def delete(self, case_id: str) -> bool:
        sql = "DELETE FROM test_cases WHERE id = ?"
        return self._execute(sql, (case_id,)).rowcount > 0

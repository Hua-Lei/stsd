"""执行编排的命令对象。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RunTaskList:
    tasklist_id: str
    environment_name: str
    base_url: str
    headers: dict[str, str] | None = None
    variables: dict[str, Any] | None = None
    timeout_seconds: float = 6.0
    kind: str = "MANUAL"
    source_run_id: str | None = None

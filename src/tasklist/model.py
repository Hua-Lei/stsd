"""任务清单的领域模型：只记录字段与不依赖外部的纯计算。

服务层负责开事务、取数据、调用外部端口、写回；这里不持有仓储，也不访问数据库。
字段与存储一一对应：``TaskList`` -> tasklists，``Item`` / ``CaseRef`` -> tasklist_items。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Status(StrEnum):
    DRAFT = "DRAFT"
    LOCKED = "LOCKED"


class CopyMode(StrEnum):
    RERESOLVE = "RERESOLVE"   # 保留用例 id 集合，按新目标版本重新解析
    PINNED = "PINNED"         # 逐条保留原有 (use_case_id, use_case_version)


class TaskListError(Exception):
    """清单级失败；条目级失败放进接口返回的 rejected / warnings。"""

    def __init__(self, code: str, message: str = "", *,
                 tasklist_id: str | None = None) -> None:
        self.code = code
        self.message = message or code
        self.tasklist_id = tasklist_id
        super().__init__(f"{code}: {self.message}")


@dataclass(frozen=True)
class CaseRef:
    """清单条目里冻结的用例引用。

    ``content_hash`` 由服务端在加入时从用例库取出，调用方不传；
    ``pinned`` 仅用于审核展示，不计入清单 content_hash。
    """

    use_case_id: str
    use_case_version: int
    content_hash: str
    pinned: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "use_case_id": self.use_case_id,
            "use_case_version": self.use_case_version,
            "content_hash": self.content_hash,
            "pinned": self.pinned,
        }


@dataclass(frozen=True)
class Item:
    """存储层的清单条目；``seq`` 是执行顺序，删除不重排，新增追加。"""

    seq: int
    case_ref: CaseRef

    @property
    def use_case_id(self) -> str:
        return self.case_ref.use_case_id

    @property
    def use_case_version(self) -> int:
        return self.case_ref.use_case_version

    @property
    def content_hash(self) -> str:
        return self.case_ref.content_hash

    def to_dict(self) -> dict[str, object]:
        return {"seq": self.seq, "case_ref": self.case_ref.to_dict()}


def compute_list_content_hash(target_version: int, items: Iterable[Item]) -> str:
    """目标版本 + 有序的 (use_case_id, use_case_version, content_hash)。

    标题、状态、rev、pinned 不进入；顺序进入，重排即是另一份清单。
    """

    payload = {
        "target_software_release_version": target_version,
        "items": [
            [item.use_case_id, item.use_case_version, item.content_hash]
            for item in items
        ],
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class TaskList:
    """清单本身。条目单独存储，需要条目参与的计算通过参数传入。"""

    tasklist_id: str
    target_software_release_version: int
    status: Status
    rev: int
    tasklist_title: str | None
    content_hash: str | None
    created_at: datetime
    updated_at: datetime
    source_tasklist_id: str | None = None
    copy_mode: CopyMode | None = None

    @property
    def is_editable(self) -> bool:
        return self.status is Status.DRAFT

    def compute_content_hash(self, items: Sequence[Item]) -> str:
        return compute_list_content_hash(self.target_software_release_version, items)

    def lock(self, items: Sequence[Item], now: datetime) -> str:
        """校验状态与非空并固化 content_hash，返回指纹。

        "引用版本仍存在且内容未变"需要用例库端口，由服务层先行校验。
        """

        if not self.is_editable:
            raise TaskListError("LIST_LOCKED", "清单已锁定", tasklist_id=self.tasklist_id)
        if not items:
            raise TaskListError("EMPTY_LIST", "空清单不允许锁定", tasklist_id=self.tasklist_id)
        self.status = Status.LOCKED
        self.content_hash = self.compute_content_hash(items)
        self.updated_at = now
        return self.content_hash

    def rename(self, tasklist_title: str | None, now: datetime) -> None:
        """元数据修改：锁定后仍允许，不影响 content_hash 与 rev。"""

        self.tasklist_title = tasklist_title
        self.updated_at = now

    def to_dict(self) -> dict[str, object]:
        return {
            "tasklist_id": self.tasklist_id,
            "target_software_release_version": self.target_software_release_version,
            "status": self.status.value,
            "rev": self.rev,
            "tasklist_title": self.tasklist_title,
            "content_hash": self.content_hash,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "source_tasklist_id": self.source_tasklist_id,
            "copy_mode": self.copy_mode.value if self.copy_mode else None,
        }

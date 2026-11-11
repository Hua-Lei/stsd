"""任务清单的领域模型：只记录字段与不依赖外部的纯计算。

服务层只负责开事务、取数据、调用规则、写回。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    DRAFT = "DRAFT"
    LOCKED = "LOCKED"


class CopyMode(StrEnum):
    RERESOLVE = "RERESOLVE"
    PINNED = "PINNED"


@dataclass(frozen=True)
class CaseRef:
    """清单条目里冻结的用例引用。

    ``content_hash`` 由服务端在加入那一刻从用例库取出，调用方不传；
    ``pinned`` 表示该条是显式指定版本加入的，仅用于审核展示，
    不计入清单 content_hash（它不是清单内容，只是来源说明）。
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
class ItemRecord:
    """存储层的清单条目（具有顺序）。"""

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


@dataclass(frozen=True)
class TaskListRecord:
    """清单本身。

    ``rev`` 只在 DRAFT 状态下随成功的编辑递增，锁定时不再变化；
    ``content_hash`` 锁定时固化，DRAFT 状态下为 None。
    """

    tasklist_id: str
    target_software_release_version: int
    status: Status
    rev: int
    tasklist_title: str | None
    content_hash: str | None
    created_at: str
    updated_at: str
    source_tasklist_id: str | None = None
    copy_mode: CopyMode | None = None

    @property
    def is_editable(self) -> bool:
        return self.status is Status.DRAFT

    def to_dict(self) -> dict[str, object]:
        return {
            "tasklist_id": self.tasklist_id,
            "target_software_release_version": self.target_software_release_version,
            "status": self.status.value,
            "rev": self.rev,
            "tasklist_title": self.tasklist_title,
            "content_hash": self.content_hash,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_tasklist_id": self.source_tasklist_id,
            "copy_mode": self.copy_mode.value if self.copy_mode else None,
        }

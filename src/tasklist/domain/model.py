"""任务清单领域模型。

这一层只表达业务概念与不变量，不依赖 sqlite、CLI、用例库实现，也不开事务：

- ``TaskList`` 是聚合根：清单的状态、版本号、条目、指纹都由它自己维护；
- ``TaskListItem`` 是聚合内实体：``seq`` 决定执行顺序，只能随条目一起读写；
- ``CaseRef`` 是不可变值对象：一旦写入清单，就不再被改写；
- 聚合之间、聚合与外部系统之间的规则（版本解析、内容指纹比对）留给应用层。

与参考实现 ``src/library/domain/model.py`` 的结构一一对应：实体负责状态迁移，
值对象负责承载不可变数据，领域错误在破坏规则时抛出。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Self
from uuid import uuid4

from ..errors import (
    DuplicateItem,
    EmptyList,
    InvalidArgument,
    ListLocked,
    TargetMissing,
)
from .hashing import compute_list_content_hash


class Status(StrEnum):
    DRAFT = "DRAFT"
    LOCKED = "LOCKED"


class CopyMode(StrEnum):
    RERESOLVE = "RERESOLVE"
    PINNED = "PINNED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def _new_id() -> str:
    return "tl_" + uuid4().hex[:16]


def validate_target(value: object) -> int:
    """目标版本必填且为 >= 1 的整数；bool 是 int 的子类，必须显式排除。"""

    if value is None:
        raise TargetMissing()
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidArgument("目标软件版本必须是 >= 1 的整数")
    return value


def normalize_title(value: object) -> str | None:
    """标题是元数据：允许 None，去掉首尾空白后为空则视为 None。"""

    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidArgument("清单名称必须是字符串")
    stripped = value.strip()
    return stripped or None


@dataclass(frozen=True)
class CaseRef:
    """清单条目里冻结的用例引用（值对象）。

    ``content_hash`` 由服务端在加入那一刻从用例库取出，调用方不传；
    ``pinned`` 表示该条是显式指定版本加入的，仅用于审核展示，
    不计入清单 content_hash（它不是清单内容，只是来源说明）。
    """

    use_case_id: str
    use_case_version: int
    content_hash: str
    pinned: bool = False

    def as_tuple(self) -> tuple[str, int, str]:
        return (self.use_case_id, self.use_case_version, self.content_hash)

    def to_dict(self) -> dict[str, object]:
        return {
            "use_case_id": self.use_case_id,
            "use_case_version": self.use_case_version,
            "content_hash": self.content_hash,
            "pinned": self.pinned,
        }


@dataclass
class TaskListItem:
    """清单条目：聚合内实体，标识是 ``use_case_id``，``seq`` 决定执行顺序。"""

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


@dataclass
class TaskList:
    """任务清单聚合根。

    不变量（都写在这个类里，而不是散落在服务层）：

    1. ``status`` 只能 DRAFT → LOCKED 单向变化；
    2. 同一清单内 ``use_case_id`` 唯一；
    3. 条目在加入那一刻固定版本，之后不再改写；
    4. ``rev`` 只在成功的编辑（有实际条目变化）时 +1；
    5. 锁定后内容字段与条目不再更新，``content_hash`` 在锁定时固化；
    6. 清单属于且只属于一个项目，项目范围由仓储按 ``proj_id`` 隔离。
    """

    tasklist_id: str
    proj_id: str
    target_software_release_version: int
    status: Status
    rev: int
    tasklist_title: str | None
    content_hash: str | None
    created_at: datetime
    updated_at: datetime
    items: list[TaskListItem] = field(default_factory=list)
    source_tasklist_id: str | None = None
    copy_mode: CopyMode | None = None

    # ------------------------------------------------------------------ 工厂
    @classmethod
    def create(
        cls,
        proj_id: str,
        target_software_release_version: object,
        tasklist_title: object = None,
        *,
        case_refs: tuple[CaseRef, ...] | list[CaseRef] = (),
        source_tasklist_id: str | None = None,
        copy_mode: CopyMode | None = None,
    ) -> Self:
        """创建 DRAFT 清单。

        ``case_refs`` 只给 ``copy_list`` 使用：复制是在“构造一份新草稿”，
        不是一次编辑，因此 ``rev`` 仍为 0。``create_list`` 不传这个参数。
        """

        if not isinstance(proj_id, str) or not proj_id:
            raise InvalidArgument("proj_id 必须是非空字符串")
        target = validate_target(target_software_release_version)
        title = normalize_title(tasklist_title)
        now = utc_now()
        items = _build_items(case_refs)
        return cls(
            tasklist_id=_new_id(),
            proj_id=proj_id,
            target_software_release_version=target,
            status=Status.DRAFT,
            rev=0,
            tasklist_title=title,
            content_hash=None,
            created_at=now,
            updated_at=now,
            items=items,
            source_tasklist_id=source_tasklist_id,
            copy_mode=copy_mode,
        )

    # ------------------------------------------------------------------ 查询
    @property
    def is_editable(self) -> bool:
        return self.status is Status.DRAFT

    @property
    def item_count(self) -> int:
        return len(self.items)

    @property
    def case_refs(self) -> list[CaseRef]:
        return [item.case_ref for item in self.items]

    def to_dict(self) -> dict[str, object]:
        """元数据视图；条目的展示信息由 read model（views.py）负责。"""

        return {
            "tasklist_id": self.tasklist_id,
            "proj_id": self.proj_id,
            "target_software_release_version": self.target_software_release_version,
            "status": self.status.value,
            "rev": self.rev,
            "tasklist_title": self.tasklist_title,
            "content_hash": self.content_hash,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "source_tasklist_id": self.source_tasklist_id,
            "copy_mode": self.copy_mode.value if self.copy_mode else None,
        }

    # ------------------------------------------------------------------ 不变量
    def ensure_draft(
        self, message: str = "清单已锁定，不能编辑用例"
    ) -> None:
        if not self.is_editable:
            raise ListLocked(message, tasklist_id=self.tasklist_id)

    # ------------------------------------------------------------------ 行为
    def rename(self, tasklist_title: object) -> None:
        """元数据修改：锁定后仍可改，且不影响 content_hash / rev。"""

        self.tasklist_title = normalize_title(tasklist_title)
        self._touch()

    def add_case_refs(self, case_refs: list[CaseRef]) -> list[CaseRef]:
        """批量追加条目；分配连续的 seq，整批只让 rev +1 一次。"""

        self.ensure_draft()
        refs = list(case_refs)
        if not refs:
            return []

        known = {item.use_case_id for item in self.items}
        for ref in refs:
            if ref.use_case_id in known:
                raise DuplicateItem(ref.use_case_id)
            known.add(ref.use_case_id)

        next_seq = max((item.seq for item in self.items), default=0) + 1
        for offset, ref in enumerate(refs):
            self.items.append(TaskListItem(seq=next_seq + offset, case_ref=ref))
        self._bump_rev()
        return refs

    def remove_case_refs(self, case_ids: list[str]) -> list[str]:
        """按 use_case_id 删除；不重排 seq，返回真正被删掉的 id。"""

        self.ensure_draft()
        wanted = list(dict.fromkeys(case_ids))
        present = {item.use_case_id for item in self.items}
        removed = [case_id for case_id in wanted if case_id in present]
        if not removed:
            return []

        gone = set(removed)
        self.items = [item for item in self.items if item.use_case_id not in gone]
        self._bump_rev()
        return removed

    def lock(self) -> str:
        """DRAFT → LOCKED，并固化 content_hash；锁定不是一次内容编辑，rev 不变。"""

        self.ensure_draft("清单已锁定，不能重复锁定")
        if not self.items:
            raise EmptyList(tasklist_id=self.tasklist_id)

        self.content_hash = compute_list_content_hash(
            self.target_software_release_version,
            [item.case_ref.as_tuple() for item in self.items],
        )
        self.status = Status.LOCKED
        self._touch()
        return self.content_hash

    # ------------------------------------------------------------------ 内部
    def _bump_rev(self) -> None:
        self.rev += 1
        self._touch()

    def _touch(self) -> None:
        self.updated_at = utc_now()


def _build_items(case_refs: list[CaseRef] | tuple[CaseRef, ...]) -> list[TaskListItem]:
    items: list[TaskListItem] = []
    known: set[str] = set()
    for seq, ref in enumerate(case_refs, 1):
        if ref.use_case_id in known:
            raise DuplicateItem(ref.use_case_id)
        known.add(ref.use_case_id)
        items.append(TaskListItem(seq=seq, case_ref=ref))
    return items

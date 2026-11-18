'''用例库领域模型。

用例树由两种节点构成：Section 是目录，只负责组织结构；测试点（TestPoint）
拥有一条按序号线性增长的修订历史。

修订由 ``(testpoint_id, revision_ver)`` 标识，``proj_ver`` 只说明这次修订
针对哪个项目版本写成，不参与标识（见 decisions/001）。修订产生后内容不再
改动；实现只能在该修订为草稿时设置，冻结要求实现非空（见 decisions/002）。
'''

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar, Literal, Self
from uuid import uuid4

from stsd.library.domain.errors import (
    ImplementationRequired,
    InvalidArgument,
    NodeDeleted,
    RevisionFrozen,
    RevisionNotFound,
)

RevisionStatus = Literal['draft', 'frozen']
NodeType = Literal['section', 'testpoint']


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class RevisionDetail:
    '''ReviseTestPoint 提供的内容。实现不在这里设置，由 AddImplementation 补。'''

    name: str
    description: str = ''

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise InvalidArgument('revision name must not be empty')
        if not isinstance(self.description, str):
            raise InvalidArgument('revision description must be a string')
        object.__setattr__(self, 'name', self.name.strip())


@dataclass(kw_only=True)
class LibNode:
    '''用例树节点。删除是软删除，节点和已冻结修订的历史都保留。'''

    node_type: ClassVar[NodeType]

    node_id: str
    project_id: str
    parent_id: str | None
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str
    is_deleted: bool = False

    @classmethod
    def create(cls, project_id: str, parent_id: str | None, actor_id: str,
               **fields) -> Self:
        now = now_utc()
        return cls(
            node_id=new_id(),
            project_id=project_id,
            parent_id=parent_id,
            created_at=now,
            updated_at=now,
            created_by=actor_id,
            updated_by=actor_id,
            **fields,
        )

    def _touch(self, actor_id: str) -> None:
        self.updated_at = now_utc()
        self.updated_by = actor_id

    def soft_delete(self, actor_id: str) -> None:
        if self.is_deleted:
            raise NodeDeleted(self.node_id)
        self.is_deleted = True
        self._touch(actor_id)


@dataclass(kw_only=True)
class Section(LibNode):
    '''目录节点，只负责组织结构；内容的变化由子节点承担。'''

    node_type: ClassVar[NodeType] = 'section'

    name: str


@dataclass
class TestPointVersion:
    '''测试点的一条修订，是 TestPoint 聚合内的实体。

    修订一旦产生，``name``、``description``、``proj_ver`` 不再变化；
    ``implementation`` 只在草稿状态可以覆盖，冻结后也不能再改。
    '''

    testpoint_id: str
    revision_ver: int
    name: str
    description: str
    implementation: str | None
    proj_ver: str
    status: RevisionStatus
    created_at: datetime
    created_by: str

    @property
    def is_frozen(self) -> bool:
        return self.status == 'frozen'


@dataclass(kw_only=True)
class TestPoint(LibNode):
    '''测试点聚合根，自己持有按序号线性增长的修订历史。'''

    node_type: ClassVar[NodeType] = 'testpoint'

    revisions: list[TestPointVersion] = field(default_factory=list)

    @property
    def latest_revision(self) -> TestPointVersion | None:
        return max(self.revisions, key=lambda r: r.revision_ver, default=None)

    @property
    def latest_frozen_revision(self) -> TestPointVersion | None:
        frozen = [r for r in self.revisions if r.is_frozen]
        return max(frozen, key=lambda r: r.revision_ver, default=None)

    def revision(self, revision_ver: int) -> TestPointVersion | None:
        return next(
            (r for r in self.revisions if r.revision_ver == revision_ver),
            None,
        )

    def content_unchanged(self, detail: RevisionDetail) -> bool:
        latest = self.latest_revision
        return (
            latest is not None
            and latest.name == detail.name
            and latest.description == detail.description
        )

    def add_revision(self, proj_ver: str, detail: RevisionDetail,
                     actor_id: str) -> TestPointVersion:
        '''产生一条新修订；实现为空，状态为草稿。'''
        if self.is_deleted:
            raise NodeDeleted(self.node_id)

        revision = TestPointVersion(
            testpoint_id=self.node_id,
            revision_ver=max(
                (r.revision_ver for r in self.revisions), default=0
            ) + 1,
            name=detail.name,
            description=detail.description,
            implementation=None,
            proj_ver=proj_ver,
            status='draft',
            created_at=now_utc(),
            created_by=actor_id,
        )
        self.revisions.append(revision)
        self._touch(actor_id)
        return revision

    def add_implementation(self, revision_ver: int, code_impl: str,
                           actor_id: str) -> TestPointVersion:
        '''为草稿修订补充或覆盖实现。'''
        if self.is_deleted:
            raise NodeDeleted(self.node_id)
        revision = self.revision(revision_ver)
        if revision is None:
            raise RevisionNotFound(self.node_id, revision_ver)
        if revision.is_frozen:
            raise RevisionFrozen(self.node_id, revision_ver)
        if not isinstance(code_impl, str) or not code_impl.strip():
            raise InvalidArgument('implementation must not be empty')

        revision.implementation = code_impl
        self._touch(actor_id)
        return revision

    def freeze(self, revision_ver: int, actor_id: str) -> TestPointVersion:
        '''冻结草稿修订；冻结后内容与实现都不可变，且不可撤销。'''
        if self.is_deleted:
            raise NodeDeleted(self.node_id)
        revision = self.revision(revision_ver)
        if revision is None:
            raise RevisionNotFound(self.node_id, revision_ver)
        if revision.is_frozen:
            raise RevisionFrozen(self.node_id, revision_ver)
        if not revision.implementation or not revision.implementation.strip():
            raise ImplementationRequired(self.node_id, revision_ver)

        revision.status = 'frozen'
        self._touch(actor_id)
        return revision

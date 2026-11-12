'''
用例库领域模型。

- Project 持有上游文档的各个版本。
- LibNode 是用例树上的节点：Section 是目录，TestPoint 是测试点。
- TestPoint 是聚合根，自己持有版本历史，历史只追加、不修改。
- 聚合之间只用 id 互相引用；涉及多个聚合的规则（父节点是否存在、
  文档版本是否存在等）留给应用层。
'''

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar, Literal, Self
from uuid import uuid4


class LibraryError(Exception):
    pass


class NodeError(LibraryError):
    pass


class VersionError(LibraryError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class Actor:
    actor_id: str
    name: str
    type: Literal['user', 'agent']


@dataclass(frozen=True)
class ProjectDoc:
    doc_id: str
    title: str
    content: str


@dataclass(frozen=True)
class ProjectVersion:
    '''
    Project的一个版本，创建后不可改。
    '''
    proj_id: str
    proj_version: str
    docs: tuple[ProjectDoc, ...] = ()


@dataclass
class Project:
    proj_id: str
    name: str
    versions: list[ProjectVersion] = field(default_factory=list)

    def add_version(self, proj_version: str,
                    docs: tuple[ProjectDoc, ...] = ()) -> ProjectVersion:
        if any(v.proj_version == proj_version for v in self.versions):
            raise VersionError(f'project version {proj_version!r} already exists')
        version = ProjectVersion(self.proj_id, proj_version, docs)
        self.versions.append(version)
        return version


@dataclass(kw_only=True)
class LibNode:
    '''
    用例树的节点，软删除机制
    '''
    node_type: ClassVar[Literal['section', 'testpoint']]

    node_id: str
    proj_id: str
    parent_id: str | None
    
    created_at: datetime
    updated_at: datetime
    updated_by: Actor
    is_deleted: bool = False

    @classmethod
    def create(cls, proj_id: str, parent_id: str | None, actor: Actor,
               **fields) -> Self:
        now = _now()
        return cls(node_id=_new_id(), proj_id=proj_id, parent_id=parent_id,
                   created_at=now, updated_at=now, updated_by=actor, **fields)

    def _touch(self, actor: Actor) -> None:
        self.updated_at = _now()
        self.updated_by = actor

    def soft_delete(self, actor: Actor) -> None:
        if self.is_deleted:
            raise NodeError(f'node {self.node_id} is already deleted')
        self.is_deleted = True
        self._touch(actor)


@dataclass(kw_only=True)
class Section(LibNode):
    '''
    目录节点，只负责组织结构。
    '''
    node_type = 'section'

    name: str
    def list() -> list[LibNode]:
        """返回该目录下的子节点列表，按创建时间排序"""
        raise NotImplementedError


@dataclass(frozen=True)
class TestPointVersion:
    '''
    测试点的一条修订记录，创建后不可改。
    '''
    testpoint_id: str
    version_no: str                  # 归属的上游文档版本，对应 ProjectVersion.proj_version
    revision_no: int                 # 同一文档版本下的修订序号，从 1 开始
    name: str
    desc: str                        # 该版本的完整测试内容
    change_note: str
    created_at: datetime
    created_by: Actor
    impl_ref: str | None = None      # 可执行实现的引用，None 表示尚未实现


@dataclass(kw_only=True)
class TestPoint(LibNode):
    '''
    测试点
    '''
    node_type = 'testpoint'

    versions: list[TestPointVersion] = field(default_factory=list)

    @property
    def current(self) -> TestPointVersion | None:
        return self.versions[-1] if self.versions else None

    def revise(self, version_no: str, name: str, desc: str, actor: Actor,
               impl_ref: str | None = None,
               change_note: str = '') -> TestPointVersion:
        if self.is_deleted:
            raise NodeError(f'node {self.node_id} is deleted')
        revision_no = 1 + max((v.revision_no for v in self.versions
                               if v.version_no == version_no), default=0)
        version = TestPointVersion(
            testpoint_id=self.node_id,
            version_no=version_no,
            revision_no=revision_no,
            name=name,
            desc=desc,
            change_note=change_note,
            created_at=_now(),
            created_by=actor,
            impl_ref=impl_ref,
        )
        self.versions.append(version)
        self._touch(actor)
        return version

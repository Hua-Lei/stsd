'''
用例库应用层：每个函数是一个用例，对应一个事务。
实体自己的规则在 model.py，这里只做需要查仓储才能判断的跨聚合规则。
范围（哪个 Project）由传入的工作单元决定。
'''

from ..adapters.repository import LibraryRepository
from ..domain.model import (Actor, LibNode, NodeError, Section, TestPoint,
                            VersionError)
from .unit_of_work import AbstractUnitOfWork


def create_section(uow: AbstractUnitOfWork, parent_id: str | None,
                   name: str, actor: Actor) -> Section:
    with uow:
        _require_parent(uow.library, parent_id)
        section = Section.create(uow.library.proj_id, parent_id, actor, name=name)
        uow.library.save(section)
        uow.commit()
        return section


def create_testpoint(uow: AbstractUnitOfWork, parent_id: str | None,
                     version_no: str, name: str, desc: str, actor: Actor,
                     impl_ref: str | None = None,
                     change_note: str = '') -> TestPoint:
    '''新建测试点，同时写入第一条修订。'''
    with uow:
        _require_parent(uow.library, parent_id)
        _require_doc_version(uow.library, version_no)
        tp = TestPoint.create(uow.library.proj_id, parent_id, actor)
        tp.revise(version_no, name, desc, actor, impl_ref, change_note)
        uow.library.save(tp)
        uow.commit()
        return tp


def revise_testpoint(uow: AbstractUnitOfWork, node_id: str, version_no: str,
                     name: str, desc: str, actor: Actor,
                     impl_ref: str | None = None,
                     change_note: str = '') -> TestPoint:
    with uow:
        tp = _require_node(uow.library, node_id)
        if not isinstance(tp, TestPoint):
            raise NodeError(f'node {node_id} is not a testpoint')
        _require_doc_version(uow.library, version_no)
        tp.revise(version_no, name, desc, actor, impl_ref, change_note)
        uow.library.save(tp)
        uow.commit()
        return tp


def delete_node(uow: AbstractUnitOfWork, node_id: str,
                actor: Actor) -> list[LibNode]:
    '''软删除节点及其所有未删除的后代，返回被删除的节点。'''
    with uow:
        root = _require_node(uow.library, node_id)
        if root.is_deleted:
            raise NodeError(f'node {node_id} is already deleted')
        targets, stack = [], [root]
        while stack:
            node = stack.pop()
            targets.append(node)
            stack.extend(c for c in uow.library.children(node.node_id)
                         if not c.is_deleted)
        for node in targets:
            node.soft_delete(actor)
        uow.library.save(*targets)
        uow.commit()
        return targets


def outline(uow: AbstractUnitOfWork,
            parent_id: str | None = None) -> list[LibNode]:
    '''某节点下未删除的直接子节点。只读，不提交。'''
    with uow:
        _require_parent(uow.library, parent_id)
        return [n for n in uow.library.children(parent_id) if not n.is_deleted]


def _require_node(repo: LibraryRepository, node_id: str) -> LibNode:
    node = repo.get_node(node_id)
    if node is None:
        raise NodeError(f'node {node_id} not found')
    return node


def _require_parent(repo: LibraryRepository, parent_id: str | None) -> None:
    if parent_id is None:
        return
    parent = _require_node(repo, parent_id)
    if not isinstance(parent, Section):
        raise NodeError(f'parent {parent_id} is not a section')
    if parent.is_deleted:
        raise NodeError(f'parent {parent_id} is deleted')


def _require_doc_version(repo: LibraryRepository, version_no: str) -> None:
    if not repo.has_doc_version(version_no):
        raise VersionError(
            f'project {repo.proj_id} has no version {version_no!r}')

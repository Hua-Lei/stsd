'''用例库应用层。

每个函数是一个用例，对应一个事务。聚合自己的规则在 ``domain/model.py``；
这里只做需要查仓储或查 Access 才能判断的跨聚合规则，以及读模型投影。
'''

from __future__ import annotations

from collections import deque

from sqlalchemy.exc import IntegrityError

from ..domain.errors import (InvalidArgument, NodeDeleted, NodeNotFound,
                             NotASection, NotATestPoint,
                             ProjectVersionNotFound, RevisionConflict,
                             RevisionNotFound)
from ..domain.model import (LibNode, RevisionDetail, Section, TestPoint,
                            TestPointVersion)
from .unit_of_work import AbstractUnitOfWork
from .views import SectionTreeNode, TestPointDetail, TestPointTreeNode, TreeNode


# ---------------------------------------------------------------------------
# 写操作
# ---------------------------------------------------------------------------
def create_section(uow: AbstractUnitOfWork, actor_id: str, project_id: str,
                   parent_id: str | None, name: str) -> SectionTreeNode:
    '''CreateSection：在项目内创建目录节点；parent_id 为空表示根下。'''
    _require_actor(actor_id)
    project_id = _require_text(project_id, 'project_id')
    name = _require_text(name, 'name')

    with uow:
        if parent_id is not None:
            _require_section(uow, project_id, parent_id)
        section = Section.create(project_id, parent_id, actor_id, name=name)
        uow.library.save(section)
        uow.commit()
        return _section_node(section)


def add_testpoint(uow: AbstractUnitOfWork, actor_id: str, project_id: str,
                  section_id: str, name: str,
                  proj_ver: str) -> TestPointTreeNode:
    '''AddTestPoint：新建测试点，同时产生 revision_ver 为 1 的第一条修订。

    第一条修订的实现为空，描述也为空；需要描述时再调用 ``revise_testpoint``。
    '''
    _require_actor(actor_id)
    project_id = _require_text(project_id, 'project_id')
    section_id = _require_text(section_id, 'section_id')
    name = _require_text(name, 'name')
    proj_ver = _require_text(proj_ver, 'proj_ver')

    with uow:
        _require_section(uow, project_id, section_id)
        _require_project_version(uow, project_id, proj_ver)

        testpoint = TestPoint.create(project_id, section_id, actor_id)
        testpoint.add_revision(
            proj_ver=proj_ver,
            detail=RevisionDetail(name=name),
            actor_id=actor_id,
        )
        uow.library.save(testpoint)
        uow.commit()

        node = _testpoint_node(testpoint)
        if node is None:  # pragma: no cover - add_revision 保证至少一条修订
            raise RevisionNotFound(testpoint.node_id, None)
        return node


def delete_node(uow: AbstractUnitOfWork, actor_id: str,
                node_id: str) -> list[str]:
    '''DeleteNode：软删除节点及其全部未删除的后代，返回被删除的节点 id。'''
    _require_actor(actor_id)

    with uow:
        root = _require_node(uow, node_id)
        if root.is_deleted:
            raise NodeDeleted(root.node_id)

        targets: list[LibNode] = []
        queue: deque[LibNode] = deque([root])
        while queue:
            node = queue.popleft()
            if not node.is_deleted:
                targets.append(node)
            queue.extend(uow.library.children(root.project_id, node.node_id))

        for node in targets:
            node.soft_delete(actor_id)
        uow.library.save(*targets)
        uow.commit()
        return [node.node_id for node in targets]


def revise_testpoint(uow: AbstractUnitOfWork, actor_id: str,
                     testpoint_id: str, proj_ver: str,
                     revision_detail: RevisionDetail) -> TestPointDetail:
    '''ReviseTestPoint：产生新修订，实现为空。

    内容与最新修订相同的测试点不产生新修订（见 library.md 规则 6），直接
    返回最新修订。``proj_ver`` 仍会先向 Access 确认存在。
    '''
    _require_actor(actor_id)
    proj_ver = _require_text(proj_ver, 'proj_ver')
    if not isinstance(revision_detail, RevisionDetail):
        raise InvalidArgument('revision_detail must be a RevisionDetail')

    with uow:
        testpoint = _require_testpoint(uow, testpoint_id)
        _require_project_version(uow, testpoint.project_id, proj_ver)

        if testpoint.content_unchanged(revision_detail):
            latest = testpoint.latest_revision
            if latest is None:  # pragma: no cover - content_unchanged 保证非空
                raise RevisionNotFound(testpoint_id, None)
            return _detail(testpoint, latest)

        revision = testpoint.add_revision(proj_ver, revision_detail, actor_id)
        try:
            uow.library.save(testpoint)
            uow.commit()
        except IntegrityError as exc:
            raise RevisionConflict(testpoint_id) from exc
        return _detail(testpoint, revision)


def add_implementation(uow: AbstractUnitOfWork, actor_id: str,
                       testpoint_id: str, revision_ver: int,
                       code_impl: str) -> TestPointDetail:
    '''AddImplementation：为草稿修订补充实现，可以覆盖。'''
    _require_actor(actor_id)
    code_impl = _require_implementation(code_impl)

    with uow:
        testpoint = _require_testpoint(uow, testpoint_id)
        revision = testpoint.add_implementation(
            revision_ver, code_impl, actor_id
        )
        uow.library.save(testpoint)
        uow.commit()
        return _detail(testpoint, revision)


def audit_and_freeze(uow: AbstractUnitOfWork, actor_id: str,
                     testpoint_id: str,
                     revision_ver: int) -> TestPointDetail:
    '''AuditAndFreeze：审计并冻结草稿；冻结要求实现非空。'''
    _require_actor(actor_id)

    with uow:
        testpoint = _require_testpoint(uow, testpoint_id)
        revision = testpoint.freeze(revision_ver, actor_id)
        uow.library.save(testpoint)
        uow.commit()
        return _detail(testpoint, revision)


# ---------------------------------------------------------------------------
# 读接口
# ---------------------------------------------------------------------------
def get_section_tree(uow: AbstractUnitOfWork, project_id: str,
                     section_id: str | None = None) -> list[TreeNode]:
    '''get_section_tree：返回该节点下未删除的直接子节点。'''
    project_id = _require_text(project_id, 'project_id')

    with uow:
        if section_id is not None:
            section = _require_node(uow, section_id)
            if section.project_id != project_id:
                raise NodeNotFound(section_id)
            if not isinstance(section, Section):
                raise NotASection(section_id)
            if section.is_deleted:
                return []

        nodes: list[TreeNode] = []
        for node in uow.library.children(project_id, section_id):
            if node.is_deleted:
                continue
            if isinstance(node, Section):
                nodes.append(_section_node(node))
            else:
                testpoint_node = _testpoint_node(node)
                if testpoint_node is not None:
                    nodes.append(testpoint_node)
        return nodes


def get_testpoint_detail(uow: AbstractUnitOfWork, testpoint_id: str,
                         revision_ver: int | None = None) -> TestPointDetail:
    '''get_testpoint_detail：读取一条修订及其所属测试点是否已删除。

    省略 ``revision_ver`` 时返回最新的已冻结修订；没有则报不存在。
    已删除的测试点仍然可以读取修订，供旧任务和历史复现使用。
    '''
    with uow:
        testpoint = _require_node(uow, testpoint_id)
        if not isinstance(testpoint, TestPoint):
            raise NotATestPoint(testpoint_id)

        if revision_ver is None:
            revision = testpoint.latest_frozen_revision
            if revision is None:
                raise RevisionNotFound(testpoint_id, None)
        else:
            revision = testpoint.revision(revision_ver)
            if revision is None:
                raise RevisionNotFound(testpoint_id, revision_ver)
        return _detail(testpoint, revision)


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------
def _require_actor(actor_id: str) -> None:
    if not isinstance(actor_id, str) or not actor_id.strip():
        raise InvalidArgument('actor_id must not be empty')


def _require_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidArgument(f'{field} must not be empty')
    return value.strip()


def _require_implementation(code_impl: str) -> str:
    if not isinstance(code_impl, str) or not code_impl.strip():
        raise InvalidArgument('code_impl must not be empty')
    return code_impl


def _require_node(uow: AbstractUnitOfWork, node_id: str) -> LibNode:
    node = uow.library.get_node(node_id)
    if node is None:
        raise NodeNotFound(node_id)
    return node


def _require_section(uow: AbstractUnitOfWork, project_id: str,
                     section_id: str) -> Section:
    node = _require_node(uow, section_id)
    # 其他项目的节点对当前项目来说等同于不存在。
    if node.project_id != project_id:
        raise NodeNotFound(section_id)
    if node.is_deleted:
        raise NodeDeleted(section_id)
    if not isinstance(node, Section):
        raise NotASection(section_id)
    return node


def _require_testpoint(uow: AbstractUnitOfWork,
                       testpoint_id: str) -> TestPoint:
    node = _require_node(uow, testpoint_id)
    if not isinstance(node, TestPoint):
        raise NotATestPoint(testpoint_id)
    if node.is_deleted:
        raise NodeDeleted(testpoint_id)
    return node


def _require_project_version(uow: AbstractUnitOfWork, project_id: str,
                             proj_ver: str) -> None:
    if not uow.project_versions.project_version_exists(project_id, proj_ver):
        raise ProjectVersionNotFound(project_id, proj_ver)


def _section_node(section: Section) -> SectionTreeNode:
    return SectionTreeNode(
        node_type='section',
        node_id=section.node_id,
        project_id=section.project_id,
        parent_id=section.parent_id,
        name=section.name,
        created_at=section.created_at,
    )


def _testpoint_node(testpoint: TestPoint) -> TestPointTreeNode | None:
    latest = testpoint.latest_revision
    if latest is None:
        return None
    latest_frozen = testpoint.latest_frozen_revision
    return TestPointTreeNode(
        node_type='testpoint',
        node_id=testpoint.node_id,
        project_id=testpoint.project_id,
        parent_id=testpoint.parent_id,
        name=latest.name,
        latest_revision_ver=latest.revision_ver,
        latest_revision_status=latest.status,
        latest_frozen_revision_ver=(
            latest_frozen.revision_ver if latest_frozen is not None else None
        ),
        created_at=testpoint.created_at,
    )


def _detail(testpoint: TestPoint,
            revision: TestPointVersion) -> TestPointDetail:
    return TestPointDetail(
        testpoint_id=testpoint.node_id,
        project_id=testpoint.project_id,
        revision_ver=revision.revision_ver,
        name=revision.name,
        description=revision.description,
        implementation=revision.implementation,
        proj_ver=revision.proj_ver,
        status=revision.status,
        testpoint_deleted=testpoint.is_deleted,
        created_at=revision.created_at,
        created_by=revision.created_by,
    )

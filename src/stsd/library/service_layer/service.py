'''用例库应用层。

服务函数的形状按是否需要外部端口区分：

- 需要外部端口：``(uow, dep, command)``；
- 不需要外部端口：``(uow, command)``。

当前 ``AddTestPoint`` 和 ``ReviseTestPoint`` 需要向 Access 确认 ``proj_ver``，
因此接收 ``dep: ProjectVersionLookup``；``SetImplementation`` 与
``get_implementation_files`` 还依赖工作单元上的实现文件存储；其余用例只
依赖本模块仓储。``command`` 是 ``command.py`` 中定义的命令或读请求对象，
承载本次调用的全部业务字段。

聚合自己的规则在 ``domain/model.py``；这里只做需要查仓储或查 Access 才能
判断的跨聚合规则，以及读模型投影。
'''

from __future__ import annotations

from collections import deque
from collections.abc import Mapping

from sqlalchemy.exc import IntegrityError

from stsd.library.command import (
    AddTestPoint,
    AuditAndFreeze,
    CreateSection,
    DeleteNode,
    GetImplementationFiles,
    GetSectionTree,
    GetTestPointDetail,
    ReviseTestPoint,
    SetImplementation,
)
from stsd.library.domain.errors import (
    ImplementationInvalid,
    ImplementationRequired,
    InvalidArgument,
    NodeDeleted,
    NodeNotFound,
    NotASection,
    NotATestPoint,
    ProjectVersionNotFound,
    RevisionConflict,
    RevisionFrozen,
    RevisionNotFound,
)
from stsd.library.domain.model import (
    LibNode,
    RevisionDetail,
    Section,
    TestPoint,
    TestPointVersion,
)
from stsd.library.ports import ProjectVersionLookup
from stsd.library.service_layer.unit_of_work import AbstractUnitOfWork
from stsd.library.service_layer.views import (
    SectionTreeNode,
    TestPointDetail,
    TestPointTreeNode,
    TreeNode,
)
from stsd.shared.implementation import (
    Implementation,
    InvalidImplementation,
    package_from_files,
    validate_implementation,
)


# ---------------------------------------------------------------------------
# 写操作
# ---------------------------------------------------------------------------
def create_section(uow: AbstractUnitOfWork,
                   command: CreateSection) -> SectionTreeNode:
    '''CreateSection：在项目内创建目录节点；parent_id 为空表示根下。'''
    _require_actor(command.actor_id)
    project_id = _require_text(command.project_id, 'project_id')
    name = _require_text(command.name, 'name')

    with uow:
        if command.parent_id is not None:
            _require_section(uow, project_id, command.parent_id)
        section = Section.create(
            project_id, command.parent_id, command.actor_id, name=name
        )
        uow.library.save(section)
        uow.commit()
        return _section_node(section)


def add_testpoint(uow: AbstractUnitOfWork, dep: ProjectVersionLookup,
                  command: AddTestPoint) -> TestPointTreeNode:
    '''AddTestPoint：新建测试点，同时产生 revision_ver 为 1 的第一条修订。

    第一条修订的实现为空，描述也为空；需要描述时再调用 ``revise_testpoint``。
    '''
    _require_actor(command.actor_id)
    project_id = _require_text(command.project_id, 'project_id')
    section_id = _require_text(command.section_id, 'section_id')
    name = _require_text(command.name, 'name')
    proj_ver = _require_text(command.proj_ver, 'proj_ver')

    with uow:
        _require_section(uow, project_id, section_id)
        _require_project_version(dep, project_id, proj_ver)

        testpoint = TestPoint.create(project_id, section_id, command.actor_id)
        testpoint.add_revision(
            proj_ver=proj_ver,
            detail=RevisionDetail(name=name),
            actor_id=command.actor_id,
        )
        uow.library.save(testpoint)
        uow.commit()

        node = _testpoint_node(testpoint)
        if node is None:  # pragma: no cover - add_revision 保证至少一条修订
            raise RevisionNotFound(testpoint.node_id, None)
        return node


def delete_node(uow: AbstractUnitOfWork,
                command: DeleteNode) -> list[str]:
    '''DeleteNode：软删除节点及其全部未删除的后代，返回被删除的节点 id。'''
    _require_actor(command.actor_id)

    with uow:
        root = _require_node(uow, command.node_id)
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
            node.soft_delete(command.actor_id)
        uow.library.save(*targets)
        uow.commit()
        return [node.node_id for node in targets]


def revise_testpoint(uow: AbstractUnitOfWork, dep: ProjectVersionLookup,
                     command: ReviseTestPoint) -> TestPointDetail:
    '''ReviseTestPoint：产生新修订，实现为空。

    内容与最新修订相同的测试点不产生新修订（见 library.md 规则 6），直接
    返回最新修订。``proj_ver`` 仍会先向 Access 确认存在。
    '''
    _require_actor(command.actor_id)
    proj_ver = _require_text(command.proj_ver, 'proj_ver')
    if not isinstance(command.revision_detail, RevisionDetail):
        raise InvalidArgument(
            'command.revision_detail must be a RevisionDetail'
        )

    with uow:
        testpoint = _require_testpoint(uow, command.testpoint_id)
        _require_project_version(dep, testpoint.project_id, proj_ver)

        if testpoint.content_unchanged(command.revision_detail):
            latest = testpoint.latest_revision
            if latest is None:  # pragma: no cover - content_unchanged 保证非空
                raise RevisionNotFound(command.testpoint_id, None)
            return _detail(testpoint, latest)

        revision = testpoint.add_revision(
            proj_ver, command.revision_detail, command.actor_id
        )
        try:
            uow.library.save(testpoint)
            uow.commit()
        except IntegrityError as exc:
            raise RevisionConflict(command.testpoint_id) from exc
        return _detail(testpoint, revision)


def set_implementation(uow: AbstractUnitOfWork,
                       command: SetImplementation) -> TestPointDetail:
    '''SetImplementation：为草稿修订整包设置或覆盖实现。'''
    _require_actor(command.actor_id)
    implementation = _require_implementation(command.implementation)
    files = _require_implementation_files(
        command.files, implementation
    )

    with uow:
        testpoint = _require_testpoint(uow, command.testpoint_id)
        revision = testpoint.set_implementation(
            command.revision_ver, implementation, command.actor_id
        )
        # 内容先落盘，声明随后与事务一起提交；提交失败最多留下孤儿内容。
        for item in implementation.source.files:
            uow.files.put(files[item.path])
        uow.library.save(testpoint)
        uow.commit()
        return _detail(testpoint, revision)


def audit_and_freeze(uow: AbstractUnitOfWork,
                     command: AuditAndFreeze) -> TestPointDetail:
    '''AuditAndFreeze：审计并冻结草稿；冻结要求实现完整且文件可读。'''
    _require_actor(command.actor_id)

    with uow:
        testpoint = _require_testpoint(uow, command.testpoint_id)
        revision = testpoint.revision(command.revision_ver)
        if revision is None:
            raise RevisionNotFound(
                command.testpoint_id, command.revision_ver
            )
        if revision.is_frozen:
            raise RevisionFrozen(
                command.testpoint_id, command.revision_ver
            )
        if revision.implementation is None:
            raise ImplementationRequired(
                command.testpoint_id, command.revision_ver
            )
        implementation = _require_implementation(revision.implementation)
        for item in implementation.source.files:
            # 读一遍而不是只查存在：内容被破坏时也要在冻结闸口暴露。
            uow.files.get(item.content_hash)
        revision = testpoint.freeze(command.revision_ver, command.actor_id)
        uow.library.save(testpoint)
        uow.commit()
        return _detail(testpoint, revision)


# ---------------------------------------------------------------------------
# 读接口
# ---------------------------------------------------------------------------
def get_section_tree(uow: AbstractUnitOfWork,
                     command: GetSectionTree) -> list[TreeNode]:
    '''get_section_tree：返回该节点下未删除的直接子节点。'''
    project_id = _require_text(command.project_id, 'project_id')

    with uow:
        if command.section_id is not None:
            section = _require_node(uow, command.section_id)
            if section.project_id != project_id:
                raise NodeNotFound(command.section_id)
            if not isinstance(section, Section):
                raise NotASection(command.section_id)
            if section.is_deleted:
                return []

        nodes: list[TreeNode] = []
        for node in uow.library.children(project_id, command.section_id):
            if node.is_deleted:
                continue
            if isinstance(node, Section):
                nodes.append(_section_node(node))
            else:
                testpoint_node = _testpoint_node(node)
                if testpoint_node is not None:
                    nodes.append(testpoint_node)
        return nodes


def get_testpoint_detail(uow: AbstractUnitOfWork,
                         command: GetTestPointDetail) -> TestPointDetail:
    '''get_testpoint_detail：读取一条修订及其所属测试点是否已删除。

    省略 ``revision_ver`` 时返回最新的已冻结修订；没有则报不存在。
    已删除的测试点仍然可以读取修订，供旧任务和历史复现使用。
    '''
    with uow:
        testpoint = _require_node(uow, command.testpoint_id)
        if not isinstance(testpoint, TestPoint):
            raise NotATestPoint(command.testpoint_id)

        if command.revision_ver is None:
            revision = testpoint.latest_frozen_revision
            if revision is None:
                raise RevisionNotFound(command.testpoint_id, None)
        else:
            revision = testpoint.revision(command.revision_ver)
            if revision is None:
                raise RevisionNotFound(
                    command.testpoint_id, command.revision_ver
                )
        return _detail(testpoint, revision)


def get_implementation_files(uow: AbstractUnitOfWork,
                             command: GetImplementationFiles
                             ) -> dict[str, str]:
    '''get_implementation_files：按包内路径返回一份实现的文件内容。

    已删除测试点的冻结修订仍然可读，供旧任务和历史复现使用。声明不存在
    或文件内容缺失时分别报错，不返回空映射掩盖问题。
    '''
    with uow:
        node = _require_node(uow, command.testpoint_id)
        if not isinstance(node, TestPoint):
            raise NotATestPoint(command.testpoint_id)
        revision = node.revision(command.revision_ver)
        if revision is None:
            raise RevisionNotFound(
                command.testpoint_id, command.revision_ver
            )
        if revision.implementation is None:
            raise ImplementationRequired(
                command.testpoint_id, command.revision_ver
            )
        implementation = _require_implementation(revision.implementation)
        return {
            item.path: uow.files.get(item.content_hash)
            for item in implementation.source.files
        }


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


def _require_implementation(value: object) -> Implementation:
    try:
        return validate_implementation(value)
    except InvalidImplementation as exc:
        raise ImplementationInvalid(str(exc)) from exc


def _require_implementation_files(
    files: object, implementation: Implementation
) -> dict[str, str]:
    if not isinstance(files, Mapping):
        raise ImplementationInvalid('files must be a mapping')
    try:
        delivered = package_from_files(files)
    except InvalidImplementation as exc:
        raise ImplementationInvalid(str(exc)) from exc
    if delivered != implementation.source:
        raise ImplementationInvalid(
            'files must exactly match implementation.source'
        )
    return dict(files)


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


def _require_project_version(dep: ProjectVersionLookup, project_id: str,
                             proj_ver: str) -> None:
    if not dep.project_version_exists(project_id, proj_ver):
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

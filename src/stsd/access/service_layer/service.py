'''Access 应用层。

服务函数的形状按是否需要外部端口区分：

- 需要外部端口：``(uow, dep, command)``；
- 不需要外部端口：``(uow, command)``。

Access 当前没有外部端口，所以所有用例都是 ``(uow, command)``。``command``
是 ``command.py`` 中定义的命令或读请求对象，承载本次调用的全部业务字段。
每个函数对应一个事务。Access 没有复杂的业务流转：写操作只做参数与引用
完整性检查，读操作把聚合投影成读模型。
'''

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.exc import IntegrityError

from stsd.access.command import (
    AddProjectVersion,
    AddUserToProject,
    CreateProject,
    CreateUser,
    GetProject,
    GetProjectMembers,
    GetProjectVersion,
    GetUserProjects,
    ListProjectVersions,
)
from stsd.access.domain.errors import (
    DuplicateProjectVersion,
    InvalidArgument,
    ProjectNotFound,
    ProjectVersionNotFound,
    UserNotFound,
)
from stsd.access.domain.model import (
    Document,
    Project,
    ProjectMember,
    ProjectVersion,
    User,
    UserInfo,
    new_id,
    now_utc,
)
from stsd.access.service_layer.unit_of_work import AbstractUnitOfWork
from stsd.access.service_layer.views import (
    DocumentView,
    ProjectMemberView,
    ProjectVersionView,
    ProjectView,
    UserView,
)


# ---------------------------------------------------------------------------
# 写操作
# ---------------------------------------------------------------------------
def create_user(uow: AbstractUnitOfWork,
                command: CreateUser) -> UserView:
    '''CreateUser：创建平台账号。'''
    _require_actor(command.actor_id)
    if not isinstance(command.user_info, UserInfo):
        raise InvalidArgument('command.user_info must be a UserInfo')

    email = command.user_info.email.strip() if command.user_info.email else None
    user = User(
        user_id=new_id(),
        name=command.user_info.name.strip(),
        email=email or None,
        created_by=command.actor_id,
        created_at=now_utc(),
    )
    with uow:
        uow.access.save(user)
        uow.commit()
        return _user_view(user)


def create_project(uow: AbstractUnitOfWork,
                   command: CreateProject) -> ProjectView:
    '''CreateProject：创建项目并保存链接 Web 的基本配置。'''
    _require_actor(command.actor_id)
    name = _require_text(command.project_name, 'project_name')
    config = _normalize_web_config(command.web_config)

    project = Project(
        project_id=new_id(),
        name=name,
        web_config=config,
        created_by=command.actor_id,
        created_at=now_utc(),
    )
    with uow:
        uow.access.save(project)
        uow.commit()
        return _project_view(project)


def add_project_version(uow: AbstractUnitOfWork,
                        command: AddProjectVersion) -> ProjectVersionView:
    '''AddProjectVersion：添加项目版本及其全部文档。

    项目版本添加后不可修改，也不可删除；文档在添加时一次性提供。
    '''
    _require_actor(command.actor_id)
    proj_ver = _require_text(command.proj_ver, 'proj_ver')
    normalized_docs = _normalize_docs(command.docs)

    with uow:
        _require_project(uow, command.project_id)
        if uow.access.get_project_version(
            command.project_id, proj_ver
        ) is not None:
            raise DuplicateProjectVersion(command.project_id, proj_ver)

        version = ProjectVersion(
            project_id=command.project_id,
            proj_ver=proj_ver,
            docs=normalized_docs,
            created_by=command.actor_id,
            created_at=now_utc(),
        )
        try:
            uow.access.save(version)
            uow.commit()
        except IntegrityError as exc:
            # 并发添加同一版本时，唯一约束会兜底。
            raise DuplicateProjectVersion(command.project_id, proj_ver) from exc
        return _version_view(version)


def add_user_to_project(uow: AbstractUnitOfWork,
                        command: AddUserToProject) -> ProjectMemberView:
    '''AddUserToProject：把用户加入项目。

    重复添加按幂等处理，返回已有的成员关系。
    '''
    _require_actor(command.actor_id)

    with uow:
        _require_project(uow, command.project_id)
        user = uow.access.get_user(command.target_user_id)
        if user is None:
            raise UserNotFound(command.target_user_id)

        existing = uow.access.get_member(
            command.project_id, command.target_user_id
        )
        if existing is not None:
            return _member_view(user, existing)

        member = ProjectMember(
            project_id=command.project_id,
            user_id=command.target_user_id,
            added_by=command.actor_id,
            added_at=now_utc(),
        )
        try:
            uow.access.save(member)
            uow.commit()
        except IntegrityError:
            # 并发重复添加：回滚后读取已存在的成员关系。
            uow.rollback()
            existing = uow.access.get_member(
                command.project_id, command.target_user_id
            )
            if existing is None:
                raise
            return _member_view(user, existing)
        return _member_view(user, member)


# ---------------------------------------------------------------------------
# 读接口
# ---------------------------------------------------------------------------
def get_user_projects(uow: AbstractUnitOfWork,
                      command: GetUserProjects) -> list[ProjectView]:
    '''get_user_projects：列出用户所属的全部项目。'''
    with uow:
        if uow.access.get_user(command.user_id) is None:
            raise UserNotFound(command.user_id)
        return [_project_view(project)
                for project in uow.access.list_user_projects(command.user_id)]


def get_project(uow: AbstractUnitOfWork,
                command: GetProject) -> ProjectView:
    '''get_project：按 project_id 读取项目的基本配置。'''
    with uow:
        return _project_view(_require_project(uow, command.project_id))


def get_project_members(uow: AbstractUnitOfWork,
                        command: GetProjectMembers) -> list[ProjectMemberView]:
    '''get_project_members：列出项目成员及成员关系。'''
    with uow:
        _require_project(uow, command.project_id)
        return [_member_view(user, member)
                for user, member in uow.access.list_project_members(
                    command.project_id)]


def list_project_versions(uow: AbstractUnitOfWork,
                          command: ListProjectVersions) -> list[str]:
    '''list_project_versions：列出项目的全部版本，供界面选择。'''
    with uow:
        _require_project(uow, command.project_id)
        return uow.access.list_project_versions(command.project_id)


def get_project_version(uow: AbstractUnitOfWork,
                        command: GetProjectVersion) -> ProjectVersionView:
    '''get_project_version：返回版本及其全部文档，不存在时报不存在。'''
    with uow:
        _require_project(uow, command.project_id)
        version = uow.access.get_project_version(
            command.project_id, command.proj_ver
        )
        if version is None:
            raise ProjectVersionNotFound(command.project_id, command.proj_ver)
        return _version_view(version)


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


def _require_project(uow: AbstractUnitOfWork, project_id: str) -> Project:
    project = uow.access.get_project(project_id)
    if project is None:
        raise ProjectNotFound(project_id)
    return project


def _normalize_web_config(web_config: Mapping[str, Any]) -> dict[str, Any]:
    '''确保配置是 JSON 对象，并做一次深拷贝。'''
    if not isinstance(web_config, Mapping):
        raise InvalidArgument('web_config must be a mapping')
    try:
        normalized = json.loads(
            json.dumps(dict(web_config), ensure_ascii=False)
        )
    except (TypeError, ValueError) as exc:
        raise InvalidArgument('web_config must be JSON serializable') from exc
    if not isinstance(normalized, dict):
        raise InvalidArgument('web_config must serialize to a JSON object')
    return normalized


def _normalize_docs(docs: Sequence[Document]) -> tuple[Document, ...]:
    if isinstance(docs, (str, bytes)) or not isinstance(docs, Sequence):
        raise InvalidArgument('docs must be a sequence of Document')
    normalized: list[Document] = []
    for doc in docs:
        if not isinstance(doc, Document):
            raise InvalidArgument('each document must be a Document')
        normalized.append(doc)
    return tuple(normalized)


def _user_view(user: User) -> UserView:
    return UserView(user_id=user.user_id, name=user.name, email=user.email)


def _project_view(project: Project) -> ProjectView:
    return ProjectView(
        project_id=project.project_id,
        name=project.name,
        web_config=json.loads(json.dumps(project.web_config)),
        created_at=project.created_at,
    )


def _member_view(user: User, member: ProjectMember) -> ProjectMemberView:
    return ProjectMemberView(
        project_id=member.project_id,
        user_id=user.user_id,
        name=user.name,
        email=user.email,
        added_by=member.added_by,
        added_at=member.added_at,
    )


def _version_view(version: ProjectVersion) -> ProjectVersionView:
    return ProjectVersionView(
        project_id=version.project_id,
        proj_ver=version.proj_ver,
        docs=tuple(DocumentView(kind=doc.kind, text=doc.text)
                   for doc in version.docs),
        created_at=version.created_at,
    )

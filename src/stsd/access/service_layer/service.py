'''Access 应用层。

每个函数是一个用例，对应一个事务。Access 没有复杂的业务流转：
写操作只做参数与引用完整性检查，读操作把聚合投影成读模型。


'''

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.exc import IntegrityError

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
def create_user(uow: AbstractUnitOfWork, actor_id: str,
                user_info: UserInfo) -> UserView:
    '''CreateUser：创建平台账号。'''
    _require_actor(actor_id)
    if not isinstance(user_info, UserInfo):
        raise InvalidArgument('user_info must be a UserInfo')

    email = user_info.email.strip() if user_info.email else None
    user = User(
        user_id=new_id(),
        name=user_info.name.strip(),
        email=email or None,
        created_by=actor_id,
        created_at=now_utc(),
    )
    with uow:
        uow.access.save(user)
        uow.commit()
        return _user_view(user)


def create_project(uow: AbstractUnitOfWork, actor_id: str, project_name: str,
                   web_config: Mapping[str, Any]) -> ProjectView:
    '''
    CreateProject：创建项目并保存链接 Web 的基本配置。
    '''
    _require_actor(actor_id)
    name = _require_text(project_name, 'project_name')
    config = _normalize_web_config(web_config)

    project = Project(
        project_id=new_id(),
        name=name,
        web_config=config,
        created_by=actor_id,
        created_at=now_utc(),
    )
    with uow:
        uow.access.save(project)
        uow.commit()
        return _project_view(project)


def add_project_version(uow: AbstractUnitOfWork, actor_id: str,
                        project_id: str, proj_ver: str,
                        docs: Sequence[Document]) -> ProjectVersionView:
    '''AddProjectVersion：添加项目版本及其全部文档。

    项目版本添加后不可修改，也不可删除；文档在添加时一次性提供。
    '''
    _require_actor(actor_id)
    proj_ver = _require_text(proj_ver, 'proj_ver')
    normalized_docs = _normalize_docs(docs)

    with uow:
        _require_project(uow, project_id)
        if uow.access.get_project_version(project_id, proj_ver) is not None:
            raise DuplicateProjectVersion(project_id, proj_ver)

        version = ProjectVersion(
            project_id=project_id,
            proj_ver=proj_ver,
            docs=normalized_docs,
            created_by=actor_id,
            created_at=now_utc(),
        )
        try:
            uow.access.save(version)
            uow.commit()
        except IntegrityError as exc:
            # 并发添加同一版本时，唯一约束会兜底。
            raise DuplicateProjectVersion(project_id, proj_ver) from exc
        return _version_view(version)


def add_user_to_project(uow: AbstractUnitOfWork, actor_id: str,
                        project_id: str,
                        target_user_id: str) -> ProjectMemberView:
    '''AddUserToProject：把用户加入项目。

    重复添加按幂等处理，返回已有的成员关系。
    '''
    _require_actor(actor_id)

    with uow:
        _require_project(uow, project_id)
        user = uow.access.get_user(target_user_id)
        if user is None:
            raise UserNotFound(target_user_id)

        existing = uow.access.get_member(project_id, target_user_id)
        if existing is not None:
            return _member_view(user, existing)

        member = ProjectMember(
            project_id=project_id,
            user_id=target_user_id,
            added_by=actor_id,
            added_at=now_utc(),
        )
        try:
            uow.access.save(member)
            uow.commit()
        except IntegrityError:
            # 并发重复添加：回滚后读取已存在的成员关系。
            uow.rollback()
            existing = uow.access.get_member(project_id, target_user_id)
            if existing is None:
                raise
            return _member_view(user, existing)
        return _member_view(user, member)


# ---------------------------------------------------------------------------
# 读接口
# ---------------------------------------------------------------------------
def get_user_projects(uow: AbstractUnitOfWork,
                      user_id: str) -> list[ProjectView]:
    '''get_user_projects：列出用户所属的全部项目。'''
    with uow:
        if uow.access.get_user(user_id) is None:
            raise UserNotFound(user_id)
        return [_project_view(project)
                for project in uow.access.list_user_projects(user_id)]


def get_project_members(uow: AbstractUnitOfWork,
                        project_id: str) -> list[ProjectMemberView]:
    '''get_project_members：列出项目成员及成员关系。'''
    with uow:
        _require_project(uow, project_id)
        return [_member_view(user, member)
                for user, member in uow.access.list_project_members(project_id)]


def list_project_versions(uow: AbstractUnitOfWork,
                          project_id: str) -> list[str]:
    '''list_project_versions：列出项目的全部版本，供界面选择。'''
    with uow:
        _require_project(uow, project_id)
        return uow.access.list_project_versions(project_id)


def get_project_version(uow: AbstractUnitOfWork, project_id: str,
                        proj_ver: str) -> ProjectVersionView:
    '''get_project_version：返回版本及其全部文档，不存在时报不存在。'''
    with uow:
        _require_project(uow, project_id)
        version = uow.access.get_project_version(project_id, proj_ver)
        if version is None:
            raise ProjectVersionNotFound(project_id, proj_ver)
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


# 让类型检查器知道本模块公开的用例函数。
__all__ = [
    'add_project_version',
    'add_user_to_project',
    'create_project',
    'create_user',
    'get_project_members',
    'get_project_version',
    'get_user_projects',
    'list_project_versions',
]

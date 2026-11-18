'''Access 仓储。

仓储只负责持久化，不提交事务；事务边界由工作单元负责。
'''

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.model import Project, ProjectMember, ProjectVersion, User
from .orm import (project_members, project_versions, projects, users)


class AccessRepository(Protocol):
    def get_user(self, user_id: str) -> User | None: ...

    def get_project(self, project_id: str) -> Project | None: ...

    def get_project_version(
        self, project_id: str, proj_ver: str
    ) -> ProjectVersion | None: ...

    def get_member(self, project_id: str, user_id: str) -> ProjectMember | None:
        ...

    def list_user_projects(self, user_id: str) -> list[Project]: ...

    def list_project_versions(self, project_id: str) -> list[str]: ...

    def list_project_members(
        self, project_id: str
    ) -> list[tuple[User, ProjectMember]]: ...

    def save(self, *entities: object) -> None:
        '''保存实体并 flush，让数据库约束错误在服务层可被捕获。'''
        ...


class SqlAlchemyAccessRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_user(self, user_id: str) -> User | None:
        return self._session.get(User, user_id)

    def get_project(self, project_id: str) -> Project | None:
        return self._session.get(Project, project_id)

    def get_project_version(
        self, project_id: str, proj_ver: str
    ) -> ProjectVersion | None:
        return self._session.get(ProjectVersion, (project_id, proj_ver))

    def get_member(self, project_id: str, user_id: str) -> ProjectMember | None:
        return self._session.get(ProjectMember, (project_id, user_id))

    def list_user_projects(self, user_id: str) -> list[Project]:
        stmt = (
            select(Project)
            .join(
                project_members,
                project_members.c.project_id == projects.c.project_id,
            )
            .where(project_members.c.user_id == user_id)
            .order_by(projects.c.created_at, projects.c.project_id)
        )
        return list(self._session.scalars(stmt))

    def list_project_versions(self, project_id: str) -> list[str]:
        stmt = (
            select(project_versions.c.proj_ver)
            .where(project_versions.c.project_id == project_id)
            .order_by(project_versions.c.created_at, project_versions.c.proj_ver)
        )
        return list(self._session.scalars(stmt))

    def list_project_members(
        self, project_id: str
    ) -> list[tuple[User, ProjectMember]]:
        stmt = (
            select(User, ProjectMember)
            .join(
                project_members,
                project_members.c.user_id == users.c.user_id,
            )
            .where(project_members.c.project_id == project_id)
            .order_by(project_members.c.added_at, users.c.user_id)
        )
        return [(row[0], row[1]) for row in self._session.execute(stmt)]

    def save(self, *entities: object) -> None:
        self._session.add_all(list(entities))
        self._session.flush()

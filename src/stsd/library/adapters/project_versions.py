'''用例库对 Access 读接口的适配。

用例库只依赖自己定义的 ``ProjectVersionLookup`` 端口；本文件把该端口实现
为对 Access ``get_project_version`` 的调用。Access 报“项目或版本不存在”
时，对用例库就等价于“版本不存在”。
'''

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from stsd.access import (
    GetProjectVersion,
    ProjectNotFound,
    ProjectVersionNotFound,
    get_project_version,
)
from stsd.access import SqlAlchemyUnitOfWork as AccessUnitOfWork
from stsd.library.ports import ProjectVersionLookup


class AccessProjectVersionLookup(ProjectVersionLookup):
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def project_version_exists(self, project_id: str, proj_ver: str) -> bool:
        try:
            with AccessUnitOfWork(self._session_factory) as uow:
                get_project_version(
                    uow,
                    GetProjectVersion(project_id=project_id, proj_ver=proj_ver),
                )
        except (ProjectNotFound, ProjectVersionNotFound):
            return False
        return True

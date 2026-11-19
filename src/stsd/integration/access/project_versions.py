'''用例库对 Access 读接口的适配。

用例库只依赖自己定义的 ``ProjectVersionLookup`` 端口；本文件把一个
"读 Access 项目版本"的可调用对象适配成该端口。它不关心 Access 的会话和
工作单元从哪来——组装根把已经装配好的 ``AccessApp.get_project_version``
传进来，因此这里只依赖 Access 的公开类型和错误。

Access 报"项目不存在"或"版本不存在"时，对用例库都等价于"版本不存在"，
统一折叠为 ``False``。
'''

from __future__ import annotations

from collections.abc import Callable

from stsd.access import (
    GetProjectVersion,
    ProjectNotFound,
    ProjectVersionNotFound,
    ProjectVersionView,
)
from stsd.library.ports import ProjectVersionLookup


class AccessProjectVersionLookup(ProjectVersionLookup):
    def __init__(
        self,
        read_project_version: Callable[[GetProjectVersion], ProjectVersionView],
    ) -> None:
        self._read_project_version = read_project_version

    def project_version_exists(self, project_id: str, proj_ver: str) -> bool:
        try:
            self._read_project_version(
                GetProjectVersion(project_id=project_id, proj_ver=proj_ver)
            )
        except (ProjectNotFound, ProjectVersionNotFound):
            return False
        return True

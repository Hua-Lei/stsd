'''执行器对 Access 项目配置的适配。

执行器绑定 ``base_url`` 时要知道项目上的 ``web_config``；本文件把一个
"读 Access 项目"的可调用对象收敛成只暴露这份配置的最小查询。Access 报
项目不存在时折叠为 ``None``，其他错误照常抛出，由执行器决定是否记为
``not_run``。
'''

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from stsd.access import GetProject, ProjectNotFound, ProjectView


class AccessProjectConfigLookup:
    def __init__(
        self,
        read_project: Callable[[GetProject], ProjectView],
    ) -> None:
        self._read_project = read_project

    def get_web_config(self, project_id: str) -> dict[str, Any] | None:
        '''项目存在时返回 ``web_config`` 的副本，不存在返回 ``None``。'''
        try:
            project = self._read_project(
                GetProject(project_id=project_id)
            )
        except ProjectNotFound:
            return None
        return dict(project.web_config)

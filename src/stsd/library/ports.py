'''用例库依赖的外部端口。

用例库不直接引用 Access 的对象，只保存 ``project_id`` 和 ``proj_ver`` 的值。
它自己定义下面这个小接口，只回答“某项目有没有某个 proj_ver”；真实实现
由适配器包装 Access 的 ``get_project_version`` 提供。
'''

from __future__ import annotations

from typing import Protocol


class ProjectVersionLookup(Protocol):
    def project_version_exists(self, project_id: str, proj_ver: str) -> bool:
        '''项目版本存在返回 True，否则返回 False。'''
        ...

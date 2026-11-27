'''用例库依赖的外部端口。

用例库不直接引用 Access 的对象，只保存 ``project_id`` 和 ``proj_ver`` 的值。
它自己定义两个接口：``ProjectVersionLookup`` 只回答“某项目有没有某个
proj_ver”；``ImplementationFileStore`` 按内容哈希读写实现文件内容。真实实现
分别由集成层和适配器提供。
'''

from __future__ import annotations

from typing import Protocol


class ProjectVersionLookup(Protocol):
    def project_version_exists(self, project_id: str, proj_ver: str) -> bool:
        '''项目版本存在返回 True，否则返回 False。'''
        ...


class ImplementationFileStore(Protocol):
    """实现文件内容的内容寻址存储。

    ``put`` 按内容哈希去重并返回 ``sha256:<hex>``；``get`` 取回原文，内容
    缺失或与哈希不一致时由适配器报错。文件内容不进 SQL，声明里的
    ``File.content_hash`` 是这里的键。
    """

    def put(self, content: str) -> str:
        '''保存一份内容，返回内容哈希。'''
        ...

    def get(self, content_hash: str) -> str:
        '''按内容哈希取回原文。'''
        ...

    def exists(self, content_hash: str) -> bool:
        '''内容是否存在。'''
        ...

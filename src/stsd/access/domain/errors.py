'''Access 模块的错误。

每个异常带一个稳定的 ``code``，入口层（HTTP/CLI）只需要捕获
``AccessError`` 并读取 ``code`` 与 ``message``，不需要认识每个子类。
'''

from __future__ import annotations


class AccessError(Exception):
    '''Access 模块所有业务错误的基类。'''

    code: str = 'ACCESS_ERROR'

    def __init__(self, message: str = '') -> None:
        self.message = message or self.code
        super().__init__(self.message)


class InvalidArgument(AccessError):
    '''入参不满足形状或取值要求。'''

    code = 'INVALID_ARGUMENT'


class UserNotFound(AccessError):
    code = 'USER_NOT_FOUND'

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f'user {user_id!r} not found')


class ProjectNotFound(AccessError):
    code = 'PROJECT_NOT_FOUND'

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        super().__init__(f'project {project_id!r} not found')


class ProjectVersionNotFound(AccessError):
    code = 'PROJECT_VERSION_NOT_FOUND'

    def __init__(self, project_id: str, proj_ver: str) -> None:
        self.project_id = project_id
        self.proj_ver = proj_ver
        super().__init__(
            f'project {project_id!r} has no version {proj_ver!r}'
        )


class DuplicateProjectVersion(AccessError):
    '''同一项目内 ``proj_ver`` 唯一，重复添加时报错。'''

    code = 'DUPLICATE_PROJECT_VERSION'

    def __init__(self, project_id: str, proj_ver: str) -> None:
        self.project_id = project_id
        self.proj_ver = proj_ver
        super().__init__(
            f'project {project_id!r} already has version {proj_ver!r}'
        )

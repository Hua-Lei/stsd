'''Access 模块。

管理用户、项目、项目版本及其文档、项目成员，是其他模块的基础支撑。
其他模块只使用这里导出的读接口；写操作由 Access 自己或 API 层调用。
'''

from stsd.access.domain.errors import (
    AccessError,
    DuplicateProjectVersion,
    InvalidArgument,
    ProjectNotFound,
    ProjectVersionNotFound,
    UserNotFound,
)
from stsd.access.domain.model import Document, DocumentKind, ProjectVersion, UserInfo
from stsd.access.service_layer.service import (
    add_project_version,
    add_user_to_project,
    create_project,
    create_user,
    get_project_members,
    get_project_version,
    get_user_projects,
    list_project_versions,
)
from stsd.access.service_layer.unit_of_work import (
    AbstractUnitOfWork,
    SqlAlchemyUnitOfWork,
)
from stsd.access.service_layer.views import (
    DocumentView,
    ProjectMemberView,
    ProjectVersionView,
    ProjectView,
    UserView,
)

__all__ = [
    'AbstractUnitOfWork',
    'AccessError',
    'Document',
    'DocumentKind',
    'DocumentView',
    'DuplicateProjectVersion',
    'InvalidArgument',
    'ProjectMemberView',
    'ProjectNotFound',
    'ProjectVersion',
    'ProjectVersionNotFound',
    'ProjectVersionView',
    'ProjectView',
    'SqlAlchemyUnitOfWork',
    'UserInfo',
    'UserNotFound',
    'UserView',
    'add_project_version',
    'add_user_to_project',
    'create_project',
    'create_user',
    'get_project_members',
    'get_project_version',
    'get_user_projects',
    'list_project_versions',
]

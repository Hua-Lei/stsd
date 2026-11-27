'''Access 模块。

管理用户、项目、项目版本及其文档、项目成员，是其他模块的基础支撑。
其他模块只使用这里导出的读接口；写操作由 Access 自己或 API 层调用。

模块门面的服务接口形状为 ``(uow, command)``，命令与读请求对象见
``stsd.access.command``。应用外层使用 ``build_access_app`` 装配好的
``AccessApp``：每个用例只接收一个 command，工作单元在内部创建。
'''

from stsd.access.app import AccessApp, build_access_app
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
    AccessError,
    DuplicateProjectVersion,
    InvalidArgument,
    ProjectNotFound,
    ProjectVersionNotFound,
    UserNotFound,
)

# 只导出命令的输入类型。Project、ProjectVersion、User、ProjectMember 是被
# ORM 映射的聚合，留在模块内部；外部读到的是 views 里的读模型。
from stsd.access.domain.model import Document, DocumentKind, UserInfo
from stsd.access.service_layer.service import (
    add_project_version,
    add_user_to_project,
    create_project,
    create_user,
    get_project,
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
    'AccessApp',
    'AccessError',
    'AddProjectVersion',
    'AddUserToProject',
    'CreateProject',
    'CreateUser',
    'Document',
    'DocumentKind',
    'DocumentView',
    'DuplicateProjectVersion',
    'GetProject',
    'GetProjectMembers',
    'GetProjectVersion',
    'GetUserProjects',
    'InvalidArgument',
    'ListProjectVersions',
    'ProjectMemberView',
    'ProjectNotFound',
    'ProjectVersionNotFound',
    'ProjectVersionView',
    'ProjectView',
    'SqlAlchemyUnitOfWork',
    'UserInfo',
    'UserNotFound',
    'UserView',
    'add_project_version',
    'add_user_to_project',
    'build_access_app',
    'create_project',
    'create_user',
    'get_project',
    'get_project_members',
    'get_project_version',
    'get_user_projects',
    'list_project_versions',
]

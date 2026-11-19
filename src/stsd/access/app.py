'''Access 的用例入口（应用装配）。

模块门面里的服务函数形状是 ``(uow, command)``，工作单元由调用方提供，
供模块内测试和组合使用。若要在应用外层调用，需要把工作单元的创建、事件
发布者等基础设施装配进来；这是本文件的职责。

``build_access_app`` 把每个用例绑定成一个只接收 ``command`` 的可调用对象：
工作单元在每次调用时新建，事务边界仍由服务层的 ``with uow`` 决定。这样
外层（``stsd.bootstrap``、HTTP 层）看不到工作单元和会话，每个用例只有一种
调用形状，且带完整类型。
'''

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from sqlalchemy.orm import Session, sessionmaker

from stsd.access.command import (
    AddProjectVersion,
    AddUserToProject,
    CreateProject,
    CreateUser,
    GetProjectMembers,
    GetProjectVersion,
    GetUserProjects,
    ListProjectVersions,
)
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
    ProjectMemberView,
    ProjectVersionView,
    ProjectView,
    UserView,
)
from stsd.shared.events import EventPublisher, NullPublisher

CommandT = TypeVar('CommandT')
ResultT = TypeVar('ResultT')


@dataclass(frozen=True)
class AccessApp:
    '''Access 的用例入口：每个字段只接收一个命令/请求对象。'''

    create_user: Callable[[CreateUser], UserView]
    create_project: Callable[[CreateProject], ProjectView]
    add_project_version: Callable[[AddProjectVersion], ProjectVersionView]
    add_user_to_project: Callable[[AddUserToProject], ProjectMemberView]
    get_user_projects: Callable[[GetUserProjects], list[ProjectView]]
    get_project_members: Callable[[GetProjectMembers], list[ProjectMemberView]]
    list_project_versions: Callable[[ListProjectVersions], list[str]]
    get_project_version: Callable[[GetProjectVersion], ProjectVersionView]


def build_access_app(
    session_factory: sessionmaker[Session],
    publisher: EventPublisher | None = None,
) -> AccessApp:
    '''把 Access 的用例绑定成 ``command -> 读模型`` 的可调用对象。

    ``publisher`` 会交给每个工作单元，事件在 ``commit()`` 成功后才发布；
    不传时使用 ``NullPublisher``。
    '''
    publisher = publisher or NullPublisher()

    def bind(
        use_case: Callable[[AbstractUnitOfWork, CommandT], ResultT],
    ) -> Callable[[CommandT], ResultT]:
        def bound(command: CommandT) -> ResultT:
            uow = SqlAlchemyUnitOfWork(session_factory, publisher)
            return use_case(uow, command)

        return bound

    return AccessApp(
        create_user=bind(create_user),
        create_project=bind(create_project),
        add_project_version=bind(add_project_version),
        add_user_to_project=bind(add_user_to_project),
        get_user_projects=bind(get_user_projects),
        get_project_members=bind(get_project_members),
        list_project_versions=bind(list_project_versions),
        get_project_version=bind(get_project_version),
    )

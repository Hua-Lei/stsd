'''用例库模块。

管理项目内的 Section 树和测试点的修订历史；决定一条修订何时成为可被任务
引用的不可变资产。只通过 ``ProjectVersionLookup`` 端口向 Access 确认
``proj_ver`` 存在，不引用 Access 的对象。

需要 ``ProjectVersionLookup`` 的服务接口形状为 ``(uow, dep, command)``，
其余为 ``(uow, command)``；命令与读请求对象见 ``stsd.library.command``。
'''

from stsd.library.command import (
    AddImplementation,
    AddTestPoint,
    AuditAndFreeze,
    CreateSection,
    DeleteNode,
    GetSectionTree,
    GetTestPointDetail,
    ReviseTestPoint,
)
from stsd.library.domain.errors import (
    ImplementationRequired,
    InvalidArgument,
    LibraryError,
    NodeDeleted,
    NodeNotFound,
    NotASection,
    NotATestPoint,
    ProjectVersionNotFound,
    RevisionConflict,
    RevisionFrozen,
    RevisionNotFound,
)

# 只导出命令的输入类型与读模型用到的字面量类型。Section、TestPoint、
# TestPointVersion 是被 ORM 映射的聚合，留在模块内部，外部改不到它们。
from stsd.library.domain.model import RevisionDetail, RevisionStatus
from stsd.library.ports import ProjectVersionLookup
from stsd.library.service_layer.service import (
    add_implementation,
    add_testpoint,
    audit_and_freeze,
    create_section,
    delete_node,
    get_section_tree,
    get_testpoint_detail,
    revise_testpoint,
)
from stsd.library.service_layer.unit_of_work import (
    AbstractUnitOfWork,
    SqlAlchemyUnitOfWork,
)
from stsd.library.service_layer.views import (
    SectionTreeNode,
    TestPointDetail,
    TestPointTreeNode,
    TreeNode,
)

__all__ = [
    'AbstractUnitOfWork',
    'AddImplementation',
    'AddTestPoint',
    'AuditAndFreeze',
    'CreateSection',
    'DeleteNode',
    'GetSectionTree',
    'GetTestPointDetail',
    'ImplementationRequired',
    'InvalidArgument',
    'LibraryError',
    'NodeDeleted',
    'NodeNotFound',
    'NotASection',
    'NotATestPoint',
    'ProjectVersionLookup',
    'ProjectVersionNotFound',
    'ReviseTestPoint',
    'RevisionConflict',
    'RevisionDetail',
    'RevisionFrozen',
    'RevisionNotFound',
    'RevisionStatus',
    'SectionTreeNode',
    'SqlAlchemyUnitOfWork',
    'TestPointDetail',
    'TestPointTreeNode',
    'TreeNode',
    'add_implementation',
    'add_testpoint',
    'audit_and_freeze',
    'create_section',
    'delete_node',
    'get_section_tree',
    'get_testpoint_detail',
    'revise_testpoint',
]

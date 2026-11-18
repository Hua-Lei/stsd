'''用例库模块。

管理项目内的 Section 树和测试点的修订历史；决定一条修订何时成为可被任务
引用的不可变资产。只通过 ``ProjectVersionLookup`` 端口向 Access 确认
``proj_ver`` 存在，不引用 Access 的对象。
'''

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
from stsd.library.domain.model import (
    RevisionDetail,
    RevisionStatus,
    Section,
    TestPoint,
    TestPointVersion,
)
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
    'ImplementationRequired',
    'InvalidArgument',
    'LibraryError',
    'NodeDeleted',
    'NodeNotFound',
    'NotASection',
    'NotATestPoint',
    'ProjectVersionLookup',
    'ProjectVersionNotFound',
    'RevisionConflict',
    'RevisionDetail',
    'RevisionFrozen',
    'RevisionNotFound',
    'RevisionStatus',
    'Section',
    'SectionTreeNode',
    'SqlAlchemyUnitOfWork',
    'TestPoint',
    'TestPointDetail',
    'TestPointTreeNode',
    'TestPointVersion',
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

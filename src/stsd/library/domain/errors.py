'''用例库模块的错误。

``code`` 是稳定的错误标识，供入口层映射成 HTTP 响应；``message`` 面向开发者，
包含定位问题所需的标识。
'''

from __future__ import annotations


class LibraryError(Exception):
    '''用例库所有业务错误的基类。'''

    code: str = 'LIBRARY_ERROR'

    def __init__(self, message: str = '') -> None:
        self.message = message or self.code
        super().__init__(self.message)


class InvalidArgument(LibraryError):
    code = 'INVALID_ARGUMENT'


class NodeNotFound(LibraryError):
    code = 'NODE_NOT_FOUND'

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        super().__init__(f'node {node_id!r} not found')


class NodeDeleted(LibraryError):
    code = 'NODE_DELETED'

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        super().__init__(f'node {node_id!r} is deleted')


class NotASection(LibraryError):
    code = 'NOT_A_SECTION'

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        super().__init__(f'node {node_id!r} is not a section')


class NotATestPoint(LibraryError):
    code = 'NOT_A_TESTPOINT'

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        super().__init__(f'node {node_id!r} is not a testpoint')


class RevisionNotFound(LibraryError):
    code = 'REVISION_NOT_FOUND'

    def __init__(self, testpoint_id: str, revision_ver: int | None) -> None:
        self.testpoint_id = testpoint_id
        self.revision_ver = revision_ver
        if revision_ver is None:
            message = f'testpoint {testpoint_id!r} has no frozen revision'
        else:
            message = (
                f'testpoint {testpoint_id!r} has no revision {revision_ver}'
            )
        super().__init__(message)


class RevisionConflict(LibraryError):
    '''并发产生修订时，``(testpoint_id, revision_ver)`` 必须唯一。'''

    code = 'REVISION_CONFLICT'

    def __init__(self, testpoint_id: str) -> None:
        self.testpoint_id = testpoint_id
        super().__init__(
            f'concurrent revision detected for testpoint {testpoint_id!r}'
        )


class ProjectVersionNotFound(LibraryError):
    '''受依赖的 Access 项目版本不存在。'''

    code = 'PROJECT_VERSION_NOT_FOUND'

    def __init__(self, project_id: str, proj_ver: str) -> None:
        self.project_id = project_id
        self.proj_ver = proj_ver
        super().__init__(
            f'project {project_id!r} has no version {proj_ver!r}'
        )


class ImplementationRequired(LibraryError):
    '''冻结要求实现非空。'''

    code = 'IMPLEMENTATION_REQUIRED'

    def __init__(self, testpoint_id: str, revision_ver: int) -> None:
        self.testpoint_id = testpoint_id
        self.revision_ver = revision_ver
        super().__init__(
            f'revision {revision_ver} of testpoint {testpoint_id!r} '
            f'has no implementation'
        )


class ImplementationInvalid(LibraryError):
    '''实现声明或随声明提交的文件包不合法。'''

    code = 'INVALID_IMPLEMENTATION'


class ImplementationFileMissing(LibraryError):
    '''声明的文件在内容存储里不存在，或内容与声明的哈希不一致。'''

    code = 'IMPLEMENTATION_FILE_MISSING'

    def __init__(self, content_hash: str) -> None:
        self.content_hash = content_hash
        super().__init__(
            f'implementation file content {content_hash!r} is missing'
        )


class ImplementationStorageError(LibraryError):
    '''内容存储读写失败。'''

    code = 'IMPLEMENTATION_STORAGE_ERROR'


class RevisionFrozen(LibraryError):
    '''已冻结的修订内容与实现都不可变，冻结不可撤销。'''

    code = 'REVISION_FROZEN'

    def __init__(self, testpoint_id: str, revision_ver: int) -> None:
        self.testpoint_id = testpoint_id
        self.revision_ver = revision_ver
        super().__init__(
            f'revision {revision_ver} of testpoint {testpoint_id!r} '
            f'is frozen'
        )

'''用例库工作单元。

一次业务用例一个事务：进入时创建会话与仓储，退出时回滚未提交的改动，
提交必须显式调用 ``commit()``。

``project_versions`` 是用例库依赖的 Access 只读端口。测试可以注入内存实现；
默认实现包装 Access 的 ``get_project_version``。
'''

from __future__ import annotations

import abc
from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from stsd.library.adapters.repository import (
    LibraryRepository,
    SqlAlchemyLibraryRepository,
)
from stsd.library.ports import ProjectVersionLookup


class AbstractUnitOfWork(abc.ABC):
    library: LibraryRepository
    project_versions: ProjectVersionLookup

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.rollback()

    @abc.abstractmethod
    def commit(self) -> None: ...

    @abc.abstractmethod
    def rollback(self) -> None: ...


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        project_versions: ProjectVersionLookup | None = None,
    ) -> None:
        self._session_factory = session_factory
        if project_versions is None:
            # 延迟导入，避免 library 在只需要领域对象时也加载 Access 服务。
            from stsd.library.adapters.project_versions import (
                AccessProjectVersionLookup,
            )

            project_versions = AccessProjectVersionLookup(session_factory)
        self.project_versions = project_versions

    def __enter__(self) -> Self:
        self._session = self._session_factory()
        self.library = SqlAlchemyLibraryRepository(self._session)
        return super().__enter__()

    def __exit__(self, *args: object) -> None:
        super().__exit__(*args)
        self._session.close()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

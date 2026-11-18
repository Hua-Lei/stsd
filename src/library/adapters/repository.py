'''用例库仓储。

仓储只负责持久化节点与修订，不提交事务；事务边界由工作单元负责。
查询返回的节点在会话内可以继续读取其修订历史。
'''

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.model import LibNode
from .orm import lib_nodes


class LibraryRepository(Protocol):
    def get_node(self, node_id: str) -> LibNode | None: ...

    def children(self, project_id: str, parent_id: str | None) -> list[LibNode]:
        '''直接子节点，包含已删除的，按创建时间排序。'''
        ...

    def save(self, *nodes: LibNode) -> None:
        '''保存节点并 flush，让唯一约束冲突在服务层可被捕获。'''
        ...


class SqlAlchemyLibraryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_node(self, node_id: str) -> LibNode | None:
        return self._session.get(LibNode, node_id)

    def children(self, project_id: str, parent_id: str | None) -> list[LibNode]:
        stmt = (
            select(LibNode)
            .where(
                lib_nodes.c.project_id == project_id,
                lib_nodes.c.parent_id == parent_id,
            )
            .order_by(lib_nodes.c.created_at, lib_nodes.c.node_id)
        )
        return list(self._session.scalars(stmt))

    def save(self, *nodes: LibNode) -> None:
        self._session.add_all(list(nodes))
        self._session.flush()

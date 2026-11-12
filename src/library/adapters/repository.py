'''
用例库的仓储
通过proj_id注入Project依赖
'''

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.model import LibNode, NodeError, ProjectVersion
from .orm import lib_nodes


class LibraryRepository(Protocol):
    @property
    def proj_id(self) -> str: ...

    def get_node(self, node_id: str) -> LibNode | None:
        '''其他项目的节点视为不存在。'''
        ...

    def children(self, parent_id: str | None) -> list[LibNode]:
        '''直接子节点，包含已删除的，按创建时间排序；parent_id 为 None 表示根下。'''
        ...

    def has_doc_version(self, version_no: str) -> bool:
        '''本项目是否有这个上游文档版本。'''
        ...

    def save(self, *nodes: LibNode) -> None:
        '''保存节点，节点必须属于本项目。事务的提交与回滚由调用方负责。'''
        ...


class SqlAlchemyLibraryRepository:
    def __init__(self, session: Session, proj_id: str) -> None:
        self._session = session
        self._proj_id = proj_id

    @property
    def proj_id(self) -> str:
        return self._proj_id

    def get_node(self, node_id: str) -> LibNode | None:
        node = self._session.get(LibNode, node_id)
        if node is None or node.proj_id != self._proj_id:
            return None
        return node

    def children(self, parent_id: str | None) -> list[LibNode]:
        # 经典映射下类属性不是 SQL 列，查询条件要用表的列。
        cols = lib_nodes.c
        stmt = (select(LibNode)
                .where(cols.proj_id == self._proj_id,
                       cols.parent_id == parent_id)
                .order_by(cols.created_at))
        return list(self._session.scalars(stmt))

    def has_doc_version(self, version_no: str) -> bool:
        return self._session.get(
            ProjectVersion, (self._proj_id, version_no)) is not None

    def save(self, *nodes: LibNode) -> None:
        for node in nodes:
            if node.proj_id != self._proj_id:
                raise NodeError(
                    f'node {node.node_id} belongs to project {node.proj_id}, '
                    f'not {self._proj_id}')
        self._session.add_all(nodes)
        self._session.flush()

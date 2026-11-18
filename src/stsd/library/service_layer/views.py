'''用例库的读模型。

读接口返回不可变的只读对象，而不是聚合本身（见 decisions/005）。
树节点带上界面直接需要的修订信息，浏览一棵树时不必逐个查询详情。
'''

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from stsd.library.domain.model import RevisionStatus


@dataclass(frozen=True)
class SectionTreeNode:
    node_type: Literal['section']
    node_id: str
    project_id: str
    parent_id: str | None
    name: str
    created_at: datetime


@dataclass(frozen=True)
class TestPointTreeNode:
    node_type: Literal['testpoint']
    node_id: str
    project_id: str
    parent_id: str | None
    name: str
    latest_revision_ver: int
    latest_revision_status: RevisionStatus
    latest_frozen_revision_ver: int | None
    created_at: datetime


TreeNode = SectionTreeNode | TestPointTreeNode


@dataclass(frozen=True)
class TestPointDetail:
    testpoint_id: str
    project_id: str
    revision_ver: int
    name: str
    description: str
    implementation: str | None
    proj_ver: str
    status: RevisionStatus
    testpoint_deleted: bool
    created_at: datetime
    created_by: str

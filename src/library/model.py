'''
Domain model for the library demo.
'''

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


class Actor:
    actor_id: str
    name: str
    type: Literal['user', 'agent']

class Project:
    proj_id: str
    name: str
    versions: list['ProjectVersion']



class ProjectVersion:
    '''
    Project的一个版本
    '''
    proj_id: str
    proj_version: str
    docs: list['ProjectDoc']


class ProjectDoc:
    doc_id: str
    title: str
    content: str


class LibNode:
    node_id: str
    parent_id: str | None
    node_type: Literal['section', 'testpoint']
    is_deleted: bool = False

    created_at: datetime
    updated_at: datetime
    updated_by: Actor                 

    def __init__(self, node_id: str,
                 parent_id: str | None,
                 node_type: Literal['section', 'testpoint'],
                 created_at: datetime,
                 updated_at: datetime,
                 updated_by: Actor,
                 change_note: str):
        self.node_id = node_id
        self.parent_id = parent_id
        self.node_type = node_type
        self.created_at = created_at
        self.updated_by = updated_by
        self.updated_at = updated_at
    @property
    def path(self):
        pass

    def softDelete(self, actor: Actor):
        if(self.is_deleted):
            raise NodeError("Node is already deleted")
        self.is_deleted = True
        self.updated_by = actor

    def move_to(self, new_parent: "LibNode", now: datetime) -> None:
        if self.is_deleted:
            raise NodeError("Cannot move a deleted node:{node_id}".format(node_id=self.node_id))
        if new_parent.node_type != "section":
            raise NodeError("move target must be section")
        if new_parent.node_id == self.node_id:
            raise NodeError("Cannot move node to itself")
        self.parent_id = new_parent.node_id
        self.updated_at = now


class TestCase:
    '''
    测试点的测试用例
    '''
    testpoint_id: int 
    testcase_id: int              
    name: str
    desc: str                        # 该版本的完整测试内容
    impl: TestCaseImpl | NotImplTestCase                        # 测试用例实现


class TestPointVersion:
    testpoint_id: int               
    version_no: str                  # 声明当前的测试点是归属哪一个文档版本，与上游提供的文档版本绑定
    revision_no: str                  # 该测试点的修订版本号，允许在同一个文档版本下多次修订
    name: str
    desc: str                        # 该版本的完整测试内容
    impl_ref: str
    change_note: str
    def getTestCase(self)->TestCase | NotImplTestCase:
        raise NotImplementedError




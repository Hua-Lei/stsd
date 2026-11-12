"""文档模块第一周草稿：定义数据模型与服务接口。"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal


DocumentKind = Literal["requirements", "openapi"]


@dataclass(frozen=True)
class DocSnapshot:
    """某个版本的文档原文。"""

    doc_id: str
    version: int
    kind: DocumentKind
    text: str


@dataclass(frozen=True)
class DocVersionSummary:
    """文档目录和版本历史中的一条记录。"""

    doc_id: str
    version: int
    kind: DocumentKind


class DocumentErrorCode(str, Enum):
    """文档服务对外使用的错误码。"""

    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    DOCUMENT_VERSION_NOT_FOUND = "DOCUMENT_VERSION_NOT_FOUND"


class DocumentError(Exception):
    """服务异常，调用方可分别读取错误码和说明。"""

    def __init__(self, code: DocumentErrorCode, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class Documents:
    """供 API 层和 AI 工作流调用的文档服务接口。

    实现时，参数不合法抛出 DocumentError，错误码为 INVALID_ARGUMENT。
    读取原文时找不到指定版本，错误码为 DOCUMENT_VERSION_NOT_FOUND。
    目录或历史查询没有记录时返回空列表。
    """

    def add_version(self, project_id: str, kind: DocumentKind, text: str) -> DocSnapshot:
        """追加一个新版本，返回该版本的快照。"""
        raise NotImplementedError

    def list_documents(self, project_id: str) -> list[DocVersionSummary]:
        """列出项目内的文档，每份文档返回最新版信息。"""
        raise NotImplementedError

    def list_versions(self, project_id: str, kind: DocumentKind) -> list[DocVersionSummary]:
        """按版本号从新到旧列出历史版本。"""
        raise NotImplementedError

    def get(
        self, project_id: str, kind: DocumentKind, version: int | None = None
    ) -> DocSnapshot:
        """读取指定版本。省略版本号时读取最新版。"""
        raise NotImplementedError

    def get_by_ref(self, project_id: str, doc_id: str, version: int) -> DocSnapshot:
        """按用例库持有的文档 ID 和版本号读取原文。"""
        raise NotImplementedError

    def get_comparison_input(
        self, project_id: str, kind: DocumentKind, from_version: int, to_version: int
    ) -> tuple[DocSnapshot, DocSnapshot]:
        """按旧版、新版的顺序提供两份原文，由 LLM 判断需求变化。"""
        raise NotImplementedError

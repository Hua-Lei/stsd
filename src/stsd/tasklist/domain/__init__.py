"""任务清单的领域层：实体、值对象、领域规则与纯函数。"""

from .hashing import compute_testpoint_content_hash, compute_list_content_hash
from .model import (
    TestPointRef,
    CopyMode,
    Status,
    TaskList,
    TaskListItem,
    normalize_title,
    utc_now,
    validate_project_version,
)
from .versioning import compare_versions, normalize_software_version, version_key

__all__ = [
    "TestPointRef",
    "CopyMode",
    "Status",
    "TaskList",
    "TaskListItem",
    "compare_versions",
    "compute_testpoint_content_hash",
    "compute_list_content_hash",
    "normalize_software_version",
    "normalize_title",
    "utc_now",
    "validate_project_version",
    "version_key",
]

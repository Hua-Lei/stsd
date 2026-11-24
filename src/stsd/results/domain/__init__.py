"""结果模块的领域层。"""

from .model import (
    RunKind,
    RunRecord,
    RunStatus,
    StepResult,
    StepStatus,
    TestPointResult,
    TestPointStatus,
)

__all__ = [
    "TestPointResult",
    "TestPointStatus",
    "RunRecord",
    "RunKind",
    "RunStatus",
    "StepResult",
    "StepStatus",
]

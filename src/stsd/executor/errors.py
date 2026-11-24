"""执行器内部错误：用例没能跑完，但执行器本身仍继续处理其他用例。"""

from __future__ import annotations


class StepError(Exception):
    """步骤运行时错误的基类；error_type 会原样写入 StepResult。"""

    error_type = "executor_error"


class RenderError(StepError):
    """请求模板里引用了不存在的变量。"""

    error_type = "render_error"


class ExtractError(StepError):
    """断言通过后，按 JSONPath 提取变量失败。"""

    error_type = "extract_error"

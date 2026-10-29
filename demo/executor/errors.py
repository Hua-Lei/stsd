"""步骤执行中的运行时错误：用例没能跑完。每个子类对应一种 error_type。

断言不通过不在这里。那是用例跑完后得出的结论，由断言结果算出，不走异常。
"""
from demo.models import ErrorType


class StepError(Exception):
    error_type: ErrorType


class RenderError(StepError):
    error_type = "render_error"


class TransportError(StepError):
    error_type = "transport_error"


class ExtractError(StepError):
    error_type = "extract_error"

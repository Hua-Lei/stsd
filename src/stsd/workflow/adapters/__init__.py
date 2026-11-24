"""执行编排与外部模块的适配器。"""

from .http import HttpExecutorAdapter
from .results import ResultsRecorderAdapter

__all__ = ["HttpExecutorAdapter", "ResultsRecorderAdapter"]

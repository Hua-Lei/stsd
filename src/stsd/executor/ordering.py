'''按环境签名排序执行顺序。

同一个环境签名下连续执行可以复用沙箱；签名变化才重建。排序是稳定的，
同一签名内的修订保持任务清单里的顺序。
'''

from __future__ import annotations

from collections.abc import Sequence

from .ports import PlatformAdapter
from .records import EnvironmentSignature, RevisionInput

EnvironmentGroup = tuple[EnvironmentSignature, list[RevisionInput]]


def group_by_environment(
    inputs: Sequence[RevisionInput], platform: PlatformAdapter
) -> list[EnvironmentGroup]:
    decorated = [
        (platform.environment_signature(item.implementation), index, item)
        for index, item in enumerate(inputs)
    ]
    decorated.sort(key=lambda entry: (entry[0].sort_key(), entry[1]))

    groups: list[EnvironmentGroup] = []
    for signature, _, item in decorated:
        if not groups or groups[-1][0] != signature:
            groups.append((signature, []))
        groups[-1][1].append(item)
    return groups

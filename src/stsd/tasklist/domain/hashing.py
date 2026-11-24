"""内容指纹：纯函数，属于领域层。

清单 content_hash 覆盖“项目版本 + 有序的
``(testpoint_id, revision_ver, content_hash)`` 集合”。
两条重要约定：

1. 元数据（title）、状态、rev、pinned 不进入指纹；
2. 顺序进入指纹——清单顺序就是执行顺序，重排即是另一份清单。

规范化使用 ``json.dumps(sort_keys=True, separators=(",", ":"))``，
保证同样的内容永远得到同样的摘要。这里不 import 任何实体类型，
只接收条目序列，避免与 ``domain/model.py`` 形成循环依赖。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence


def compute_list_content_hash(
    project_version: str,
    items: Iterable[Sequence[object]],
) -> str:
    """items 的每一项按 ``(testpoint_id, revision_ver, content_hash)`` 传入。

    返回形如 ``sha256:<hex>`` 的字符串，便于直接展示与跨模块传阅。
    """

    payload = {
        "project_version": project_version,
        "items": [
            [str(item[0]), int(item[1]), str(item[2])]  # type: ignore[index]
            for item in items
        ],
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_testpoint_content_hash(payload: object) -> str:
    """对测试点实现正文算稳定指纹。

    正文格式暂不约定，可以是不透明字符串，也可以是 dict；只要求
    TaskList 每次用同一套规范化方式计算。
    """

    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

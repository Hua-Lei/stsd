"""清单指纹与规范化。

清单 content_hash 覆盖“目标软件版本 + 有序的 (use_case_id, use_case_version,
content_hash) 集合”（design_1.md 第二节）。两条重要约定：

1. 元数据（title）、状态、rev 不进入指纹；
2. 顺序进入指纹——清单顺序就是执行顺序，重排即是另一份清单。

规范化使用 ``json.dumps(sort_keys=True, separators=(",", ":"))``，
保证同样的内容永远得到同样的摘要。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence


def compute_list_content_hash(
    target_software_release_version: int,
    items: Iterable[Sequence[object]],
) -> str:
    """items 的每一项按 ``(use_case_id, use_case_version, content_hash)`` 传入。

    返回形如 ``sha256:<hex>`` 的字符串，便于直接展示与跨模块传阅。
    """

    payload = {
        "target_software_release_version": target_software_release_version,
        "items": [
            [str(item[0]), int(item[1]), str(item[2])]  # type: ignore[index]
            for item in items
        ],
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_case_content_hash(payload: object) -> str:
    """适配器用：对一份用例 JSON（TestCase 形状的 dict）算稳定指纹。"""

    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

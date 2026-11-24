"""软件版本字符串的规范化与比较。

版本对外保存为 ``v0.1``、``v0.9``、``v0.10`` 这样的字符串；
比较时按数字段解析，避免字典序把 ``v0.10`` 排在 ``v0.9`` 前面。
"""

from __future__ import annotations

import re

_PATTERN = re.compile(r"^[vV]?(\d+(?:\.\d+)*)$")


def version_key(value: str) -> tuple[int, ...]:
    """把版本字符串转成可比较的数字元组；非法格式抛 ValueError。

    末尾的 0 会被忽略，因此 ``v1``、``v1.0``、``v1.0.0`` 视为同一版本。
    """

    if not isinstance(value, str):
        raise ValueError("版本必须是字符串")
    match = _PATTERN.fullmatch(value.strip())
    if match is None:
        raise ValueError(f"版本格式应为 v0.1 或 0.1，得到 {value!r}")
    parts = [int(part) for part in match.group(1).split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def normalize_software_version(value: object) -> str:
    """校验并规范化为 ``v`` + 数字段。

    - ``0.1`` -> ``v0.1``
    - ``1`` / ``v1`` -> ``v1.0``
    - ``v1.0.0`` 保留三段
    """

    if isinstance(value, bool):
        raise ValueError("版本必须是字符串或整数")
    if isinstance(value, int):
        value = str(value)
    if not isinstance(value, str):
        raise ValueError("版本必须是字符串或整数")
    match = _PATTERN.fullmatch(value.strip())
    if match is None:
        raise ValueError(f"版本格式应为 v0.1 或 0.1，得到 {value!r}")
    parts = [int(part) for part in match.group(1).split(".")]
    if len(parts) == 1:
        parts.append(0)
    return "v" + ".".join(str(part) for part in parts)


def compare_versions(left: str, right: str) -> int:
    """返回 -1 / 0 / 1；用于排序和 max。"""

    left_key = version_key(left)
    right_key = version_key(right)
    return (left_key > right_key) - (left_key < right_key)

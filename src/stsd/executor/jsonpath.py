"""极简 JSONPath：只支持 $、.key、[index]。"""

from __future__ import annotations

import re

MISSING = object()

_TOKEN = re.compile(r"\.([A-Za-z_][\w-]*)|\[(\d+)\]")


def parse(path: str) -> list[str | int]:
    """把 ``$.a[0].b`` 拆成 ``["a", 0, "b"]``；语法错误直接抛 ValueError。"""

    if not path.startswith("$"):
        raise ValueError(f"JSONPath 必须以 $ 开头: {path!r}")
    rest = path[1:]
    tokens: list[str | int] = []
    pos = 0
    while pos < len(rest):
        match = _TOKEN.match(rest, pos)
        if not match:
            raise ValueError(f"无法解析的 JSONPath: {path!r}（位置 {pos + 1}）")
        key, index = match.groups()
        tokens.append(key if key is not None else int(index))
        pos = match.end()
    return tokens


def get(data, path: str):
    """按 path 取值；字段/索引不存在返回 ``MISSING``，与 JSON null 区分。"""

    current = data
    for token in parse(path):
        if isinstance(token, str):
            if not isinstance(current, dict) or token not in current:
                return MISSING
            current = current[token]
        else:
            if not isinstance(current, list) or token >= len(current):
                return MISSING
            current = current[token]
    return current

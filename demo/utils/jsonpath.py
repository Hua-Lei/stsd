"""极简 JSONPath 取值：只支持 $、.key、[index]，例如 $.learner.id、$.items[0].name。

路径不存在时返回 MISSING（而不是 None），因为 JSON 里的 null 本身就是合法值，
需要和“字段不存在”区分开。
"""
import re

MISSING = object()

_TOKEN = re.compile(r"\.([A-Za-z_][\w-]*)|\[(\d+)\]")


def parse(path: str) -> list[str | int]:
    """把路径拆成 key / index 列表；语法不合法时抛 ValueError。"""
    if not path.startswith("$"):
        raise ValueError(f"JSONPath 必须以 $ 开头: {path!r}")
    rest = path[1:]
    tokens: list[str | int] = []
    pos = 0
    while pos < len(rest):
        m = _TOKEN.match(rest, pos)
        if not m:
            raise ValueError(f"无法解析的 JSONPath: {path!r}（位置 {pos + 1}）")
        key, index = m.groups()
        tokens.append(key if key is not None else int(index))
        pos = m.end()
    return tokens


def get(data, path: str):
    cur = data
    for token in parse(path):
        if isinstance(token, str):
            if not isinstance(cur, dict) or token not in cur:
                return MISSING
            cur = cur[token]
        else:
            if not isinstance(cur, list) or token >= len(cur):
                return MISSING
            cur = cur[token]    
    return cur

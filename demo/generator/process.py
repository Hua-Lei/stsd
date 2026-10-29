from pathlib import Path
import copy
import json
from typing import Literal
import httpx
import re
from models import TestCase

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

def load_spec(source: str) -> dict:
    if source.startswith(("http://", "https://")):
        resp = httpx.get(source, timeout=15)
        resp.raise_for_status()
        return resp.json()
    return json.loads(Path(source).read_text(encoding="utf-8"))


def filter_spec(spec: dict, exclude_ext: list[str]) -> tuple[dict, list[str]]:
    """去掉执行器跑不了的接口（响应非 JSON）和带指定扩展标记的接口。返回 (新文档, 被排除的接口)。"""
    spec = copy.deepcopy(spec)
    excluded = []
    for path, ops in list(spec["paths"].items()):
        for method in [m for m in ops if m in HTTP_METHODS]:
            op = ops[method]
            types = {t for r in op.get("responses", {}).values() for t in r.get("content", {})}
            reason = None
            if types - {"application/json"}:
                reason = f"响应类型 {', '.join(sorted(types - {'application/json'}))}"
            elif hit := [e for e in exclude_ext if op.get(e)]:
                reason = f"带 {', '.join(hit)}"
            if reason:
                excluded.append(f"{method.upper()} {path}（{reason}）")
                del ops[method]
        if not any(m in HTTP_METHODS for m in ops):
            del spec["paths"][path]
    return spec, excluded

def load_routes(spec: dict) -> list[tuple[str, re.Pattern]]:
    routes = []
    for path, ops in spec["paths"].items():
        pattern = re.compile("^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(path)) + "$")
        routes += [(method.upper(), pattern) for method in ops if method in HTTP_METHODS]
    return routes


def endpoint_ids(spec: dict) -> set[str]:
    return {f"{m.upper()} {p}" for p, ops in spec["paths"].items() for m in ops if m in HTTP_METHODS}


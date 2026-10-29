from models import TestCase
import re

def static_warnings(case: TestCase, valid_ids: set[str], routes) -> list[str]:
    warnings = [f"关联编号不存在: {r}" for r in case.requirement_ids if r not in valid_ids]
    for i, step in enumerate(case.steps, 1):
        # 先把 {{var}} 换成占位值，再和文档中的路由比对
        path = re.sub(r"\{\{\s*\w+\s*\}\}", "x", step.request.path.split("?")[0])
        if not any(m == step.request.method and p.match(path) for m, p in routes):
            warnings.append(f"第 {i} 步 {step.request.method} {step.request.path} 不在接口文档中")
    return warnings

import argparse
import json
import sys
from pathlib import Path

import httpx
from pydantic import ValidationError

from demo.executor import CaseExecutor
from demo.models import CaseResult, TestCase

ICON = {"passed": "PASS", "failed": "FAIL", "error": "ERR ", "skipped": "SKIP"}


def print_report(r: CaseResult) -> None:
    print(f"[{ICON[r.status]}] {r.case_id}  {r.title}")
    for s in r.steps:
        line = f"    {s.index}. [{ICON[s.status]}] {s.name}"
        if s.request:
            line += f"  {s.request.method} {s.request.path}"
        if s.response:
            line += f" -> {s.response.status} ({s.response.elapsed_ms}ms)"
        print(line)
        if s.message:
            print(f"         {s.error_type}: {s.message}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m demo.executor", description="运行测试用例 JSON")
    parser.add_argument("cases", nargs="+", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--json-out", type=Path, help="把完整结果写成 JSON，供后续分析")
    parser.add_argument("--timeout", type=float, default=10, help="单个请求的超时（秒）")
    args = parser.parse_args()

    results: list[CaseResult] = []
    bad_files = 0
    with httpx.Client(base_url=args.base_url, timeout=args.timeout) as client:
        executor = CaseExecutor(client)
        for path in args.cases:
            try:
                case = TestCase.model_validate_json(path.read_text(encoding="utf-8"))
            except ValidationError as e:
                bad_files += 1
                print(f"[ERR ] {path}: 用例格式不合法\n{e}\n")
                continue
            result = executor.run_case(case)
            print_report(result)
            results.append(result)

    if args.json_out:
        args.json_out.write_text(
            json.dumps([r.model_dump() for r in results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    counts = {k: sum(r.status == k for r in results) for k in ("passed", "failed", "error")}
    print(f"共 {len(results) + bad_files} 条: {counts['passed']} 通过, {counts['failed']} 失败, "
          f"{counts['error']} 出错, {bad_files} 格式不合法")
    return 0 if counts["passed"] == len(results) and not bad_files else 1


if __name__ == "__main__":
    sys.exit(main())

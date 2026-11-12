import json
import re
from pathlib import Path

_SAFE = re.compile(r"[^\w.-]+", re.UNICODE)


def export_case_files(service, tasklist_id, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, payload in enumerate(service.export_cases(tasklist_id), 1):
        name = _SAFE.sub("_", str(payload.get("id", "case")))
        path = out / f"{index:03d}_{name}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths.append(path)
    return paths

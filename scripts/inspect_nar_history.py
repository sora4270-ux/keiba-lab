#!/usr/bin/env python3
"""Print non-sensitive NAR history diagnostics; never rewrite predictions."""
import json
from pathlib import Path

PATH = Path("data/auto/nar_predictions.json")


def inspect(path=PATH):
    if not path.exists():
        return {"status": "missing", "bytes": 0, "frozen_count": None}
    size = path.stat().st_size
    if size == 0:
        return {"status": "empty", "bytes": size, "frozen_count": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError):
        return {"status": "invalid_json", "bytes": size, "frozen_count": None}
    if not isinstance(data, dict) or not isinstance(data.get("races"), list):
        return {"status": "invalid_schema", "bytes": size, "frozen_count": None}
    return {"status": "valid", "bytes": size, "frozen_count": len(data["races"]),
            "draft_count": len(data.get("drafts", [])) if isinstance(data.get("drafts", []), list) else None}


if __name__ == "__main__":
    print(json.dumps(inspect(), ensure_ascii=False))

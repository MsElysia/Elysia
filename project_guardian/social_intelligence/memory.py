# Append-only JSONL artifacts for thread / profile / draft packs (bounded).

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOCIAL_DATA_DIR = PROJECT_ROOT / "data" / "social_intelligence"


def ensure_social_data_dir() -> Path:
    SOCIAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return SOCIAL_DATA_DIR


def _trim_jsonl(path: Path, max_lines: int) -> None:
    if max_lines <= 0 or not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= max_lines:
        return
    keep = lines[-max_lines:]
    path.write_text("\n".join(keep) + "\n", encoding="utf-8")


def append_jsonl(name: str, record: Dict[str, Any], *, max_lines: int) -> Path:
    d = ensure_social_data_dir()
    path = d / name
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    _trim_jsonl(path, max_lines)
    return path


def read_tail_jsonl(name: str, max_lines: int = 100) -> List[Dict[str, Any]]:
    path = SOCIAL_DATA_DIR / name
    if not path.exists() or max_lines <= 0:
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    lines = lines[-max_lines:]
    out: List[Dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out

#!/usr/bin/env python3
"""
Import ChatGPT export zip into Elysia personal memory.

ChatGPT exports contain conversations-*.json files. This script:
1. Extracts the zip (or uses an already-extracted folder)
2. Parses each conversation JSON
3. Extracts user + assistant messages
4. Saves as text files to F:\\ProjectGuardian\\memory\\personal\\chatlogs\\
   (or fallback to project local path if F: unavailable)

Usage:
  python scripts/import_chatgpt_export.py path/to/export.zip
  python scripts/import_chatgpt_export.py path/to/extracted_folder
  python scripts/import_chatgpt_export.py path/to/export.zip --limit 5   # first 5 convos only
"""

import json
import os
import sys
import re
import zipfile
import shutil
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
MEMORY_BASE = Path("F:/ProjectGuardian/memory")
PERSONAL = MEMORY_BASE / "personal"
CHATLOGS = PERSONAL / "chatlogs"


def _resolve_chatlogs_dir() -> Path:
    """Use F: if available, else fallback drives, else local."""
    if MEMORY_BASE.exists() or MEMORY_BASE.parent.exists():
        CHATLOGS.mkdir(parents=True, exist_ok=True)
        return CHATLOGS
    for d in ["G:/", "E:/", "D:/"]:
        alt = Path(d) / "ProjectGuardian" / "memory" / "personal" / "chatlogs"
        if Path(d).exists():
            alt.mkdir(parents=True, exist_ok=True)
            return alt
    local = PROJECT_ROOT / "memory" / "personal" / "chatlogs"
    local.mkdir(parents=True, exist_ok=True)
    return local


def extract_messages_from_conversation(conv: dict):
    """
    Extract (role, text, create_time) from a ChatGPT conversation.
    Returns list of (role, text, timestamp) for user and assistant only.
    """
    out = []
    mapping = conv.get("mapping", {})
    for node_id, node in mapping.items():
        msg = node.get("message")
        if not msg:
            continue
        author = msg.get("author") or {}
        role = (author.get("role") or "").lower()
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content") or {}
        parts = content.get("parts") or []
        text = " ".join(str(p) for p in parts if p).strip()
        if not text:
            continue
        create_time = msg.get("create_time") or 0
        out.append((role, text, create_time))
    out.sort(key=lambda x: x[2])
    return out


def conv_to_text(messages, title: str = "") -> str:
    """Format messages as readable text."""
    lines = []
    if title:
        lines.append(f"# {title}\n")
    for role, text, _ in messages:
        prefix = "User:" if role == "user" else "Assistant:"
        lines.append(f"{prefix}\n{text}\n")
    return "\n".join(lines)


def process_conversation_file(path: Path, out_dir: Path, index: int, limit) -> int:
    """Process one conversations-*.json file. Returns count of conversations saved."""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        print(f"  [SKIP] {path.name}: invalid JSON - {e}")
        return 0
    if not isinstance(data, list):
        data = [data]
    saved = 0
    for i, conv in enumerate(data):
        if limit is not None and saved >= limit:
            break
        msg_list = extract_messages_from_conversation(conv)
        if not msg_list:
            continue
        conv_id = conv.get("id", conv.get("conversation_id", f"conv-{index}-{i}"))
        if isinstance(conv_id, str) and len(conv_id) > 32:
            conv_id = conv_id[:8]
        title = f"ChatGPT export {index:03d}-{i:02d} ({conv_id})"
        text = conv_to_text(msg_list, title)
        safe_name = re.sub(r"[^\w\-]", "_", str(conv_id))[:50]
        out_name = f"chatgpt_{index:03d}_{i:02d}_{safe_name}.txt"
        out_path = out_dir / out_name
        out_path.write_text(text, encoding="utf-8")
        print(f"  [OK] {out_name} ({len(msg_list)} messages)")
        saved += 1
    return saved


def run(src: Path, out_dir: Path, limit=None) -> int:
    """Process source (zip or folder). Returns total conversations saved."""
    if src.is_file() and src.suffix.lower() == ".zip":
        extract_dir = src.parent / f"_extract_{src.stem}"
        try:
            with zipfile.ZipFile(src, "r") as zf:
                zf.extractall(extract_dir)
            conv_files = sorted(extract_dir.glob("conversations-*.json"))
        except Exception as e:
            print(f"[ERROR] Failed to extract zip: {e}")
            return 0
        finally:
            if extract_dir.exists() and limit is None:
                pass  # keep for debugging if needed
    else:
        conv_files = sorted(Path(src).glob("conversations-*.json"))
    if not conv_files:
        print("[WARN] No conversations-*.json files found")
        return 0
    total = 0
    for idx, cf in enumerate(conv_files):
        n = process_conversation_file(cf, out_dir, idx, limit)
        total += n
        if limit is not None:
            limit -= n
            if limit <= 0:
                break
    return total


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Import ChatGPT export zip into Elysia personal memory")
    parser.add_argument("source", type=Path, help="Path to .zip or extracted folder")
    parser.add_argument("--limit", type=int, default=None, help="Max conversations to import")
    parser.add_argument("--out", type=Path, default=None, help="Output directory (default: personal/chatlogs)")
    args = parser.parse_args()
    src = args.source.resolve()
    if not src.exists():
        print(f"[ERROR] Source not found: {src}")
        return 1
    out_dir = args.out or _resolve_chatlogs_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Importing from: {src}")
    print(f"Output: {out_dir}\n")
    total = run(src, out_dir, args.limit)
    print(f"\nDone. Saved {total} conversation(s) to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

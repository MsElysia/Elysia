#!/usr/bin/env python3
"""Read-only diagnostic for control-panel conversation memory (canonical + legacy).

Does not delete legacy files, mutate legacy JSON, or call LLMs.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project_guardian.conversation_store import (  # noqa: E402
    DEFAULT_CONVERSATIONS_DIR,
    count_canonical_conversation_files,
    describe_legacy_control_panel_chat,
    is_legacy_control_panel_imported,
    legacy_import_marker_path,
)
from project_guardian.ui_control_panel import CONTROL_PANEL_CHAT_HISTORY_PATH  # noqa: E402


def main() -> int:
    base = Path(DEFAULT_CONVERSATIONS_DIR)
    legacy = Path(CONTROL_PANEL_CHAT_HISTORY_PATH)
    marker = legacy_import_marker_path(base)
    legacy_info = describe_legacy_control_panel_chat(legacy)
    canonical_count = count_canonical_conversation_files(base)
    imported = is_legacy_control_panel_imported(base)

    print("Control panel conversation memory (read-only)")
    print(f"  Canonical dir: {base}")
    print(f"  Canonical conversation files (*.jsonl): {canonical_count}")
    print(f"  Legacy path: {legacy}")
    print(f"  Legacy file exists: {legacy_info.get('legacy_exists')}")
    if legacy_info.get("legacy_exists"):
        print(f"  Legacy sessions: {legacy_info.get('session_count')}")
        print(f"  Legacy messages (approx): {legacy_info.get('message_count')}")
    if legacy_info.get("read_error"):
        print(f"  Legacy read error: {legacy_info.get('read_error')}")
    print(f"  Import marker: {marker}")
    print(f"  Legacy import completed: {imported}")
    print()
    if imported:
        print(
            "Recommendation: ConversationStore is source of truth. "
            "After verifying JSONL history in the canonical dir, you may manually archive "
            f"{legacy} (not deleted automatically)."
        )
    elif legacy_info.get("legacy_exists"):
        print(
            "Recommendation: Open the control panel or call GET /api/chat/history once "
            "to run the one-time legacy import into canonical JSONL."
        )
    else:
        print("Recommendation: No legacy file; canonical ConversationStore only.")
    print()
    print("This script does not modify chat files or execute commands.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Tests for ChatGPT export → Elysia chatlogs import."""

from pathlib import Path

import pytest

from project_guardian.chatgpt_export_import import (
    extract_messages_ordered,
    import_chatgpt_export,
    import_conversations_to_chatlogs,
    iter_conversations_from_zip,
)


def _minimal_conv_linear() -> dict:
    """Three-node chain: system (skipped) -> user -> assistant."""
    return {
        "title": "Test thread",
        "conversation_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "current_node": "n2",
        "mapping": {
            "n0": {"id": "n0", "parent": None, "children": ["n1"], "message": None},
            "n1": {
                "id": "n1",
                "parent": "n0",
                "children": ["n2"],
                "message": {
                    "author": {"role": "user"},
                    "content": {"parts": ["Hello"]},
                    "create_time": 100.0,
                },
            },
            "n2": {
                "id": "n2",
                "parent": "n1",
                "children": [],
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"parts": ["Hi there"]},
                    "create_time": 101.0,
                },
            },
        },
    }


def test_extract_messages_ordered_follows_parent_chain():
    conv = _minimal_conv_linear()
    msgs = extract_messages_ordered(conv)
    assert [(m[0], m[1]) for m in msgs] == [("user", "Hello"), ("assistant", "Hi there")]


def test_extract_messages_branch_prefers_current_path():
    """Branched mapping: only nodes on path from current_node appear, in order."""
    conv = {
        "title": "Branch",
        "conversation_id": "branch-id-1111-2222-333333333333",
        "current_node": "b_user",
        "mapping": {
            "root": {"id": "root", "parent": None, "children": ["a_user"], "message": None},
            "a_user": {
                "id": "a_user",
                "parent": "root",
                "children": ["a_asst"],
                "message": {
                    "author": {"role": "user"},
                    "content": {"parts": ["Path A"]},
                    "create_time": 1.0,
                },
            },
            "a_asst": {
                "id": "a_asst",
                "parent": "a_user",
                "children": ["b_user"],
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"parts": ["Reply A"]},
                    "create_time": 2.0,
                },
            },
            "b_user": {
                "id": "b_user",
                "parent": "a_asst",
                "children": [],
                "message": {
                    "author": {"role": "user"},
                    "content": {"parts": ["Path B continue"]},
                    "create_time": 3.0,
                },
            },
        },
    }
    msgs = extract_messages_ordered(conv)
    roles_text = [(m[0], m[1]) for m in msgs]
    assert roles_text == [
        ("user", "Path A"),
        ("assistant", "Reply A"),
        ("user", "Path B continue"),
    ]


def test_import_conversations_stable_filename(tmp_path: Path):
    out = tmp_path / "chatlogs"
    stats = import_conversations_to_chatlogs(
        [_minimal_conv_linear()],
        out,
        dry_run=False,
        skip_existing=True,
        force=False,
    )
    assert stats.written == 1
    files = list(out.glob("*.md"))
    assert len(files) == 1
    assert files[0].name == "elysia_chatgpt_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.md"
    text = files[0].read_text(encoding="utf-8")
    assert "Test thread" in text
    assert "## User" in text and "Hello" in text
    assert "## Assistant" in text and "Hi there" in text

    stats2 = import_conversations_to_chatlogs(
        [_minimal_conv_linear()],
        out,
        dry_run=False,
        skip_existing=True,
        force=False,
    )
    assert stats2.written == 0
    assert stats2.skipped_existing == 1


def test_iter_conversations_from_zip_roundtrip(tmp_path: Path):
    import json
    import zipfile

    conv = _minimal_conv_linear()
    zpath = tmp_path / "export.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("conversations-000.json", json.dumps([conv]))
    convs = list(iter_conversations_from_zip(zpath))
    assert len(convs) == 1
    assert convs[0]["conversation_id"] == conv["conversation_id"]


def test_import_chatgpt_export_zip(tmp_path: Path):
    import json
    import zipfile

    conv = _minimal_conv_linear()
    zpath = tmp_path / "export.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("conversations-000.json", json.dumps([conv]))
    out = tmp_path / "out"
    stats = import_chatgpt_export(zpath, out)
    assert stats.written == 1
    assert stats.errors == 0

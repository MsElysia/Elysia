from pathlib import Path

from elysia_collective_seed.legacy_consolidation_inventory import build_report


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_exact_duplicate(tmp_path: Path):
    cur = tmp_path / "cur"
    old = tmp_path / "old"
    _write(cur / "a.py", "def x():\n    return 1\n")
    _write(old / "renamed.py", "def x():\n    return 1\n")
    report = build_report(cur, [old])
    match = report["matches"][0]
    assert match["classification"] == "EXACT_DUPLICATE"
    assert "a.py" in match["canonical_candidates"]


def test_same_path_different_content(tmp_path: Path):
    cur = tmp_path / "cur"
    old = tmp_path / "old"
    _write(cur / "module.py", "def x():\n    return 2\n")
    _write(old / "module.py", "def x():\n    return 1\n")
    report = build_report(cur, [old])
    match = report["matches"][0]
    assert match["classification"] == "SAME_PATH_DIFFERENT_CONTENT"
    assert match["canonical_candidates"] == ["module.py"]


def test_symbol_overlap(tmp_path: Path):
    cur = tmp_path / "cur"
    old = tmp_path / "old"
    _write(cur / "new_name.py", "class DreamEngine:\n    pass\ndef reflect():\n    return 2\n")
    _write(old / "ancient.py", "class DreamEngine:\n    pass\ndef reflect():\n    return 1\n")
    report = build_report(cur, [old])
    match = report["matches"][0]
    assert match["classification"] == "SYMBOL_OVERLAP"
    assert "new_name.py" in match["canonical_candidates"]


def test_unique_legacy_and_genesis_tag(tmp_path: Path):
    cur = tmp_path / "cur"
    old = tmp_path / "old"
    _write(cur / "live.py", "def live():\n    return True\n")
    _write(old / "AI_Constitution_notes.md", "historical source")
    report = build_report(cur, [old])
    match = report["matches"][0]
    assert match["classification"] == "UNIQUE_LEGACY"
    legacy = report["legacy_inventory"][0]
    assert "GENESIS_CANDIDATE" in legacy["tags"]


def test_private_material_is_flagged(tmp_path: Path):
    cur = tmp_path / "cur"
    old = tmp_path / "old"
    _write(cur / "live.py", "def live():\n    return True\n")
    _write(old / "personal" / "chatlogs" / "history.txt", "private")
    report = build_report(cur, [old])
    legacy = report["legacy_inventory"][0]
    assert "SENSITIVE_OR_PRIVATE_REVIEW" in legacy["tags"]

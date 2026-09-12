from pathlib import Path

from elysia_collective_seed.implementation_readiness_scanner import scan_source


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_flags_placeholder_stub(tmp_path: Path):
    path = tmp_path / "stub.py"
    _write(
        path,
        "def run():\n    # TODO: implement real adapter\n    pass\n# placeholder\n",
    )
    rec = scan_source(path, tmp_path)
    assert rec.readiness in {"LIKELY_STUB", "REVIEW"}
    assert "todo_markers" in rec.reasons
    assert "placeholder_markers" in rec.reasons


def test_flags_not_implemented(tmp_path: Path):
    path = tmp_path / "abstractish.py"
    _write(path, "def run():\n    raise NotImplementedError\n")
    rec = scan_source(path, tmp_path)
    assert rec.readiness == "PARTIAL_OR_ABSTRACT"
    assert rec.not_implemented_count == 1


def test_clean_module_is_candidate(tmp_path: Path):
    path = tmp_path / "live.py"
    _write(path, "def add(a, b):\n    return a + b\n")
    rec = scan_source(path, tmp_path)
    assert rec.readiness == "IMPLEMENTATION_CANDIDATE"
    assert not rec.reasons


def test_legacy_path_is_non_runtime_candidate(tmp_path: Path):
    path = tmp_path / "old modules" / "legacy.py"
    _write(path, "def run():\n    return True\n")
    rec = scan_source(path, tmp_path)
    assert rec.readiness == "NON_RUNTIME_CANDIDATE"

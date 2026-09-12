from pathlib import Path

from elysia_collective_seed.boot_path_analyzer import analyze, classify_path


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_classify_path():
    assert classify_path("project_guardian/core.py") == "CANDIDATE"
    assert classify_path("tests/test_core.py") == "TEST"
    assert classify_path("old modules/core.py") == "LEGACY"
    assert classify_path("proposals/x/idea.py") == "PROPOSAL"
    assert classify_path("backup/core.py") == "BACKUP"


def test_reachability_without_execution(tmp_path: Path):
    _write(tmp_path / "project_guardian" / "__init__.py", "")
    _write(
        tmp_path / "project_guardian" / "__main__.py",
        "from project_guardian import live\n",
    )
    _write(
        tmp_path / "project_guardian" / "live.py",
        "from project_guardian import helper\nVALUE = 1\n",
    )
    _write(tmp_path / "project_guardian" / "helper.py", "VALUE = 2\n")
    _write(tmp_path / "project_guardian" / "orphan.py", "VALUE = 3\n")

    result = analyze(tmp_path, ["project_guardian/__main__.py"])
    by_path = {row["path"]: row for row in result["modules"]}

    assert result["executes_code"] is False
    assert by_path["project_guardian/__main__.py"]["reachable"] is True
    assert by_path["project_guardian/live.py"]["reachable"] is True
    assert by_path["project_guardian/helper.py"]["reachable"] is True
    assert by_path["project_guardian/orphan.py"]["reachable"] is False
    assert by_path["project_guardian/orphan.py"]["status"] == "ORPHAN_CANDIDATE"


def test_parse_error_is_reported_not_executed(tmp_path: Path):
    _write(tmp_path / "startup.py", "import bad\n")
    _write(tmp_path / "bad.py", "this is not valid python !!!")

    result = analyze(tmp_path, ["startup.py"])
    by_path = {row["path"]: row for row in result["modules"]}

    assert by_path["bad.py"]["parse_error"] is not None

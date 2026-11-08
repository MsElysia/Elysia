"""Synthetic, no-install regressions for the Windows promotion safety preflight.

These tests never use the operator's Dev/Release/operational/backup paths.
The original script accepted a clean, wrong Dev tip without an external pin
and allowed --skip-tests/--allow-dirty-dev. This test-first file requires
the existing promotable entrypoint to refuse those paths before any writes.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.windows_sync import gitutil
from tools.windows_sync import promote_release as promotion

GOOD = "a" * 40
WRONG = "b" * 40


@pytest.fixture
def synthetic(monkeypatch, tmp_path):
    dev, release = tmp_path / "dev", tmp_path / "release"
    dev.mkdir()
    (release / "pilot").mkdir(parents=True)
    (release / "pilot" / "START_ELYSIA1.bat").write_text(
        "@echo off\nrem synthetic only\n", encoding="utf-8"
    )
    (tmp_path / "state").mkdir()
    for name in ("ops", "pilot", "pilot-data", "backups"):
        (tmp_path / name).mkdir()
    monkeypatch.setenv("ELYSIA_RELEASE_ROOT", str(release))
    monkeypatch.setattr(promotion, "DEFAULT_RELEASE_ROOT", release, raising=False)
    monkeypatch.setattr(promotion, "DEFAULT_STATE_ROOT", tmp_path / "state", raising=False)
    monkeypatch.setattr(promotion, "DEFAULT_RELEASE_BACKUP_ROOT", tmp_path / "backups", raising=False)
    monkeypatch.setattr(promotion, "OPERATIONAL_DATA_ROOT", tmp_path / "ops")
    monkeypatch.setattr(promotion, "PRESERVED_PILOT_ROOT", tmp_path / "pilot")
    monkeypatch.setattr(promotion, "PRESERVED_PILOT_DATA", tmp_path / "pilot-data")
    monkeypatch.setattr(promotion, "dev_root", lambda: dev)
    monkeypatch.setattr(promotion, "release_root", lambda: release)
    monkeypatch.setattr(promotion, "state_root", lambda: tmp_path / "state")

    state = {
        "head": GOOD,
        "branch": "integration/windows-canonical",
        "dirty": False,
        "tracking": GOOD,
        "live": GOOD,
        "remote_url": "https://github.com/MsElysia/Elysia.git",
        "missing_launcher": None,
        "remote_error": False,
    }
    commands = []

    def fake_git(repo, *args):
        assert repo == dev
        args = tuple(args)
        commands.append(args)
        if args[:2] == ("rev-parse", "--verify"):
            return state["head"] if args[-1] == "HEAD" else state["tracking"]
        if args[:3] == ("symbolic-ref", "--quiet", "--short"):
            if state["branch"] is None:
                raise gitutil.GitError("synthetic detached HEAD")
            return state["branch"]
        if args[:2] == ("status", "--porcelain=v1"):
            return " M tests/dummy.py\0" if state["dirty"] else ""
        if args[:2] == ("remote", "get-url"):
            return state["remote_url"]
        if args[:2] == ("ls-remote", "--exit-code"):
            if state["remote_error"]:
                raise gitutil.GitError("synthetic offline remote")
            return state["live"] + "\trefs/heads/integration/windows-canonical"
        if args[:2] == ("ls-tree", "--full-tree"):
            path = args[-1]
            return "" if path == state["missing_launcher"] else (
                "100644 blob " + "c" * 40 + "\t" + path
            )
        raise AssertionError("unexpected git preflight command " + repr(args))

    monkeypatch.setattr(promotion, "_git_preflight", fake_git, raising=False)
    # Baseline original WorktreeState mock: old code promotes a wrong, clean SHA.
    monkeypatch.setattr(
        gitutil, "worktree_state",
        lambda _repo: gitutil.WorktreeState(
            head=state["head"], branch=state["branch"], dirty=state["dirty"],
            staged=False, unstaged=state["dirty"], untracked=False, porcelain="",
        ),
    )
    monkeypatch.setattr(gitutil, "rev_parse", lambda *_: GOOD)

    calls = []
    def marker(name, output=None):
        def invoke(*args, **kwargs):
            calls.append(name)
            return output
        return invoke

    monkeypatch.setattr(promotion, "scan_repo_changed", marker("scan", []))
    monkeypatch.setattr(promotion, "run_intel_tests", marker("test", (True, "synthetic pass")))
    monkeypatch.setattr(promotion, "backup_operational_data_manifest", marker("ops_manifest", None))
    monkeypatch.setattr(promotion, "backup_previous_release", marker("backup", None))
    monkeypatch.setattr(promotion, "ensure_release_checkout", marker("checkout", None))
    monkeypatch.setattr(promotion, "build_status", marker("status", {
        "installed_runtime_sha": GOOD,
        "synchronization_status": "synthetic",
        "release_verification_status": "synthetic",
    }))
    monkeypatch.setattr(promotion, "save_json", marker("save", None))
    monkeypatch.setattr(promotion, "_append_log", marker("log", None))
    return SimpleNamespace(
        dev=dev, release=release, base=tmp_path, state=state,
        calls=calls, commands=commands, monkeypatch=monkeypatch,
    )


def denied(synthetic, **kwargs):
    result = promotion.promote(
        expected_sha=kwargs.pop("expected_sha", GOOD),
        skip_tests=kwargs.pop("skip_tests", False),
        allow_dirty_dev=kwargs.pop("allow_dirty_dev", False),
    )
    assert result["ok"] is False, result
    assert result.get("error"), result
    assert synthetic.calls == [], "Unsafe preflight performed a write/test/backup: " + repr(synthetic.calls)
    return result


def test_legacy_promotion_without_pinned_sha_refuses_before_side_effects(synthetic):
    # On the unmodified source, this legacy call accepts any clean Dev SHA,
    # executes the tests/backups/checkout and can report success.
    result = promotion.promote(skip_tests=False, allow_dirty_dev=False)
    assert not result["ok"]
    assert "sha" in result["error"].lower() or "pin" in result["error"].lower()
    assert synthetic.calls == []


@pytest.mark.parametrize("sha", [None, "", "abcd", "z" * 40, WRONG])
def test_absent_malformed_or_mismatched_pin_refuses(synthetic, sha):
    denied(synthetic, expected_sha=sha)


@pytest.mark.parametrize("flag", ["skip_tests", "allow_dirty_dev"])
def test_legacy_bypass_flags_cannot_override_preflight(synthetic, flag):
    denied(synthetic, **{flag: True})


def test_detached_dev_refuses_without_writes(synthetic):
    synthetic.state["branch"] = None
    denied(synthetic)


def test_noncanonical_dev_branch_refuses(synthetic):
    synthetic.state["branch"] = "main"
    denied(synthetic)


def test_dirty_dev_refuses_even_with_correct_pin(synthetic):
    synthetic.state["dirty"] = True
    denied(synthetic)


@pytest.mark.parametrize("field", ["head", "tracking", "live"])
def test_target_must_match_dev_local_tracking_and_live_remote(synthetic, field):
    synthetic.state[field] = WRONG
    denied(synthetic)


def test_offline_or_unauthorized_origin_blocks_not_assumed_fresh(synthetic):
    synthetic.state["remote_error"] = True
    denied(synthetic)
    synthetic.state["remote_error"] = False
    synthetic.state["remote_url"] = "https://github.com/other-account/other.git"
    denied(synthetic)


@pytest.mark.parametrize("name", [
    "pilot/START_ELYSIA1.bat",
    "pilot/START_ELYSIA_VERIFIED_PILOT.bat",
    "pilot/launch_verified_pilot.py",
])
def test_required_tracked_launcher_missing_denied_before_checkout(synthetic, name):
    synthetic.state["missing_launcher"] = name
    denied(synthetic)
    assert "checkout" not in synthetic.calls


def test_release_nested_inside_operational_data_is_refused(synthetic):
    target = synthetic.base / "ops" / "fake-release"
    target.mkdir()
    synthetic.monkeypatch.setenv("ELYSIA_RELEASE_ROOT", str(target))
    synthetic.monkeypatch.setattr(promotion, "release_root", lambda: target)
    denied(synthetic)


def test_release_ancestor_capturing_preserved_pilot_is_refused(synthetic):
    target = synthetic.base
    synthetic.monkeypatch.setenv("ELYSIA_RELEASE_ROOT", str(target))
    synthetic.monkeypatch.setattr(promotion, "release_root", lambda: target)
    denied(synthetic)


def test_release_symlink_to_unprotected_external_destination_is_refused(synthetic):
    external = synthetic.base / "elsewhere"
    external.mkdir()
    link = synthetic.base / "redirected-release"
    try:
        link.symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Synthetic real directory symlink unavailable on this host")
    synthetic.monkeypatch.setenv("ELYSIA_RELEASE_ROOT", str(link))
    synthetic.monkeypatch.setattr(promotion, "release_root", lambda: link.resolve())
    denied(synthetic)
    assert list(external.iterdir()) == []


def test_release_parent_symlink_is_refused(synthetic):
    external = synthetic.base / "elsewhere"
    external.mkdir(exist_ok=True)
    link = synthetic.base / "parent-link"
    try:
        link.symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Synthetic real directory symlink unavailable on this host")
    target = link / "new-release"
    synthetic.monkeypatch.setenv("ELYSIA_RELEASE_ROOT", str(target))
    synthetic.monkeypatch.setattr(promotion, "release_root", lambda: target.resolve())
    denied(synthetic)
    assert list(external.iterdir()) == []


def test_clean_pinned_preflight_preserves_existing_eligibility_without_promotion(synthetic):
    # Positive case uses only pure preflight; NO backup, checkout, tests,
    # launcher invocation, server startup, or installed state mutation.
    dev, release, sha = promotion._release_preflight(
        expected_sha=GOOD, skip_tests=False, allow_dirty_dev=False
    )
    assert (dev, release, sha) == (synthetic.dev, synthetic.release, GOOD)
    assert synthetic.calls == []
    assert any(args[0] == "ls-remote" for args in synthetic.commands)
    assert len([args for args in synthetic.commands if args[0] == "ls-tree"]) == 3

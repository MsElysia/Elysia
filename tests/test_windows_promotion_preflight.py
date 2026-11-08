"""Disposable, mock-network fail-closed Elysia release preflight regressions.

No real release, personal memory, backup tree, network call, or operator root.
These tests deliberately never invoke a successful promote() mutating path.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.windows_sync import gitutil
from tools.windows_sync import promote_release as promotion

PIN = "a" * 40
WRONG = "b" * 40
REQUIRED_LAUNCHERS = (
    "pilot/START_ELYSIA1.bat",
    "pilot/START_ELYSIA_VERIFIED_PILOT.bat",
    "pilot/launch_verified_pilot.py",
)


@pytest.fixture
def accepted(tmp_path, monkeypatch):
    dev = tmp_path / "dev"
    release = tmp_path / "release"
    protected = tmp_path / "protected"
    dev.mkdir()
    protected.mkdir()
    for name in REQUIRED_LAUNCHERS:
        item = dev / name
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_text("synthetic launcher fixture\n", encoding="utf-8")

    state = {"head": PIN, "branch": promotion.CANONICAL_BRANCH,
             "dirty": False, "cached": PIN, "remote": PIN,
             "fail_remote": False, "missing_tree": set()}
    monkeypatch.setattr(promotion.gitutil, "worktree_state", lambda _dev:
                        SimpleNamespace(head=state["head"],
                                        branch=state["branch"],
                                        dirty=state["dirty"]))
    monkeypatch.setattr(promotion.gitutil, "remote_ref_sha",
                        lambda *_args: state["cached"])

    def fake_git(_dev, args, **_kwargs):
        if args[:3] == ["ls-remote", "--exit-code", "origin"]:
            if state["fail_remote"]:
                raise gitutil.GitError("synthetic remote unavailable")
            return subprocess.CompletedProcess(
                ["git"], 0,
                f"{state['remote']}\trefs/heads/{promotion.CANONICAL_BRANCH}\n", "")
        if args[:2] == ["ls-tree", PIN]:
            target = args[-1]
            if target in state["missing_tree"]:
                return subprocess.CompletedProcess(["git"], 0, "", "")
            return subprocess.CompletedProcess(
                ["git"], 0, f"100644 blob {'c'*40}\t{target}\n", "")
        raise AssertionError(f"unexpected synthetic Git operation: {args!r}")

    monkeypatch.setattr(promotion.gitutil, "run_git", fake_git)
    kwargs = dict(expected_sha=PIN, dev=dev, release_requested=release,
                  protected_roots=(protected, dev),
                  skip_tests=False, allow_dirty_dev=False)
    return state, kwargs


def test_clean_pinned_normal_branch_remote_and_launchers_allow_prefight_only(accepted):
    _, kwargs = accepted
    assert promotion.preflight_release(**kwargs) == PIN
    assert not kwargs["release_requested"].exists()


@pytest.mark.parametrize("bad_sha", [None, "", "deadbeef", "a" * 39, "g" * 40, WRONG])
def test_missing_malformed_or_unapproved_sha_denied(accepted, bad_sha):
    _, kwargs = accepted
    with pytest.raises((RuntimeError, ValueError), match="SHA|sha|revision|expected"):
        promotion.preflight_release(**{**kwargs, "expected_sha": bad_sha})
    assert not kwargs["release_requested"].exists()


@pytest.mark.parametrize("attribute,value", [
    ("head", WRONG),
    ("cached", WRONG),
    ("cached", None),
    ("remote", WRONG),
    ("remote", "x" * 40),
    ("fail_remote", True),
])
def test_local_cached_and_live_remote_must_all_match_pinned_sha(accepted, attribute, value):
    state, kwargs = accepted
    state[attribute] = value
    with pytest.raises((RuntimeError, gitutil.GitError, ValueError)):
        promotion.preflight_release(**kwargs)
    assert not kwargs["release_requested"].exists()


@pytest.mark.parametrize("branch,dirty", [
    (None, False), ("feature/elsewhere", False),
    ("main", False), (promotion.CANONICAL_BRANCH, True),
])
def test_detached_foreign_or_dirty_dev_denied(accepted, branch, dirty):
    state, kwargs = accepted
    state.update(branch=branch, dirty=dirty)
    with pytest.raises(RuntimeError, match="branch|dirty|clean"):
        promotion.preflight_release(**kwargs)


@pytest.mark.parametrize("flag", ["skip_tests", "allow_dirty_dev"])
def test_old_emergency_flags_cannot_override_preflight(accepted, flag):
    _, kwargs = accepted
    with pytest.raises(RuntimeError, match="skip|bypass|allow|flag|not permitted"):
        promotion.preflight_release(**{**kwargs, flag: True})


@pytest.mark.parametrize("launcher", REQUIRED_LAUNCHERS)
def test_launcher_missing_on_disk_rejected_before_checkout(accepted, launcher):
    _, kwargs = accepted
    (kwargs["dev"] / launcher).unlink()
    with pytest.raises(RuntimeError, match="launcher|tracked|missing"):
        promotion.preflight_release(**kwargs)
    assert not kwargs["release_requested"].exists()


def test_launcher_untracked_in_pinned_tree_rejected(accepted):
    state, kwargs = accepted
    state["missing_tree"].add(REQUIRED_LAUNCHERS[1])
    with pytest.raises(RuntimeError, match="launcher|tracked|missing"):
        promotion.preflight_release(**kwargs)


@pytest.mark.parametrize("collision", [
    "equal_protected", "child_of_protected", "parent_of_protected",
    "equal_dev", "child_of_dev",
])
def test_protected_root_intersections_rejected(accepted, collision):
    _, kwargs = accepted
    protected, dev = kwargs["protected_roots"]
    candidate = {
        "equal_protected": protected,
        "child_of_protected": protected / "source",
        "parent_of_protected": protected.parent,
        "equal_dev": dev,
        "child_of_dev": dev / "release",
    }[collision]
    with pytest.raises(RuntimeError, match="protected|overlap|destination|root"):
        promotion.preflight_release(**{**kwargs, "release_requested": candidate})


def test_release_ancestor_symlink_refused_without_touching_target(accepted, tmp_path):
    _, kwargs = accepted
    external = tmp_path / "real-target"
    external.mkdir()
    (external / "sentinel").write_text("unchanged", encoding="utf-8")
    link = tmp_path / "release-link"
    try:
        link.symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"synthetic real symlink unavailable: {type(exc).__name__}")
    with pytest.raises(RuntimeError, match="link|reparse|junction|alias"):
        promotion.preflight_release(**{**kwargs, "release_requested": link / "new-release"})
    assert sorted(p.name for p in external.iterdir()) == ["sentinel"]


def test_release_root_symlink_refused(accepted, tmp_path):
    _, kwargs = accepted
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "release-alias"
    try:
        alias.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"synthetic real symlink unavailable: {type(exc).__name__}")
    with pytest.raises(RuntimeError, match="link|reparse|junction|alias"):
        promotion.preflight_release(**{**kwargs, "release_requested": alias})


def test_non_absolute_release_target_refused(accepted):
    _, kwargs = accepted
    with pytest.raises(RuntimeError, match="absolute|destination|root"):
        promotion.preflight_release(**{**kwargs, "release_requested": Path("relative-release")})


def test_synthetic_reparse_guard_rejects_inferred_windows_alias(accepted, monkeypatch):
    _, kwargs = accepted
    original = promotion._is_redirected_path
    monkeypatch.setattr(promotion, "_is_redirected_path",
                        lambda node: True if node == kwargs["release_requested"] else original(node))
    with pytest.raises(RuntimeError, match="junction|reparse|link|redirect"):
        promotion.preflight_release(**kwargs)


def test_promotion_denies_wrong_clean_head_before_all_side_effects(accepted, monkeypatch):
    """Same old bug: a clean but wrong tip could previously reach backup/checkout."""
    state, kwargs = accepted
    state["head"] = WRONG
    monkeypatch.setattr(promotion, "dev_root", lambda: kwargs["dev"])
    monkeypatch.setattr(promotion, "_configured_release_path",
                        lambda: kwargs["release_requested"])
    monkeypatch.setattr(promotion, "_protected_release_roots",
                        lambda dev: kwargs["protected_roots"])

    observed = []
    def forbidden(name):
        def fail(*_args, **_kw):
            observed.append(name)
            raise AssertionError(f"side effect before authorization: {name}")
        return fail
    for name in (
        "backup_operational_data_manifest", "backup_previous_release",
        "ensure_release_checkout", "run_intel_tests", "scan_repo_changed",
        "_append_log", "save_json", "state_root", "release_backup_root",
    ):
        monkeypatch.setattr(promotion, name, forbidden(name))
    result = promotion.promote(
        expected_sha=PIN, skip_tests=False, allow_dirty_dev=False)
    assert result["ok"] is False
    assert result["error"]
    assert observed == []
    assert not kwargs["release_requested"].exists()


def test_promotion_missing_pin_and_bypass_flags_no_side_effects(accepted, monkeypatch):
    _, kwargs = accepted
    monkeypatch.setattr(promotion, "dev_root", lambda: kwargs["dev"])
    monkeypatch.setattr(promotion, "_configured_release_path",
                        lambda: kwargs["release_requested"])
    monkeypatch.setattr(promotion, "_protected_release_roots",
                        lambda _dev: kwargs["protected_roots"])
    def prohibited(*_args, **_kw):
        raise AssertionError("preflight denial triggered mutation")
    for name in ("backup_operational_data_manifest", "backup_previous_release",
                 "ensure_release_checkout", "scan_repo_changed", "_append_log",
                 "save_json", "state_root"):
        monkeypatch.setattr(promotion, name, prohibited)
    for expected, skip, dirty in ((None, False, False), (PIN, True, False),
                                  (PIN, False, True)):
        result = promotion.promote(
            expected_sha=expected, skip_tests=skip, allow_dirty_dev=dirty)
        assert result["ok"] is False
        assert result["error"]
    assert not kwargs["release_requested"].exists()

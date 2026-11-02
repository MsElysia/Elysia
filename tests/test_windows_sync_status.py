"""Deterministic sync-status evidence regressions; no git, network or user data."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tools.windows_sync import gitutil

from tools.windows_sync import sync_check

SHA = "a" * 40
OTHER_SHA = "b" * 40
PREVIOUS_CHECK = "2026-10-31T12:00:00+00:00"


def _status(monkeypatch, tmp_path, *, dirty=False, fetch=True,
            ahead=0, behind=0, release_sha=SHA,
            release_evidence="git_checkout", release_dirty=False):
    dev = tmp_path / "dev"
    dev.mkdir()
    release = tmp_path / "release"
    release.mkdir()
    saved = []
    monkeypatch.setattr(sync_check, "dev_root", lambda: dev)
    monkeypatch.setattr(sync_check, "release_root", lambda: release)
    monkeypatch.setattr(sync_check, "status_path", lambda: tmp_path / "state.json")
    monkeypatch.setattr(sync_check, "load_json", lambda path: {
        "last_successful_check_utc": PREVIOUS_CHECK
    })
    monkeypatch.setattr(sync_check, "save_json", lambda path, data: saved.append(dict(data)))
    monkeypatch.setattr(sync_check.gitutil, "worktree_state", lambda path: SimpleNamespace(
        head=SHA, branch="integration/windows-canonical", dirty=dirty
    ))
    monkeypatch.setattr(sync_check.gitutil, "fetch", lambda path, remote: None)
    monkeypatch.setattr(sync_check.gitutil, "remote_ref_sha", lambda *args: SHA)
    monkeypatch.setattr(sync_check.gitutil, "ahead_behind", lambda *args: (ahead, behind))
    monkeypatch.setattr(sync_check, "read_release_identity", lambda path: (
        release_sha, release_evidence, release_dirty
    ))
    result = sync_check.build_status(do_fetch=fetch)
    assert saved and saved[-1] == result
    return result


def test_fresh_clean_equal_shas_remain_synchronized(monkeypatch, tmp_path):
    result = _status(monkeypatch, tmp_path)
    assert result["synchronization_status"] == "synchronized"
    assert result["release_verification_status"] == "matches_github_and_dev"
    assert result["fetch_ok"] is True
    assert result["last_successful_check_utc"] != PREVIOUS_CHECK


def test_dirty_equal_shas_are_not_verified_synchronized(monkeypatch, tmp_path):
    result = _status(monkeypatch, tmp_path, dirty=True)
    assert result["divergence"] == "identical"  # commit history only
    assert result["synchronization_status"] == "local_uncommitted_changes"
    assert result["release_verification_status"] == "source_sha_matches_but_dev_dirty"
    assert not result["pending_updates"]  # no remote commits pending
    assert any("uncommitted" in note for note in result["notes"])


def test_skipped_fetch_preserves_prior_success_and_marks_cached(monkeypatch, tmp_path):
    result = _status(monkeypatch, tmp_path, fetch=False)
    assert result["fetch_attempted"] is False
    assert result["fetch_ok"] is False
    assert result["last_successful_check_utc"] == PREVIOUS_CHECK
    assert result["synchronization_status"] == "cached_sha_match_unverified"
    assert result["release_verification_status"] == "source_sha_matches_cached_remote"


def test_dirty_and_no_fetch_do_not_look_verified(monkeypatch, tmp_path):
    result = _status(monkeypatch, tmp_path, dirty=True, fetch=False)
    assert result["synchronization_status"] == "local_uncommitted_changes"
    assert result["release_verification_status"] == "source_sha_matches_but_dev_dirty"
    assert result["last_successful_check_utc"] == PREVIOUS_CHECK


def test_git_comparison_failure_is_degraded_not_diverged(monkeypatch, tmp_path):
    result = _status(monkeypatch, tmp_path, ahead=-1, behind=-1, release_sha=OTHER_SHA)
    assert result["synchronization_status"] == "degraded"
    assert result["divergence"] == "unknown"
    assert result["pending_updates"] is True
    assert result["errors"]
    assert result["release_verification_status"] == "stale_or_mismatch"
    assert result["last_successful_check_utc"] == PREVIOUS_CHECK


def test_remote_ahead_remains_updates_available(monkeypatch, tmp_path):
    result = _status(monkeypatch, tmp_path, behind=2, release_sha=OTHER_SHA)
    assert result["synchronization_status"] == "updates_available"
    assert result["pending_updates"] is True
    assert result["release_verification_status"] == "stale_or_mismatch"


def test_equal_release_sha_does_not_claim_running_process(monkeypatch, tmp_path):
    result = _status(monkeypatch, tmp_path)
    assert result["installed_release_source_sha"] == SHA
    assert result["installed_runtime_sha"] == SHA  # legacy alias only
    assert result["release_source_evidence"] == "git_checkout"
    assert result["release_source_dirty"] is False
    assert result["running_runtime_sha"] is None
    assert result["running_runtime_verification"] == "not_checked"
    assert any("active process was not verified" in n for n in result["notes"])


def test_dirty_release_checkout_never_reports_verified_parity(monkeypatch, tmp_path):
    result = _status(monkeypatch, tmp_path, release_dirty=True)
    assert result["release_verification_status"] == "release_source_dirty"
    assert result["release_source_dirty"] is True
    assert result["pending_updates"] is True
    assert result["running_runtime_sha"] is None


def test_marker_identity_is_not_trusted_for_release_parity(monkeypatch, tmp_path):
    result = _status(monkeypatch, tmp_path, release_evidence="marker_unverified")
    assert result["release_verification_status"] == "release_source_unverified_marker"
    assert result["pending_updates"] is True


def test_missing_or_unreadable_release_not_reported_operational(monkeypatch, tmp_path):
    missing = _status(monkeypatch, tmp_path, release_sha=None, release_evidence="missing", release_dirty=None)
    assert missing["release_verification_status"] == "not_installed"
    inaccessible = _status(monkeypatch, tmp_path, release_sha=None, release_evidence="unavailable", release_dirty=None)
    assert inaccessible["release_verification_status"] == "release_source_unavailable"
    assert inaccessible["running_runtime_sha"] is None


def test_release_identity_reads_git_checkout_dirty_bit(monkeypatch, tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    monkeypatch.setattr(sync_check.gitutil, "worktree_state", lambda root: SimpleNamespace(
        head=SHA, dirty=True
    ))
    assert sync_check.read_release_identity(release) == (SHA, "git_checkout", True)


def test_release_identity_marker_is_unverified_and_rejects_invalid_sha(monkeypatch, tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    monkeypatch.setattr(sync_check.gitutil, "worktree_state", lambda root: (
        (_ for _ in ()).throw(gitutil.GitError("not a checkout"))
    ))
    marker = release / "RELEASE_SHA.txt"
    marker.write_text(SHA, encoding="utf-8")
    assert sync_check.read_release_identity(release) == (SHA, "marker_unverified", None)
    marker.write_text("truncated-sha", encoding="utf-8")
    assert sync_check.read_release_identity(release) == (None, "invalid_marker", None)

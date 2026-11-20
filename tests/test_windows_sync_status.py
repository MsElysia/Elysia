"""Deterministic sync-status evidence regressions; no git, network or user data."""
from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from tools.windows_sync import gitutil

from tools.windows_sync import sync_check

SHA = "a" * 40
OTHER_SHA = "b" * 40
PREVIOUS_CHECK = "2026-10-31T12:00:00+00:00"


def _status(monkeypatch, tmp_path, *, dirty=False, fetch=True,
            ahead=0, behind=0, release_sha=SHA,
            release_evidence="git_checkout", release_dirty=False):
    dev = tmp_path / "dev"
    dev.mkdir(exist_ok=True)
    release = tmp_path / "release"
    release.mkdir(exist_ok=True)
    saved = []
    monkeypatch.setattr(sync_check, "dev_root", lambda: dev)
    monkeypatch.setattr(sync_check, "release_root", lambda: release)
    monkeypatch.setattr(sync_check, "status_path", lambda: tmp_path / "state.json")
    monkeypatch.setattr(sync_check, "load_json", lambda path: {
        "last_successful_check_utc": PREVIOUS_CHECK
    })
    monkeypatch.setattr(sync_check, "save_json", lambda path, data: saved.append(dict(data)))
    monkeypatch.setattr(sync_check.gitutil, "worktree_state", lambda path: SimpleNamespace(
        head=SHA, branch="integration/windows-canonical", dirty=dirty,
        porcelain=" M file" if dirty else ""
    ))
    monkeypatch.setattr(sync_check.gitutil, "fetch", lambda path, remote: None)
    monkeypatch.setattr(sync_check, "_trusted_canonical_origin",
                        lambda path: "https://github.com/MsElysia/Elysia.git")
    monkeypatch.setattr(sync_check, "_live_canonical_sha", lambda path: SHA)
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
    assert result["pending_updates"] is None
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
    monkeypatch.setattr(sync_check.gitutil, "run_git", lambda *args: SimpleNamespace(
        stdout=str(release)
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


# Real disposable repositories exercise Git porcelain, branch and ref observations.
def _git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, stderr=subprocess.PIPE,
    ).strip()


@pytest.fixture
def real_sync(tmp_path, monkeypatch):
    dev = tmp_path / "dev"
    dev.mkdir()
    _git(dev, "init", "-b", "integration/windows-canonical")
    _git(dev, "config", "user.email", "test@example.invalid")
    _git(dev, "config", "user.name", "Synthetic Test")
    (dev / "sample.txt").write_text("synthetic")
    _git(dev, "add", "sample.txt")
    _git(dev, "commit", "-m", "initial")
    sha = _git(dev, "rev-parse", "HEAD")
    _git(dev, "update-ref", "refs/remotes/origin/integration/windows-canonical", sha)
    release = tmp_path / "release"
    subprocess.run(
        ["git", "clone", "--quiet", "--no-hardlinks", str(dev), str(release)],
        check=True,
    )
    path = tmp_path / "status.json"
    path.write_text(json.dumps({"last_successful_check_utc": PREVIOUS_CHECK}))
    monkeypatch.setattr(sync_check, "dev_root", lambda: dev)
    monkeypatch.setattr(sync_check, "release_root", lambda: release)
    monkeypatch.setattr(sync_check, "status_path", lambda: path)
    monkeypatch.setattr(sync_check.gitutil, "fetch", lambda *a: None)
    monkeypatch.setattr(sync_check, "_trusted_canonical_origin",
                        lambda path: "https://github.com/MsElysia/Elysia.git")
    monkeypatch.setattr(sync_check, "_live_canonical_sha",
                        lambda path: sync_check.gitutil.remote_ref_sha(
                            path, "origin", "integration/windows-canonical"
                        ))

    def check(do_fetch=True):
        result = sync_check.build_status(do_fetch=do_fetch)
        assert json.loads(path.read_text()) == result
        return result

    return dev, release, sha, check


def test_real_git_stable_clean_source_parity(real_sync):
    dev, release, sha, check = real_sync
    status = check()
    assert status["synchronization_status"] == "synchronized"
    assert status["release_verification_status"] == "matches_github_and_dev"
    assert status["installed_runtime_sha"] == status["installed_release_source_sha"] == sha
    assert status["remote_observation"] == "freshly_fetched"
    assert status["running_runtime_sha"] is None


@pytest.mark.parametrize("edit", ["untracked", "head", "branch"])
def test_real_git_edit_during_fetch_is_not_green(real_sync, monkeypatch, edit):
    dev, release, sha, check = real_sync

    def fetch(*args):
        if edit == "untracked":
            (dev / "during.txt").write_text("changed")
        elif edit == "branch":
            _git(dev, "checkout", "-b", "other-branch")
        else:
            (dev / "during.txt").write_text("changed")
            _git(dev, "add", "during.txt")
            _git(dev, "commit", "-m", "during")

    monkeypatch.setattr(sync_check.gitutil, "fetch", fetch)
    status = check()
    assert status["synchronization_status"] == "changed_during_check"
    assert status["release_verification_status"] == "source_identity_unstable"
    assert status["github_sha"] is None
    assert status["ahead"] is None and status["behind"] is None
    assert status["pending_updates"] is None
    assert status["last_successful_check_utc"] == PREVIOUS_CHECK
    assert status["errors"]


@pytest.mark.parametrize("source", ["remote", "release", "final_unavailable"])
def test_real_git_final_identity_change_is_not_green(real_sync, monkeypatch, source):
    dev, release, sha, check = real_sync
    if source == "remote":
        original = sync_check.gitutil.remote_ref_sha
        reads = [0]

        def remote(*args):
            reads[0] += 1
            if reads[0] == 2:
                _git(dev, "update-ref", "-d", "refs/remotes/origin/integration/windows-canonical")
            return original(*args)

        monkeypatch.setattr(sync_check.gitutil, "remote_ref_sha", remote)
    elif source == "release":
        original = sync_check.read_release_identity
        reads = [0]

        def identity(*args):
            reads[0] += 1
            if reads[0] == 2:
                (release / "new").write_text("edited")
            return original(*args)

        monkeypatch.setattr(sync_check, "read_release_identity", identity)
    else:
        original = sync_check.gitutil.worktree_state
        reads = [0]

        def identity(*args):
            reads[0] += 1
            if reads[0] == 2:
                raise gitutil.GitError("unavailable")
            return original(*args)

        monkeypatch.setattr(sync_check.gitutil, "worktree_state", identity)
    status = check()
    assert status["synchronization_status"] in ("changed_during_check", "degraded")
    assert status["github_sha"] is None
    assert status["pending_updates"] is None
    assert status["last_successful_check_utc"] == PREVIOUS_CHECK


def test_real_git_dirty_initial_has_no_clean_parity(real_sync):
    dev, release, sha, check = real_sync
    (dev / "local.txt").write_text("uncommitted")
    result = check()
    assert result["synchronization_status"] == "local_uncommitted_changes"
    assert result["release_verification_status"] == "source_sha_matches_but_dev_dirty"
    assert result["divergence"] == "identical"


def test_real_git_nested_release_does_not_inherit_parent_checkout(real_sync, monkeypatch):
    dev, release, sha, check = real_sync
    nested = dev / "nested"
    nested.mkdir()
    (nested / "RELEASE_SHA.txt").write_text(sha)
    monkeypatch.setattr(sync_check, "release_root", lambda: nested)
    result = check()
    assert result["release_source_evidence"] == "marker_unverified"
    assert result["release_verification_status"] == "release_source_unverified_marker"


def test_real_git_remote_ahead_and_cached_status(real_sync):
    dev, release, sha, check = real_sync
    _git(dev, "checkout", "-b", "new-remote")
    (dev / "extra").write_text("remote")
    _git(dev, "add", "extra")
    _git(dev, "commit", "-m", "remote")
    remote = _git(dev, "rev-parse", "HEAD")
    _git(dev, "checkout", "integration/windows-canonical")
    _git(dev, "update-ref", "refs/remotes/origin/integration/windows-canonical", remote)
    fresh = check()
    assert fresh["behind"] == 1 and fresh["synchronization_status"] == "updates_available"
    cached = check(do_fetch=False)
    assert cached["remote_observation"] == "cached_unverified"
    assert cached["pending_updates"] is None
    assert cached["last_successful_check_utc"] == fresh["last_successful_check_utc"]


def test_status_json_and_report_remain_source_only(real_sync):
    dev, release, sha, check = real_sync
    status = check()
    assert status["operational_verification"]["installed_launcher_startup"] == "not_tested_by_this_check"
    assert status["release_verification_scope"] == "git_head_or_release_marker_comparison_only"
    assert status["running_runtime_verification"] == "not_checked"


def test_real_git_fetch_failure_preserves_last_success(real_sync, monkeypatch):
    dev, release, sha, check = real_sync
    monkeypatch.setattr(
        sync_check.gitutil, "fetch",
        lambda *args: (_ for _ in ()).throw(gitutil.GitError("offline")),
    )
    result = check()
    assert result["fetch_ok"] is False
    assert result["synchronization_status"] == "degraded"
    assert result["github_sha"] is None
    assert result["pending_updates"] is None
    assert result["last_successful_check_utc"] == PREVIOUS_CHECK


@pytest.mark.parametrize("result", [(-1, -1), (-1, 0), (0, -1)])
def test_real_git_history_failure_is_unknown(real_sync, monkeypatch, result):
    dev, release, sha, check = real_sync
    monkeypatch.setattr(sync_check.gitutil, "ahead_behind", lambda *args: result)
    status = check()
    assert status["synchronization_status"] == "degraded"
    assert status["divergence"] == "unknown"
    assert status["ahead"] is None and status["behind"] is None
    assert status["pending_updates"] is None
    assert status["last_successful_check_utc"] == PREVIOUS_CHECK


def test_report_and_cli_return_errors_for_unstable_status(real_sync, monkeypatch, capsys):
    from tools.windows_sync import status_report
    dev, release, sha, check = real_sync
    monkeypatch.setattr(
        sync_check.gitutil, "fetch",
        lambda *args: (dev / "during.txt").write_text("new"),
    )
    status = check()
    rendered = status_report.render_text(status)
    assert "changed_during_check" in rendered
    assert "Source SHA only" in rendered
    assert "NOT TESTED BY THIS CHECK" in rendered
    monkeypatch.setattr(status_report, "build_status", lambda **kwargs: status)
    assert status_report.main(["--json"]) == 2
    assert "changed_during_check" in capsys.readouterr().out



def _trusted_bare_fixture(tmp_path, monkeypatch):
    """Test live Git with an isolated bare remote; only trust policy is adapted."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare")
    dev = tmp_path / "dev-live"
    dev.mkdir()
    _git(dev, "init", "-b", "integration/windows-canonical")
    _git(dev, "config", "user.name", "Synthetic")
    _git(dev, "config", "user.email", "test@example.invalid")
    (dev / "example.txt").write_text("Version A", encoding="utf-8")
    _git(dev, "add", "example.txt")
    _git(dev, "commit", "-m", "A")
    a = _git(dev, "rev-parse", "HEAD")
    _git(dev, "remote", "add", "origin", str(origin))
    _git(dev, "push", "-u", "origin", "integration/windows-canonical")
    release = tmp_path / "release-live"
    subprocess.run(
        ["git", "clone", "-q", "--branch", "integration/windows-canonical",
         str(origin), str(release)],
        check=True,
    )
    writer = tmp_path / "writer"
    subprocess.run(
        ["git", "clone", "-q", "--branch", "integration/windows-canonical",
         str(origin), str(writer)],
        check=True,
    )
    _git(writer, "config", "user.name", "Synthetic")
    _git(writer, "config", "user.email", "test@example.invalid")
    path = tmp_path / "status-live.json"
    path.write_text(json.dumps({"last_successful_check_utc": PREVIOUS_CHECK}))
    monkeypatch.setattr(sync_check, "dev_root", lambda: dev)
    monkeypatch.setattr(sync_check, "release_root", lambda: release)
    monkeypatch.setattr(sync_check, "status_path", lambda: path)
    # Only the trust validator permits this fixture's local bare origin.
    # Actual gitutil.fetch, Git remote get-url, ls-remote and rev-list execute.
    monkeypatch.setattr(sync_check, "_canonical_origin",
                        lambda url: url.strip() == str(origin))
    return origin, dev, release, writer, a, path


def _writer_push(writer, content="Version B"):
    (writer / "example.txt").write_text(content, encoding="utf-8")
    _git(writer, "commit", "-am", "update")
    tip = _git(writer, "rev-parse", "HEAD")
    _git(writer, "push", "origin", "integration/windows-canonical")
    return tip


def test_actual_git_custom_refspec_does_not_certify_stale_tip(tmp_path, monkeypatch):
    origin, dev, release, writer, a, state_path = _trusted_bare_fixture(tmp_path, monkeypatch)
    b = _writer_push(writer)
    _git(writer, "checkout", "-b", "other-fetched-branch")
    _git(writer, "push", "origin", "other-fetched-branch")
    _git(dev, "config", "--unset-all", "remote.origin.fetch")
    _git(dev, "config", "--add", "remote.origin.fetch",
         "+refs/heads/other-fetched-branch:refs/remotes/origin/other-fetched-branch")
    status = sync_check.build_status(do_fetch=True)
    assert _git(dev, "rev-parse", "refs/remotes/origin/integration/windows-canonical") == a
    assert _git(dev, "ls-remote", "--exit-code", "origin",
                "refs/heads/integration/windows-canonical").split()[0] == b
    assert status["fetch_ok"] is False
    assert status["synchronization_status"] == "degraded"
    assert status["github_sha"] is None and status["pending_updates"] is None
    assert status["last_successful_check_utc"] == PREVIOUS_CHECK
    assert status["release_verification_status"] != "matches_github_and_dev"
    assert json.loads(state_path.read_text()) == status
    assert "http" not in str(status["errors"]).lower()


def test_actual_git_canonical_refspec_fetch_gets_new_tip(tmp_path, monkeypatch):
    origin, dev, release, writer, a, state_path = _trusted_bare_fixture(tmp_path, monkeypatch)
    b = _writer_push(writer)
    status = sync_check.build_status(do_fetch=True)
    assert status["fetch_ok"] is True
    assert status["remote_observation"] == "freshly_fetched"
    assert status["github_sha"] == b
    assert status["synchronization_status"] == "updates_available"
    assert status["behind"] == 1 and status["ahead"] == 0
    assert status["pending_updates"] is True
    assert json.loads(state_path.read_text()) == status
    assert status["last_successful_check_utc"] != PREVIOUS_CHECK


def test_actual_git_stable_clean_authoritative_parity(tmp_path, monkeypatch):
    origin, dev, release, writer, a, state_path = _trusted_bare_fixture(tmp_path, monkeypatch)
    status = sync_check.build_status(do_fetch=True)
    assert status["fetch_ok"] is True
    assert status["github_sha"] == a
    assert status["synchronization_status"] == "synchronized"
    assert status["release_verification_status"] == "matches_github_and_dev"
    assert status["pending_updates"] is False
    assert status["last_successful_check_utc"] != PREVIOUS_CHECK


def test_actual_git_missing_live_canonical_degrades(tmp_path, monkeypatch):
    origin, dev, release, writer, a, state_path = _trusted_bare_fixture(tmp_path, monkeypatch)
    _git(origin, "update-ref", "-d", "refs/heads/integration/windows-canonical")
    status = sync_check.build_status(do_fetch=True)
    assert status["synchronization_status"] == "degraded"
    assert status["github_sha"] is None
    assert status["fetch_ok"] is False and status["pending_updates"] is None
    assert status["last_successful_check_utc"] == PREVIOUS_CHECK


def test_actual_git_untrusted_origin_stops_before_fetch(tmp_path, monkeypatch):
    origin, dev, release, writer, a, state_path = _trusted_bare_fixture(tmp_path, monkeypatch)
    # Restore real allowlist and assert no attempt is made to contact origin.
    def disallow(_):
        return False
    monkeypatch.setattr(sync_check, "_canonical_origin", disallow)
    monkeypatch.setattr(sync_check.gitutil, "fetch", lambda *a: pytest.fail("fetch contacted bad origin"))
    status = sync_check.build_status(do_fetch=True)
    assert status["synchronization_status"] == "degraded"
    assert status["github_sha"] is None and status["pending_updates"] is None
    assert status["last_successful_check_utc"] == PREVIOUS_CHECK
    assert "http" not in str(status["errors"]).lower()
    assert str(origin) not in str(status["errors"])


@pytest.mark.parametrize("url,allowed", [
    ("https://github.com/MsElysia/Elysia", True),
    ("https://github.com/MsElysia/Elysia.git", True),
    ("git@github.com:MsElysia/Elysia.git", True),
    ("ssh://git@github.com/MsElysia/Elysia", True),
    ("https://github.com/other/Elysia.git", False),
    ("https://user@github.com/MsElysia/Elysia.git", False),
    ("https://github.com/MsElysia/Elysia-other", False),
    ("https://github.com/MsElysia/Elysia.git.evil.invalid", False),
])
def test_authoritative_origin_allowlist_exactness(url, allowed):
    # Uses the actual production validator, no network traffic.
    assert sync_check._canonical_origin(url) is allowed


def test_actual_git_live_tip_changes_at_final_read(tmp_path, monkeypatch):
    origin, dev, release, writer, a, state_path = _trusted_bare_fixture(tmp_path, monkeypatch)
    original = sync_check._live_canonical_sha
    counter = [0]
    def update_before_second_read(root):
        counter[0] += 1
        if counter[0] == 2:
            _writer_push(writer)
        return original(root)
    monkeypatch.setattr(sync_check, "_live_canonical_sha", update_before_second_read)
    status = sync_check.build_status(do_fetch=True)
    assert counter[0] == 2
    assert status["synchronization_status"] == "changed_during_check"
    assert status["github_sha"] is None and status["pending_updates"] is None
    assert status["last_successful_check_utc"] == PREVIOUS_CHECK


def test_untrusted_origin_and_failed_fetch_errors_never_echo_urls(real_sync, monkeypatch):
    dev, release, sha, check = real_sync
    monkeypatch.setattr(sync_check, "_trusted_canonical_origin",
                        lambda *args: "https://github.com/MsElysia/Elysia.git")
    def failed_fetch(*args):
        raise gitutil.GitError("AUTH_PRIVATE_SENTINEL unavailable")
    monkeypatch.setattr(sync_check.gitutil, "fetch", failed_fetch)
    status = check()
    assert status["synchronization_status"] == "degraded"
    assert "AUTH_PRIVATE_SENTINEL" not in str(status)
    assert status["fetch_ok"] is False
    assert status["last_successful_check_utc"] == PREVIOUS_CHECK

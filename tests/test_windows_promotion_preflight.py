"""Synthetic, no-install regressions for the Windows promotion safety preflight.

These tests never use the operator's Dev/Release/operational/backup paths.
The original script accepted a clean, wrong Dev tip without an external pin
and allowed --skip-tests/--allow-dirty-dev. This test-first file requires
the existing promotable entrypoint to refuse those paths before any writes.
"""
from __future__ import annotations

import os
import subprocess
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
    (dev / "pilot").mkdir()
    for name in promotion._STABLE_LAUNCHERS:
        path = dev / name
        path.write_text("# synthetic launcher only\n", encoding="utf-8")
    (release / "pilot").mkdir(parents=True)
    (release / "pilot" / "START_ELYSIA1.bat").write_text(
        "@echo off\nrem synthetic only\n", encoding="utf-8"
    )
    # A genuine clean Git checkout under TEMP, never the user's Release.
    subprocess.run(["git", "init", "-q"], cwd=release, check=True)
    subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=release, check=True)
    subprocess.run(["git", "config", "user.name", "Synthetic"], cwd=release, check=True)
    subprocess.run(["git", "remote", "add", "origin", "https://github.com/MsElysia/Elysia.git"], cwd=release, check=True)
    subprocess.run(["git", "add", "."], cwd=release, check=True)
    subprocess.run(["git", "commit", "-qm", "synthetic release baseline"], cwd=release, check=True)
    (tmp_path / "executing-source").mkdir()
    monkeypatch.setattr(promotion, "_REPO", tmp_path / "executing-source")
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
    # Any preflight denial must never even enter the state writer.
    state_calls = []
    def forbidden_state_root():
        state_calls.append("state_root")
        return tmp_path / "state"
    monkeypatch.setattr(promotion, "state_root", forbidden_state_root)

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

    real_git = promotion._git_preflight
    def fake_git(repo, *args):
        if repo == release:
            # Verify actual Git worktree/head/dirty/remote, not just mocked
            # release metadata. Git subprocess operates in disposable TEMP.
            return real_git(repo, *args)
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
        calls=calls, commands=commands, state_calls=state_calls,
        monkeypatch=monkeypatch,
    )


def denied(synthetic, **kwargs):
    existing_launcher = (synthetic.release / "pilot" / "START_ELYSIA1.bat").read_bytes()
    result = promotion.promote(
        expected_sha=kwargs.pop("expected_sha", GOOD),
        skip_tests=kwargs.pop("skip_tests", False),
        allow_dirty_dev=kwargs.pop("allow_dirty_dev", False),
    )
    assert result["ok"] is False, result
    assert result.get("error"), result
    assert synthetic.calls == [], "Unsafe preflight performed a write/test/backup: " + repr(synthetic.calls)
    assert synthetic.state_calls == [], "Unsafe preflight reached state_root"
    assert (synthetic.release / "pilot" / "START_ELYSIA1.bat").read_bytes() == existing_launcher
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
    assert synthetic.state_calls == []
    assert any(args[0] == "ls-remote" for args in synthetic.commands)
    assert len([args for args in synthetic.commands if args[0] == "ls-tree"]) == 3


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows junction test")
def test_release_native_windows_junction_is_refused_when_available(synthetic):
    external = synthetic.base / "windows-junction-target"
    external.mkdir()
    link = synthetic.base / "windows-junction"
    create = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(external)],
        capture_output=True, text=True, timeout=10,
    )
    if create.returncode:
        pytest.skip("No unprivileged junction creation on this Windows runner")
    assert link.is_junction()
    synthetic.monkeypatch.setenv("ELYSIA_RELEASE_ROOT", str(link))
    synthetic.monkeypatch.setattr(promotion, "release_root", lambda: link.resolve())
    denied(synthetic)
    assert list(external.iterdir()) == []


def test_git_preflight_does_not_inherit_forged_git_dir(tmp_path, monkeypatch):
    """Actual disposable Git: -C must not be displaced by GIT_DIR variables."""
    a, b = tmp_path / "repo-a", tmp_path / "repo-b"
    for dest, label in ((a, "A"), (b, "B")):
        dest.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
        subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"],
                       cwd=dest, check=True)
        subprocess.run(["git", "config", "user.name", "Synthetic"],
                       cwd=dest, check=True)
        (dest / "synthetic.txt").write_text(label, encoding="utf-8")
        subprocess.run(["git", "add", "synthetic.txt"], cwd=dest, check=True)
        subprocess.run(["git", "commit", "-qm", "synthetic"],
                       cwd=dest, check=True)
    real_b = promotion._git_preflight(b, "rev-parse", "--verify", "HEAD")
    real_a = promotion._git_preflight(a, "rev-parse", "--verify", "HEAD")
    assert real_a != real_b
    monkeypatch.setenv("GIT_DIR", str(a / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(a))
    monkeypatch.setenv("GIT_INDEX_FILE", str(a / ".git" / "index"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.worktree")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(a))
    assert promotion._git_preflight(b, "rev-parse", "--verify", "HEAD") == real_b


def test_existing_dirty_release_is_blocked_before_any_backup_or_test(synthetic):
    """Actual disposable Git status: tracked changes must block in preflight."""
    original = synthetic.release / "pilot" / "START_ELYSIA1.bat"
    original.write_text("@echo off\nrem UNSAVED synthetic local edit\n", encoding="utf-8")
    result = denied(synthetic)
    assert "release" in result["error"].lower()
    assert "dirty" in result["error"].lower() or "modified" in result["error"].lower()


def test_existing_release_untracked_file_blocks_before_any_mutation(synthetic):
    (synthetic.release / "synthetic-untracked.txt").write_text("untracked", encoding="utf-8")
    denied(synthetic)


def test_existing_release_unidentified_git_tree_blocks(synthetic):
    # Existing directory is not a valid release Git checkout. No fake/mocked
    # release state can bypass an actual Git subprocess failure.
    # Rename disposable Git metadata: Windows Git objects may be read-only.
    (synthetic.release / ".git").rename(synthetic.base / "displaced-synthetic-git")
    assert not (synthetic.release / ".git").exists()
    denied(synthetic)


def test_existing_release_with_wrong_origin_blocks(synthetic):
    subprocess.run(
        ["git", "remote", "set-url", "origin", "https://github.com/other/forged.git"],
        cwd=synthetic.release, check=True,
    )
    denied(synthetic)


def test_clean_absent_release_preflight_remains_eligible(synthetic):
    """A previously absent Release may be added later after separate authority."""
    # Keep disposable Git objects intact while simulating an absent Release.
    synthetic.release.rename(synthetic.base / "displaced-synthetic-release")
    dev, release, sha = promotion._release_preflight(
        expected_sha=GOOD, skip_tests=False, allow_dirty_dev=False,
    )
    assert dev == synthetic.dev and release == synthetic.release and sha == GOOD
    assert synthetic.calls == [] and synthetic.state_calls == []
    assert not synthetic.release.exists()


@pytest.mark.parametrize("shape", ["equal", "child", "parent"])
def test_release_overlapping_executing_repo_is_blocked(synthetic, shape):
    # Deliberately leave Dev in a separate temp worktree, so checking Dev
    # alone cannot protect the currently executing Python source tree.
    repo = synthetic.base / "isolated-execution-root" / "source"
    repo.mkdir(parents=True)
    synthetic.monkeypatch.setattr(promotion, "_REPO", repo)
    if shape == "equal":
        path = repo
    elif shape == "child":
        path = repo / "fake-release"
        path.mkdir()
    else:
        path = repo.parent
    synthetic.monkeypatch.setenv("ELYSIA_RELEASE_ROOT", str(path))
    synthetic.monkeypatch.setattr(promotion, "release_root", lambda: path)
    # Assert the PRECISE guard, not merely a later non-Git Release error.
    with pytest.raises(RuntimeError, match="release destination overlaps protected source/data/storage"):
        promotion._safe_release_destination(synthetic.dev)
    # Counterfactual: remove only the executing-source overlap by pointing
    # _REPO somewhere unrelated. All other protected roots remain identical.
    # The candidate must now pass destination validation; this prevents a
    # vacuous green from an unrelated Dev/ops/state/backup overlap.
    with synthetic.monkeypatch.context() as scope:
        scope.setattr(promotion, "_REPO", synthetic.base / "unrelated-source")
        assert promotion._safe_release_destination(synthetic.dev) == path
    # Secondary full-entrypoint check preserves the no-side-effect contract.
    denied(synthetic)


@pytest.mark.parametrize("name", [
    "pilot/START_ELYSIA1.bat",
    "pilot/START_ELYSIA_VERIFIED_PILOT.bat",
    "pilot/launch_verified_pilot.py",
])
def test_missing_on_disk_launcher_blocks_despite_forged_clean_git_index(synthetic, name):
    # The fake Git layer insists status clean and launcher tracked, yet
    # real on-disk file is absent. Mirrors skip-worktree/sparse checkout.
    (synthetic.dev / name).unlink()
    denied(synthetic)
    assert synthetic.state["missing_launcher"] is None


def test_symlinked_on_disk_launcher_blocks_despite_clean_git_index(synthetic):
    src = synthetic.dev / "pilot" / "START_ELYSIA1.bat"
    src.unlink()
    target = synthetic.base / "external-launcher.txt"
    target.write_text("synthetic only", encoding="utf-8")
    try:
        src.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Real file symlink unsupported: {type(exc).__name__}")
    denied(synthetic)
    assert target.read_text(encoding="utf-8") == "synthetic only"


def test_pilot_symlinked_parent_blocks_despite_tracked_launcher(synthetic):
    import shutil
    shutil.rmtree(synthetic.dev / "pilot")
    external = synthetic.base / "other-pilot"
    external.mkdir()
    for name in promotion._STABLE_LAUNCHERS:
        (external / Path(name).name).write_text("synthetic", encoding="utf-8")
    try:
        (synthetic.dev / "pilot").symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Real directory symlink unsupported: {type(exc).__name__}")
    denied(synthetic)


# Task 008: real disposable two-repository Git regression, NOT a mock of checkout.
# Preflight already strips GIT_*, but the subsequent gitutil write path did not.
@pytest.fixture
def isolated_git_pair(tmp_path):
    root = tmp_path / "git-env-008"
    root.mkdir()
    bare, a, b = (root / "origin.git", root / "repo-a", root / "repo-b")
    clean_env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    clean_env["GIT_TERMINAL_PROMPT"] = "0"

    def git(directory, *args, check=True):
        result = subprocess.run(
            ["git", "-C", str(directory), *args],
            env=clean_env, text=True, capture_output=True, timeout=20,
        )
        if check:
            assert result.returncode == 0, (
                f"synthetic git {args[0]} failed: {result.stderr}"
            )
        return result.stdout.strip()

    git(root, "init", "--bare", str(bare))
    git(root, "clone", str(bare), str(b))
    git(b, "config", "user.name", "Synthetic Tester")
    git(b, "config", "user.email", "synthetic@example.invalid")
    tracked = "synthetic-checkout.txt"
    (b / tracked).write_text("BASE\n", encoding="utf-8")
    git(b, "add", tracked)
    git(b, "commit", "-m", "synthetic shared base")
    common = git(b, "rev-parse", "HEAD")
    git(b, "push", "origin", "HEAD:refs/heads/integration/windows-canonical")
    git(root, "clone", "--branch", "integration/windows-canonical", str(bare), str(a))
    git(a, "config", "user.name", "Synthetic Tester")
    git(a, "config", "user.email", "synthetic@example.invalid")
    (a / tracked).write_text("REPOSITORY A: MUST NOT CHANGE\n", encoding="utf-8")
    git(a, "commit", "-am", "synthetic A divergent commit")
    a_head = git(a, "rev-parse", "HEAD")
    (b / tracked).write_text("REPOSITORY B: MUST TARGET B\n", encoding="utf-8")
    git(b, "commit", "-am", "synthetic B divergent commit")
    b_head = git(b, "rev-parse", "HEAD")
    assert len({common, a_head, b_head}) == 3
    assert Path(git(b, "remote", "get-url", "origin")).resolve() == bare.resolve()
    assert Path(git(a, "remote", "get-url", "origin")).resolve() == bare.resolve()
    return SimpleNamespace(
        root=root, bare=bare, a=a, b=b, common=common,
        a_head=a_head, b_head=b_head, git=git, clean_env=clean_env,
        a_contents=(a / tracked).read_bytes(),
        b_contents=(b / tracked).read_bytes(),
        tracked=tracked,
    )


def _poison_git_environment(monkeypatch, pair):
    # In an UNSANITIZED subprocess, Git -C B follows A's Git metadata.
    monkeypatch.setenv("GIT_DIR", str(pair.a / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(pair.a))
    monkeypatch.setenv("GIT_INDEX_FILE", str(pair.a / ".git" / "index"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.worktree")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(pair.a))


def _assert_a_unchanged(pair):
    assert pair.git(pair.a, "rev-parse", "HEAD") == pair.a_head
    assert (pair.a / pair.tracked).read_bytes() == pair.a_contents
    assert pair.git(pair.a, "status", "--porcelain=v1") == ""


def test_actual_post_preflight_checkout_ignores_inherited_git_identity(isolated_git_pair, monkeypatch):
    """A and B share a reachable base commit; baseline can wrongly checkout A.

    A generic GitError or missing object cannot satisfy this test: checked-out
    B HEAD MUST change to the pinned base, while A HEAD and bytes cannot change.
    """
    pair = isolated_git_pair
    _poison_git_environment(monkeypatch, pair)
    raw = subprocess.run(
        ["git", "-C", str(pair.b), "rev-parse", "HEAD"],
        capture_output=True, text=True, timeout=20,
    )
    assert raw.returncode == 0
    assert raw.stdout.strip() == pair.a_head != pair.b_head, (
        "Negative control must prove raw Git -C B is redirected to A"
    )
    # The function makes real subprocess Git status/fetch/checkout calls.
    # Its origin is a local disposable bare repository, never public network.
    promotion.ensure_release_checkout(pair.b, pair.b, pair.common)
    assert pair.git(pair.b, "rev-parse", "HEAD") == pair.common
    assert (pair.b / pair.tracked).read_text(encoding="utf-8") == "BASE\n"
    _assert_a_unchanged(pair)


def test_actual_post_preflight_checkout_without_poison_still_works(isolated_git_pair):
    pair = isolated_git_pair
    promotion.ensure_release_checkout(pair.b, pair.b, pair.common)
    assert pair.git(pair.b, "rev-parse", "HEAD") == pair.common
    _assert_a_unchanged(pair)


def test_actual_worktree_creation_ignores_inherited_git_identity(isolated_git_pair, monkeypatch):
    pair = isolated_git_pair
    new_release = pair.root / "new-release"
    assert not new_release.exists()
    before_a_worktrees = pair.git(pair.a, "worktree", "list", "--porcelain")
    _poison_git_environment(monkeypatch, pair)
    promotion.ensure_release_checkout(pair.b, new_release, pair.common)
    assert new_release.is_dir()
    assert pair.git(new_release, "rev-parse", "HEAD") == pair.common
    assert Path(pair.git(new_release, "rev-parse", "--show-toplevel")).resolve() == new_release.resolve()
    assert pair.git(pair.a, "worktree", "list", "--porcelain") == before_a_worktrees
    _assert_a_unchanged(pair)
    assert pair.git(pair.b, "rev-parse", "HEAD") == pair.b_head


def test_bad_pinned_checkout_does_not_touch_other_repository(isolated_git_pair, monkeypatch):
    pair = isolated_git_pair
    _poison_git_environment(monkeypatch, pair)
    with pytest.raises(gitutil.GitError):
        promotion.ensure_release_checkout(pair.b, pair.b, "f" * 40)
    assert pair.git(pair.b, "rev-parse", "HEAD") == pair.b_head
    assert (pair.b / pair.tracked).read_bytes() == pair.b_contents
    _assert_a_unchanged(pair)



def test_promotion_rejects_ambient_git_overrides_before_side_effects(
    synthetic, isolated_git_pair, monkeypatch
):
    """Preflight must refuse contaminated Git env before logs/backups/tests.

    The real post-preflight checkout helper is independently tested above
    to operate safely with the same poisoned variables when called directly.
    """
    pair = isolated_git_pair
    _poison_git_environment(monkeypatch, pair)
    result = denied(synthetic)
    assert "inherited Git override environment" in result["error"]
    _assert_a_unchanged(pair)
    assert pair.git(pair.b, "rev-parse", "HEAD") == pair.b_head


def test_scoped_gitutil_isolation_ignores_config_and_index_overrides(
    isolated_git_pair, monkeypatch
):
    """Check the helper used by EVERY promoted fetch/checkout/status call."""
    pair = isolated_git_pair
    _poison_git_environment(monkeypatch, pair)
    assert gitutil.rev_parse(pair.b, "HEAD", isolated_env=True) == pair.b_head
    assert gitutil.worktree_state(pair.b, isolated_env=True).head == pair.b_head
    assert gitutil.worktree_state(pair.b, isolated_env=True).dirty is False
    _assert_a_unchanged(pair)

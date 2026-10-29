"""Real normal-entrypoint sessions, stores and processes; no runtime mocks."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = "Fictional moonberry lantern color is violet."
CORRECTED = "Fictional moonberry lantern color is amber."


@pytest.fixture
def app(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    for name in runpy.run_path(str(ROOT / "tests/test_canonical_windows_app.py"))["FILES"]:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return root


def environment(root):
    env = {k: v for k, v in os.environ.items()
           if k.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT"}}
    env.update(TEMP=str(root.parent), TMP=str(root.parent), PYTHONUTF8="1",
               PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    return env


def command(root):
    if os.name == "nt":
        # Real default Windows command, not a test-only entrypoint.
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(root / "Start Project Guardian.bat")]
    return [sys.executable, "-S", "-B", str(root / "elysia.py"),
            "--interactive", "--synthetic-store", "windows-pilot"]


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def run(root, lines):
    result = subprocess.run(command(root), input="\n".join(lines) + "\n", cwd=root,
        env=environment(root), text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def test_complete_runtime_delivery_and_restart(app):
    first = run(app, ["/status", "/calculate (12 * 8) - 20", f"/teach lantern | {ORIGINAL}",
        "moonberry lantern color", f"/correct lantern | {CORRECTED}",
        "/history lantern", "/research Skylark Composite", "/status", "/exit"])
    assert ORIGINAL in first.stdout and CORRECTED in first.stdout
    assert "Calculation: 76" in first.stdout
    assert "3 new sources preserved" in first.stdout
    assert "Shutdown complete. Named fictional store retained." in first.stdout
    statuses = [json.loads(x.split(": ", 1)[1]) for x in first.stdout.splitlines()
                if x.startswith("Runtime status: ")]
    assert len(statuses) == 2
    assert statuses[-1]["learned_revisions"] == 2
    assert statuses[-1]["running"] is True
    assert statuses[-1]["providers"] is False and statuses[-1]["autonomy"] is False
    before = snapshot(app)
    second = run(app, ["moonberry lantern color", "/history lantern",
        "Skylark Composite protective treatment", "/restart", "/status", "/exit"])
    assert "From synthetic memory: " + CORRECTED in second.stdout
    assert "Unresolved potential conflict" in second.stdout
    assert "Restart complete." in second.stdout
    assert snapshot(app) == before
    arithmetic = run(app, ["/calculate 0.1 + 0.2", "/calculate 1 / 0",
        "/calculate __import__('os').system('unsafe')", "/calculate 2 ** 100",
        "/calculate 1e-999999", "/exit"])
    assert "Calculation: 0.3" in arithmetic.stdout
    assert arithmetic.stdout.count("Calculation unavailable:") == 4
    assert len(arithmetic.stdout) < 5000
    assert snapshot(app) == before
    denied = run(app, [f"/teach absent | {CORRECTED}", f"/correct lantern | {ORIGINAL}",
        "/teach real | Private non-fictional data", "/autonomy enable", "/exit"])
    assert denied.stdout.count("Learning unavailable:") == 3
    assert "Unknown command." in denied.stdout
    assert snapshot(app) == before
    for result in (first, second, denied):
        evidence = json.loads(next(line.split(": ", 1)[1] for line in result.stdout.splitlines()
                                   if line.startswith("Security evidence: ")))
        assert evidence["denied_effects"] == []
        assert evidence["legacy_core_loaded"] is False
        assert evidence["running_after_shutdown"] is False
        assert evidence["restart_equal"] is True
    receipt = os.environ.get("ELYSIA_DELIVERY_RECEIPT")
    if receipt:
        Path(receipt).write_text(json.dumps({"platform": sys.platform,
            "argv": command(app), "runs": [{"stdout": r.stdout, "stderr": r.stderr,
            "exit_code": r.returncode} for r in (first, second, denied)],
            "restart_bytes_equal": True}, indent=2), encoding="utf-8")


def wait_ready(process, output):
    deadline = time.monotonic() + 15
    while "Ask Elysia:" not in output.read_text(encoding="utf-8"):
        assert process.poll() is None, output.read_text(encoding="utf-8")
        assert time.monotonic() < deadline, "readiness deadline expired"
        time.sleep(.02)


@pytest.mark.parametrize("stop", ["normal", "crash"])
def test_duplicate_launch_refused_and_owner_release(app, stop):
    # Kill only the directly owned Python child, never a PID discovered by name.
    # On Windows use Python directly for the forced-crash case to avoid killing
    # only a cmd.exe wrapper; the complete workflow above uses the real .bat.
    argv = [sys.executable, "-S", "-B", str(app / "elysia.py"),
            "--interactive", "--synthetic-store", "windows-pilot"]
    output = app.parent / "owner.txt"
    with output.open("w", encoding="utf-8") as handle:
        owner = subprocess.Popen(argv, cwd=app, env=environment(app), stdin=subprocess.PIPE,
            stdout=handle, stderr=handle, text=True)
        try:
            wait_ready(owner, output)
            before = snapshot(app)
            loser = subprocess.run(argv, input="/exit\n", cwd=app, env=environment(app),
                capture_output=True, text=True, timeout=10)
            assert loser.returncode == 2, loser.stdout + loser.stderr
            assert "ownership unavailable" in loser.stderr.lower()
            assert snapshot(app) == before
            assert owner.poll() is None
            if stop == "normal":
                owner.communicate("/exit\n", timeout=10)
                assert owner.returncode == 0
            else:
                owner.kill()
                owner.communicate(timeout=10)
        finally:
            if owner.poll() is None:
                owner.kill()
                owner.communicate(timeout=5)
    reopened = run(app, ["/status", "/exit"])
    assert "Runtime status:" in reopened.stdout
    assert snapshot(app) == before


def test_corrupt_store_refused_without_reset(app):
    run(app, [f"/teach lantern | {ORIGINAL}", "/exit"])
    (app / ".synthetic-pilot-stores/windows-pilot/synthetic-learning.json").write_text("{")
    before = snapshot(app)
    result = subprocess.run(command(app), input="/exit\n", cwd=app, env=environment(app),
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert "Offline startup failed:" in result.stderr
    assert snapshot(app) == before


def test_uncertain_ownership_release_cannot_report_shutdown_success(app):
    code = '''from contextlib import contextmanager
import os, runpy, sys
import elysia_runtime_owner as owner
from project_guardian.local_ingestion.apply_transaction import ApplyTransactionError
name = '_windows_mutex' if os.name == 'nt' else '_posix_lock'
real = getattr(owner, name)
@contextmanager
def uncertain(*args, **kwargs):
    with real(*args, **kwargs):
        yield
    raise ApplyTransactionError('synthetic ownership release uncertain')
setattr(owner, name, uncertain)
sys.argv = ['elysia.py', '--interactive', '--synthetic-store', 'windows-pilot']
runpy.run_path('elysia.py', run_name='__main__')
'''
    result = subprocess.run([sys.executable, "-S", "-B", "-c", code], input="/exit\n",
        cwd=app, env=environment(app), capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert "ownership release uncertain" in result.stderr
    assert "Shutdown complete" not in result.stdout
    assert "Security evidence:" not in result.stdout
    assert "Shutdown complete" in run(app, ["/exit"]).stdout


def test_simultaneous_launches_choose_exactly_one_owner(app):
    # Release two already-created interpreters together into the real entrypoint.
    code = '''import runpy, sys
sys.stdin.readline()
sys.argv = ['elysia.py', '--interactive', '--synthetic-store', 'windows-pilot']
runpy.run_path('elysia.py', run_name='__main__')
'''
    outputs = [app.parent / f"race-{n}.txt" for n in range(2)]
    handles, processes = [], []
    try:
        for output in outputs:
            handle = output.open("w", encoding="utf-8")
            handles.append(handle)
            processes.append(subprocess.Popen([sys.executable, "-S", "-B", "-c", code],
                cwd=app, env=environment(app), stdin=subprocess.PIPE,
                stdout=handle, stderr=handle, text=True))
        for process in processes:
            process.stdin.write("go\n")
            process.stdin.flush()
        deadline = time.monotonic() + 15
        while True:
            texts = [p.read_text(encoding="utf-8") for p in outputs]
            winners = [n for n, text in enumerate(texts) if "Ask Elysia:" in text]
            losers = [n for n, p in enumerate(processes) if p.poll() == 2]
            if len(winners) == len(losers) == 1:
                break
            assert time.monotonic() < deadline, texts
            time.sleep(.02)
        assert winners[0] != losers[0]
        assert "ownership unavailable" in texts[losers[0]].lower()
        before = snapshot(app)
        processes[winners[0]].communicate("/exit\n", timeout=10)
        assert processes[winners[0]].returncode == 0
        assert snapshot(app) == before
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)
        for handle in handles:
            handle.close()
    assert "Runtime status:" in run(app, ["/status", "/exit"]).stdout

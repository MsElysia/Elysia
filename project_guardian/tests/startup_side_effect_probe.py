"""Manual bounded probe: disposable source/storage, network denied, graceful stop.

Run with the repository Python. Never copies operator memory or credentials.
Evidence stays in a new tmp/startup-boundary-* directory. Not a production mode.
"""
import hashlib
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


GUARD = r'''
import json, os, pathlib, socket, sys, threading, time, traceback
ROOT = pathlib.Path(os.environ["BOUNDARY_PROBE_ROOT"]).resolve()
EVENTS = ROOT / "probe_events.jsonl"
bound_sockets = []
runtime = [pathlib.Path(sys.base_prefix).resolve(), pathlib.Path(sys.prefix).resolve()]
def inside(path, root):
    try:
        pathlib.Path(path).resolve().relative_to(root)
        return True
    except (ValueError, TypeError, OSError):
        return False
def record(kind, detail):
    with open(EVENTS, "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"kind": kind, "detail": detail}) + "\n")
def audit(event, args):
    if event == "open":
        path, mode, flags = args
        if isinstance(path, int):
            return
        if str(path).lower() == os.devnull.lower():
            return
        writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        if not inside(path, ROOT) and (writing or not any(inside(path, p) for p in runtime)):
            raise PermissionError("probe file boundary")
    elif event in ("os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime", "sqlite3.connect"):
        if not inside(args[0], ROOT):
            raise PermissionError("probe write boundary")
    elif event in ("os.rename", "os.link", "os.symlink"):
        if not all(inside(p, ROOT) for p in args[:2]):
            raise PermissionError("probe move boundary")
    elif event in ("subprocess.Popen", "os.system", "os.startfile", "os.startfile/2"):
        record("blocked_process", event)
        raise PermissionError("probe forbids external process execution")
    elif event == "socket.bind":
        if args[1][0] not in ("127.0.0.1", "::1"):
            raise OSError("probe permits only loopback listeners")
        bound_sockets.append(args[0])
    elif event == "socket.getaddrinfo" and args[0] in ("127.0.0.1", "::1"):
        return  # Numeric loopback resolution sends no provider request.
    elif event == "socket.connect":
        for listener in bound_sockets:
            try:
                if listener.getsockname() == args[1]:
                    return  # Only this process's listeners / asyncio socketpairs.
            except OSError:
                pass
        record("blocked_network", {"event": event, "stack": traceback.format_stack(limit=16)})
        raise OSError("probe network denied")
    elif event in ("socket.getaddrinfo", "socket.sendto", "socket.gethostbyname"):
        record("blocked_network", {"event": event, "stack": traceback.format_stack(limit=9)})
        raise OSError("probe network denied")
sys.addaudithook(audit)
heartbeat_complete = threading.Event()
def profile_heartbeat(frame, event, arg):
    # Observe the real first beat at its sleep boundary, without replacing work.
    if frame.f_code.co_name != "_beat" or not frame.f_code.co_filename.endswith("monitoring.py"):
        return
    beat = frame.f_locals.get("self")
    if event == "call" and os.environ.get("BOUNDARY_SCENARIO") == "degraded":
        # Seed the reported operational condition, not a fake vector backend.
        # Detection, finding application and memory remain real implementations.
        guardian = beat.system_monitor.guardian
        original_state = guardian.get_startup_operational_state
        def degraded_state():
            return dict(original_state(), vector_degraded=True, vector_rebuild_pending=True)
        guardian.get_startup_operational_state = degraded_state
        record("seeded_vector_state", "degraded=True, rebuild_pending=True")
    if event == "c_call" and arg is time.sleep and not heartbeat_complete.is_set():
        guardian = getattr(beat.system_monitor, "guardian", None)
        record("first_heartbeat_complete", getattr(guardian, "_adversarial_registry", {}))
        record("active_memory", {
            "path": guardian.config.get("memory_filepath"),
            "count": guardian.memory.get_memory_count(load_if_needed=True),
        })
        heartbeat_complete.set()
threading.setprofile(profile_heartbeat)
def watch():
    log = ROOT / "elysia_unified.log"
    previous = len(log.read_text(encoding="utf-8", errors="replace")) if log.exists() else 0
    deadline = time.monotonic() + 50
    while time.monotonic() < deadline:
        if heartbeat_complete.is_set() and log.exists() and "Unified Elysia System is running" in log.read_text(encoding="utf-8", errors="replace")[previous:]:
            time.sleep(0.3)
            main = sys.modules.get("__main__")
            if hasattr(main, "request_main_shutdown"):
                record("graceful_stop", "ready")
                main.request_main_shutdown("isolated side-effect probe")
                return
        time.sleep(0.1)
    record("probe_timeout", "readiness not reached")
threading.Thread(target=watch, daemon=True).start()
record("guard_active", "network, external processes and out-of-copy writes denied")
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=("clean", "errors", "degraded"), default="clean")
    parser.add_argument("--cycles", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    (repo / "tmp").mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="startup-boundary-", dir=repo / "tmp"))
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=repo).decode().split("\0")
    for name in tracked:
        path = Path(name)
        if not name or any(word in name.lower() for word in ("api_keys", "api keys", "credential", "secret")):
            continue
        if name == "pytest.ini" or path.suffix in {".py", ".html", ".js", ".css"} or (name.startswith("config/") and path.suffix == ".json"):
            dest = root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo / path, dest)
    # Include focused tests before they have been committed.
    for name in ("test_startup_maintenance_boundary.py", "test_startup_diagnostic_routing.py", "test_monitoring_adversarial_boundary.py"):
        shutil.copy2(Path(__file__).with_name(name), root / "project_guardian" / "tests" / name)
    profile = root / "profile"
    local = profile / "AppData" / "Local"
    # Match external_storage's platform fallback; otherwise Linux checks an
    # unused Windows fixture instead of the memory opened by real startup.
    memory_dir = local / "ElysiaGuardian" / "memory" if os.name == "nt" else profile / ".elysia_guardian" / "memory"
    memory = memory_dir / "guardian_memory.json"
    memory.parent.mkdir(parents=True)
    seed = [{"time": "2020-01-01", "thought": f"synthetic-source-{i}",
             "category": "fixture", "priority": 0.5, "metadata": {"source_id": i}}
            for i in range(4200)]
    if args.scenario != "clean":
        for i, row in enumerate(seed):
            row["category"] = ("user", "learning", "system", "monitoring")[i % 4]
        for row in seed[-2:]:
            row.update(category="error", thought="[Error] Synthetic connection failed")
    memory.write_text(json.dumps(seed), encoding="utf-8")
    before = memory.read_bytes()
    (root / "synthetic_before.json").write_bytes(before)
    guard = root / "probe_guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(GUARD, encoding="utf-8")
    env = dict(os.environ)
    for name in list(env):
        if any(word in name.upper() for word in ("API_KEY", "ACCESS_TOKEN", "SECRET", "PASSWORD")) or name.startswith("ELYSIA_"):
            env.pop(name)
    env.update(BOUNDARY_PROBE_ROOT=str(root), PYTHONPATH=str(guard),
               BOUNDARY_SCENARIO=args.scenario,
               USERPROFILE=str(profile), HOME=str(profile), LOCALAPPDATA=str(local),
               APPDATA=str(profile / "AppData" / "Roaming"), TMP=str(root / "temp"),
               TEMP=str(root / "temp"), PYTHONDONTWRITEBYTECODE="1",
               ELYSIA_STATUS_PORT="18888", PYTHONIOENCODING="utf-8")
    (root / "temp").mkdir()
    autonomy = root / "config" / "autonomy.json"
    auto_before = autonomy.read_bytes()
    assert json.loads(auto_before)["enabled"] is False
    results = []
    for cycle in range(1, args.cycles + 1):
        results.append(run_cycle(root, env, memory, before, seed, autonomy, auto_before, cycle, args.scenario))
    result = {"root": str(root), "scenario": args.scenario, "cycles": results,
              "memory_boundary_pass": all(r["memory_boundary_pass"] for r in results)}
    (root / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["memory_boundary_pass"] else 1


def run_cycle(root, env, memory, before, seed, autonomy, auto_before, cycle, scenario):
    stdout, stderr = root / f"stdout-{cycle}.txt", root / f"stderr-{cycle}.txt"
    events_path = root / "probe_events.jsonl"
    event_offset = len(events_path.read_text(encoding="utf-8")) if events_path.exists() else 0
    with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
        child = subprocess.Popen([sys.executable, "-u", "elysia.py"], cwd=root, env=env, stdout=out, stderr=err)
        try:
            code = child.wait(timeout=60)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
            code = "forced_timeout"
    after = memory.read_bytes()
    rows = json.loads(after)
    logs = stdout.read_text(encoding="utf-8", errors="replace") + stderr.read_text(encoding="utf-8", errors="replace")
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8")[event_offset:].splitlines()]
    beats = [e for e in events if e["kind"] == "first_heartbeat_complete"]
    active = [e["detail"] for e in events if e["kind"] == "active_memory"]
    types = {f["type"] for e in beats for f in e["detail"].get("findings_by_id", {}).values()}
    expected = set() if scenario == "clean" else {"repeated_failure"}
    if scenario == "degraded":
        expected.add("degraded_vector_state")
    result = {"cycle": cycle, "exit": code,
              "first_heartbeat_complete": bool(beats),
              "heartbeat_error": "[Heartbeat] Error:" in logs,
              "adversarial_task_completion_logged": "task_completed_unverified" in logs,
              "registry_types": sorted(types),
              "expected_findings_in_registry_and_logs": expected <= types and all(f"[Adversarial Finding] {t}:" in logs for t in expected),
              "ready": "Unified Elysia System is running" in logs,
              "guardian_ready": "Guardian Core initialized (singleton)" in logs,
              "startup_success_with_warnings": "Status: SUCCESS_WITH_WARNINGS" in logs,
              "goodbye": "Goodbye!" in logs,
              "consolidation_logged": "Memory consolidation:" in logs,
              "before_count": len(seed), "after_count": len(rows),
              "source_records_preserved": all(row in rows for row in seed),
              "byte_unchanged": before == after,
              "seeded_memory_is_active": bool(active) and all(
                  item.get("path") and Path(item["path"]).resolve() == memory.resolve()
                  and item.get("count") == len(seed) for item in active
              ),
              "before_sha256": hashlib.sha256(before).hexdigest(),
              "after_sha256": hashlib.sha256(after).hexdigest(),
              "autonomy_unchanged": auto_before == autonomy.read_bytes()}
    result["memory_boundary_pass"] = (
        code == 0 and result["guardian_ready"] and result["ready"] and result["goodbye"]
        and result["byte_unchanged"] and result["before_count"] == result["after_count"]
        and result["seeded_memory_is_active"]
        and not result["consolidation_logged"] and result["autonomy_unchanged"]
        and result["first_heartbeat_complete"] and result["expected_findings_in_registry_and_logs"]
        and not result["heartbeat_error"]
        and (scenario != "degraded" or result["adversarial_task_completion_logged"])
    )
    return result


if __name__ == "__main__":
    raise SystemExit(main())

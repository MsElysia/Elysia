"""Run the complete applicable restricted Windows pilot suite, offline.

Uses the existing development Python/pytest environment. No dependency install,
provider activation or repository-wide legacy conftest is performed. This is
the main-based runtime closure suite, not a claim of full historical CI.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "tests/test_delivery_runtime.py",
    "tests/test_restricted_windows_startup.py",
    "tests/test_synthetic_learning_isolated.py",
    "tests/test_research_pilot_launcher.py",
    "tests/test_canonical_windows_app.py",
    "tests/test_final_consolidation.py",
    "tests/test_main_based_boundary.py",
    "project_guardian/tests/test_memory_intelligence_ingestion.py",
    "project_guardian/tests/test_chatgpt_apply_transaction.py",
    "project_guardian/tests/test_windows_apply_lock.py",
    "project_guardian/tests/test_offline_research_recovery.py",
    "tests/test_orchestration_serial.py",
    "tests/test_orchestration_parallel.py",
    "tests/test_orchestration_validator.py",
    "tests/test_router_rules.py",
    "tests/test_router_telemetry_adapt.py",
)

# Execute new chat contracts in their own pytest processes. In particular,
# browser tests install an irreversible audit hook, while the real HTTP probe
# needs a narrowly scoped local-only fixture listener.
CHAT_TESTS = (
    "tests/test_local_memory_chat.py",
    "tests/test_local_chat_integration.py",
    "tests/test_local_context_bundle_contract.py",
    "tests/test_synthetic_memory_path_alias.py",
    "tests/test_windows_local_chat_runner.py",
)
BROWSER_TESTS = ("tests/test_restricted_browser_bridge.py", "tests/test_browser_worker_path_alias.py")
HTTP_TESTS = ("tests/test_local_chat_http.py",)

# Windows asyncio needs a local stdlib socketpair for its event-loop self-pipe.
# Permit only that exact installed function's own ephemeral loopback listener.
# The application's stricter process guard remains unchanged and uses -S.
TEST_GUARD = '''import os,sys,socket
pair_code=socket.socketpair.__code__
# Capture test-only allowance once; changing os.environ within a strict test
# must never turn its deny-network process into a loopback-capable process.
allow_http_fixture=os.environ.get("ELYSIA_CHAT_HTTP_FIXTURE")=="1"
def audit(event,args):
    if event=="import" and args[0]=="project_guardian.api_key_manager":
        raise RuntimeError("offline tests refuse credential discovery")
    if event in {"socket.bind","socket.connect","socket.getaddrinfo"}:
        frame=sys._getframe(1)
        while frame and frame.f_code is not pair_code: frame=frame.f_back
        allowed=False
        if frame and event in {"socket.bind","socket.connect"}:
            listener=frame.f_locals.get("lsock")
            address=args[1]
            if event=="socket.bind": allowed=args[0] is listener and address==("127.0.0.1",0)
            elif listener is not None: allowed=address==listener.getsockname() and address[0]=="127.0.0.1"
        # Only the separate HTTP-fixture pytest subprocess may communicate
        # with numeric IPv4 loopback. No DNS names, non-loopback hosts,
        # wildcard listeners, or non-ephemeral fixture binds are accepted.
        if allow_http_fixture:
            address=args[1] if event!="socket.getaddrinfo" else None
            if event=="socket.getaddrinfo":
                host,port=args[:2]
                allowed=host=="127.0.0.1" and type(port) is int and 0<=port<65536
            elif event=="socket.bind":
                allowed=address==("127.0.0.1",0)
            elif event=="socket.connect":
                allowed=(type(address) is tuple and len(address)==2
                         and address[0]=="127.0.0.1"
                         and type(address[1]) is int and 0<address[1]<65536)
        if not allowed: raise RuntimeError("offline tests refuse non-socketpair network: "+event)
    if event=="open" and not isinstance(args[0],int):
        name=os.path.normcase(os.path.abspath(os.fsdecode(args[0])))
        parts=name.replace("\\\\","/").split("/")
        if (name==os.path.normcase(os.environ["ELYSIA_FORBIDDEN_LEARNING_CONFIG"])
                or "api keys" in parts or os.path.basename(name) in {"api_keys.json","api_key.json"}):
            raise RuntimeError("legacy credential configuration refused")
sys.addaudithook(audit)
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, help="New empty local directory for synthetic transcripts")
    parser.add_argument("--chat-only", action="store_true",
                        help="Run only isolated chat, browser and synthetic loopback HTTP contracts")
    args = parser.parse_args()
    receipts = None
    if args.evidence_dir:
        receipts = args.evidence_dir.resolve()
        receipts.mkdir(parents=True, exist_ok=False)
    # A short existing TEMP location avoids Windows MAX_PATH failures in deeply
    # nested transaction fixtures; the caller may set TEMP to local scratch.
    with tempfile.TemporaryDirectory(prefix="elysia-tests-") as directory:
        # Deliberately retain Windows' original TEMP spelling here. The
        # synthetic memory store must normalize its own transaction identity.
        scratch = Path(directory)
        guard = scratch / "guard"
        guard.mkdir()
        (guard / "sitecustomize.py").write_text(TEST_GUARD, encoding="utf-8")
        env = {k: v for k, v in os.environ.items()
               if k.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT"}}
        env.update(TEMP=str(scratch), TMP=str(scratch), PYTHONUTF8="1",
                   PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
                   PYTHONPATH=os.pathsep.join((str(guard), str(ROOT), str(ROOT / "tests"))),
                   ELYSIA_FORBIDDEN_LEARNING_CONFIG=str(ROOT / "config/auto_learning.json"),
                   ELYSIA_ORCH_TELEMETRY_MIRROR_SEC="0", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
        if receipts:
            env.update(ELYSIA_FINAL_RECEIPTS=str(receipts),
                       ELYSIA_CANONICAL_RECEIPT=str(receipts / "combined.json"),
                       ELYSIA_TEST_RECEIPT=str(receipts / "learning.json"),
                       ELYSIA_RESEARCH_RECEIPT=str(receipts / "research.txt"))
        stages = (
            ("Preserved restricted Windows suite", TESTS, False),
            ("Local memory/model contracts", CHAT_TESTS, False),
            ("Browser authorization boundary", BROWSER_TESTS, False),
            ("Synthetic loopback HTTP application", HTTP_TESTS, True),
        )
        if args.chat_only:
            stages = stages[1:]
        for index, (label, files, loopback) in enumerate(stages):
            stage_env = dict(env)
            if loopback:
                stage_env["ELYSIA_CHAT_HTTP_FIXTURE"] = "1"
            command = [sys.executable, "-B", "-m", "pytest", "--noconftest", "-q", "-rs",
                       "-p", "no:cacheprovider", *files,
                       "--basetemp=" + str(scratch / ("pytest-" + str(index)))]
            print("Stage: " + label, flush=True)
            print("Command: " + subprocess.list2cmdline(command), flush=True)
            result = subprocess.run(command, cwd=ROOT, env=stage_env)
            if result.returncode != 0:
                print("FAILED stage: " + label + " (exit " + str(result.returncode) + ")", flush=True)
                return result.returncode
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

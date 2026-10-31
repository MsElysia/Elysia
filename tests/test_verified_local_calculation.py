"""Behavioral integration: real bounded calculator, primary audit, queue/objective/value."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
if "project_guardian" not in sys.modules:
    package = types.ModuleType("project_guardian")
    package.__path__ = [str(ROOT / "project_guardian")]
    sys.modules["project_guardian"] = package

from project_guardian import verified_local_calculation as lane


def approve(prompt):
    return "AUTHORIZE " + re.search(r"request ([0-9a-f]{32});", prompt).group(1)


def prepare(session, **changes):
    args = dict(rate="35.50", painters=3, days=2, hours_per_day=8)
    args.update(changes)
    return session.prepare(**args)


def test_authorized_end_to_end_and_restart(tmp_path):
    with lane.OperatorCalculationSession(tmp_path, confirm=approve) as session:
        request = prepare(session)
        grant = session.authorize(request)
        result = session.execute(request, grant)
        assert result["verification_status"] == "verified"
        assert result["evidence"]["result"] == "1704"
        assert result["effect_kind"] == "computation"
        assert not result["durable_effect_verified"] and not result["external_effect_verified"]
        assert result["audit_persisted"] is True
        assert result["value_verified"] is True
        assert result["value_type"] == "operator_support"
        task = session.queue.get_by_id(request.task_id)
        assert task["status"] == "completed"
        assert task["last_outcome"] == "execution_succeeded_value"
        objective = session.objectives.get(result["objective_id"])
        assert objective["status"] == "completed"
        assert objective["progress"] == .12
        assert objective["execution_completed"] is True
        assert task["execution_evidence"] == objective["last_execution"]["execution_evidence"]
        before = session.journal_path.read_bytes()
    for _ in range(2):
        with lane.OperatorCalculationSession(tmp_path, confirm=approve) as session:
            restored = session.outcomes[request.task_id]
            assert restored == result
            assert session.queue.get_by_id(request.task_id)["verification_status"] == "verified"
            assert session.objectives.get(result["objective_id"])["progress"] == .12
            assert session.journal_path.read_bytes() == before
            with pytest.raises(lane.CalculationBoundaryError):
                session.execute(request, grant)


@pytest.mark.parametrize("kind", ["denied", "forged", "wrong_request", "wrong_capability", "expired", "receipt"])
def test_unauthorized_never_calls_tool_or_verifies(tmp_path, monkeypatch, kind):
    now = [1.0]
    with lane.OperatorCalculationSession(tmp_path, confirm=(lambda p: "no") if kind == "denied" else approve,
                                         clock=lambda: now[0]) as session:
        request = prepare(session)
        grant = session.authorize(prepare(session) if kind == "wrong_request" else request)
        if kind == "forged": grant = object()
        if kind == "receipt": grant = {"success": True, "operator_authorized": True, "task_id": request.task_id}
        if kind == "expired": now[0] = 122
        monkeypatch.setattr(lane, "calculate_local", lambda *a: pytest.fail("unauthorized calculator call"))
        result = session.execute(request, grant, selected_capability="tool:advertised" if kind == "wrong_capability" else lane.CAPABILITY)
        assert result["verification_status"] == "blocked"
        assert not result["execution_attempted"] and not result["value_verified"]
        assert session.objectives.get(result["objective_id"])["progress"] == 0
    with lane.OperatorCalculationSession(tmp_path) as restarted:
        assert restarted.outcomes[request.task_id]["verification_status"] == "blocked"


@pytest.mark.parametrize("bad", ["999", {"success": True, "verified": True, "result": "1704"}, None])
def test_false_report_and_unrelated_writer_stay_partial(tmp_path, monkeypatch, bad):
    with lane.OperatorCalculationSession(tmp_path, confirm=approve) as session:
        request = prepare(session)
        def fake(expression):
            from threading import Thread
            writer = Thread(target=lambda: (tmp_path / "unrelated.txt").write_text("healthy"))
            writer.start(); writer.join()
            return bad
        monkeypatch.setattr(lane, "calculate_local", fake)
        result = session.execute(request, session.authorize(request))
        assert result["verification_status"] == "partial"
        assert result["execution_outcome"] == "partial"
        assert not result["value_verified"]
        task = session.queue.get_by_id(request.task_id)
        assert task["status"] == "partial"
        assert task["last_outcome"] == "execution_partial_no_value"
        assert session.objectives.get(result["objective_id"])["progress"] == 0


@pytest.mark.parametrize("interrupted", [False, True])
def test_failure_or_interruption_never_verifies(tmp_path, monkeypatch, interrupted):
    with lane.OperatorCalculationSession(tmp_path, confirm=approve) as session:
        request = prepare(session)
        def broken(*a):
            raise KeyboardInterrupt() if interrupted else ValueError("synthetic failure")
        monkeypatch.setattr(lane, "calculate_local", broken)
        result = session.execute(request, session.authorize(request))
        assert result["verification_status"] == "failed"
        assert result["execution_reason"] == ("interrupted" if interrupted else "calculator_failed")
        assert not result["value_verified"]
    with lane.OperatorCalculationSession(tmp_path) as session:
        assert session.outcomes[request.task_id]["verification_status"] == "failed"


def test_replay_consumed_and_deserialized_grants_are_rejected(tmp_path):
    with lane.OperatorCalculationSession(tmp_path, confirm=approve) as session:
        request = prepare(session)
        grant = session.authorize(request)
        session.execute(request, grant)
        with pytest.raises(lane.CalculationBoundaryError): session.execute(request, grant)
        other = prepare(session)
        assert session.execute(other, grant)["verification_status"] == "blocked"
        copied = lane.CalculationRequest(**lane.asdict(prepare(session)))
        with pytest.raises(lane.CalculationBoundaryError): session.authorize(copied)


@pytest.mark.parametrize("fail_on", [1, 2])
def test_primary_failure_does_not_publish_verified_outcome(tmp_path, monkeypatch, fail_on):
    with lane.OperatorCalculationSession(tmp_path, confirm=approve) as session:
        request = prepare(session)
        calls = []
        real_read = session._read_memory
        real_calculator = lane.calculate_local
        def called(expression):
            calls.append(expression)
            return real_calculator(expression)
        monkeypatch.setattr(lane, "calculate_local", called)
        writes = [0]
        real_append = session._append
        def append(event):
            writes[0] += 1
            if writes[0] == fail_on:
                monkeypatch.setattr(session.memory, "_write_atomic", lambda *a: (_ for _ in ()).throw(OSError("full")))
            real_append(event)
        monkeypatch.setattr(session, "_append", append)
        monkeypatch.setattr("time.sleep", lambda *a: None)
        with pytest.raises(lane.CalculationPersistenceError): session.execute(request, session.authorize(request))
        assert len(calls) == (0 if fail_on == 1 else 1)
        assert request.task_id not in session.outcomes or session.outcomes[request.task_id]["verification_status"] != "verified"
    with lane.OperatorCalculationSession(tmp_path) as session:
        assert request.task_id not in session.outcomes or session.outcomes[request.task_id]["verification_status"] == "attempted"


def test_dry_run_and_concurrent_session(tmp_path, monkeypatch):
    with lane.OperatorCalculationSession(tmp_path, confirm=approve) as session:
        with pytest.raises(OSError): lane.OperatorCalculationSession(tmp_path)
        request = prepare(session)
        monkeypatch.setattr(lane, "calculate_local", lambda *a: pytest.fail("dry calculator call"))
        result = session.execute(request, session.authorize(request), dry_run=True)
        assert result["execution_outcome"] == "partial"
        assert not result["execution_attempted"]


@pytest.mark.parametrize("changes", [{"rate": "035.50"}, {"rate": "__import__('os')"}, {"painters": True},
                                     {"days": 367}, {"hours_per_day": 0}, {"rate": "0"}])
def test_arguments_cannot_expand_capability_or_authority(tmp_path, changes):
    with lane.OperatorCalculationSession(tmp_path) as session:
        with pytest.raises(lane.CalculationBoundaryError): prepare(session, **changes)


def test_replayed_or_altered_persisted_result_is_refused(tmp_path):
    with lane.OperatorCalculationSession(tmp_path, confirm=approve) as session:
        request = prepare(session)
        session.execute(request, session.authorize(request))
        path = session.journal_path
    original = json.loads(path.read_text())
    for mutation in ("duplicate", "result", "identity", "effect"):
        rows = json.loads(json.dumps(original))
        if mutation == "duplicate": rows.append(rows[-1])
        else:
            field = {"result": "result", "identity": "task_id", "effect": "effect_kind"}[mutation]
            rows[-1]["metadata"]["calculation_v1"][field] = "forged"
        path.write_text(json.dumps(rows))
        with pytest.raises(lane.CalculationPersistenceError): lane.OperatorCalculationSession(tmp_path)
    path.write_text(json.dumps(original))


def test_linked_journal_refused_before_execution(tmp_path):
    with lane.OperatorCalculationSession(tmp_path, confirm=approve) as session:
        request = prepare(session)
        grant = session.authorize(request)
        outside = tmp_path / "outside.json"
        outside.write_text("[]")
        try: session.journal_path.symlink_to(outside)
        except OSError:
            if sys.platform != "win32":
                raise
            # Junctions exercise Windows path refusal without elevated symlink privilege.
            junction = tmp_path / "workspace-junction"
            target = tmp_path / "junction-target"
            target.mkdir()
            created = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(target)],
                                     capture_output=True, text=True)
            assert created.returncode == 0, created.stderr
            with pytest.raises(lane.CalculationBoundaryError): lane.OperatorCalculationSession(junction)
            assert list(target.iterdir()) == []
            return
        with pytest.raises(lane.CalculationBoundaryError): session.execute(request, grant)
        assert outside.read_text() == "[]"


def test_reused_calculator_function_matches_exact_source():
    import ast
    source = subprocess.check_output(["git", "show", "4eea564b0de97c124aea7475527e7ab542249ffc:elysia_offline.py"], cwd=ROOT).decode()
    local = (ROOT / "project_guardian/local_calculator.py").read_text()
    functions = lambda text: [ast.dump(n, include_attributes=False) for n in ast.parse(text).body
                              if isinstance(n, ast.FunctionDef) and n.name == "calculate_local"]
    assert functions(source) == functions(local)


def test_other_writer_cannot_replace_primary_evidence(tmp_path):
    with lane.OperatorCalculationSession(tmp_path, confirm=approve) as session:
        request = prepare(session)
        grant = session.authorize(request)
        session.journal_path.write_text("unrelated original bytes")
        with pytest.raises(lane.CalculationPersistenceError): session.execute(request, grant)
        assert session.journal_path.read_text() == "unrelated original bytes"


def test_storage_directory_substitution_refused(tmp_path):
    with lane.OperatorCalculationSession(tmp_path, confirm=approve) as session:
        request = prepare(session)
        grant = session.authorize(request)
        moved = tmp_path / "preserved-directory"
        try: session.root.rename(moved)
        except OSError:  # Windows may lock the containing directory while session.lock is open.
            return
        session.root.mkdir()
        with pytest.raises(lane.CalculationBoundaryError): session.execute(request, grant)


def test_process_death_restores_attempt_without_rerun(tmp_path):
    code = '''
import os,re,sys
from project_guardian import verified_local_calculation as lane
def confirm(prompt):
    return "AUTHORIZE " + re.search(r"request ([0-9a-f]{32});",prompt).group(1)
with lane.OperatorCalculationSession(sys.argv[1],confirm=confirm) as session:
    request=session.prepare(rate="35.50",painters=3,days=2,hours_per_day=8)
    lane.calculate_local=lambda expression: os._exit(17)
    session.execute(request,session.authorize(request))
'''
    proc = subprocess.run([sys.executable, "-B", "-c", code, str(tmp_path)], cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 17, proc.stderr
    with lane.OperatorCalculationSession(tmp_path) as restarted:
        assert len(restarted.outcomes) == 1
        result = next(iter(restarted.outcomes.values()))
        assert result["verification_status"] == "attempted"
        assert result["execution_outcome"] == "partial"
        assert not result["value_verified"]
        assert restarted.queue.get_by_id(result["task_id"])["status"] == "partial"


def test_real_operator_cli_authorize_and_fresh_process_reload(tmp_path):
    import threading
    command = [sys.executable, "-B", "scripts/run_verified_calculation.py", "--workspace", str(tmp_path),
               "--rate", "35.50", "--painters", "3", "--days", "2", "--hours-per-day", "8"]
    proc = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, bufsize=1)
    output = []
    def operator():
        current = ""
        while True:
            char = proc.stdout.read(1)
            if not char: break
            output.append(char)
            current += char
            if current.endswith("authorize this one request: "):
                request_id = re.search(r"request ([0-9a-f]{32});", current).group(1)
                proc.stdin.write("AUTHORIZE " + request_id + "\n")
                proc.stdin.flush()
    thread = threading.Thread(target=operator, daemon=True)
    thread.start()
    try:
        code = proc.wait(timeout=20)
        thread.join(timeout=2)
        assert code == 0, proc.stderr.read()
    finally:
        if proc.poll() is None: proc.kill(); proc.wait()
    status = subprocess.run([sys.executable, "-B", "scripts/run_verified_calculation.py", "--workspace",
                             str(tmp_path), "--status"], cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert status.returncode == 0, status.stderr
    records = json.loads(status.stdout.splitlines()[-1])
    assert len(records) == 1
    assert records[0]["evidence"]["result"] == "1704"
    assert records[0]["verification_status"] == "verified"



def test_lane_never_publishes_to_optional_usb_mirror(tmp_path, monkeypatch):
    mirror = types.ModuleType("memory_storage_config")
    calls = []
    mirror.notify_usb_persist_mirror = lambda *a: calls.append(a)
    monkeypatch.setitem(sys.modules, "memory_storage_config", mirror)
    with lane.OperatorCalculationSession(tmp_path, confirm=approve) as session:
        request = prepare(session)
        assert session.execute(request, session.authorize(request))["verification_status"] == "verified"
    assert calls == []

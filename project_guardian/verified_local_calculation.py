"""Manual, host-authorized calculator lane. No model or self-task authority.

The host owns this session, its confirmation channel and its storage directory.
Opaque grants are process-local; JSON, recommendations and disk records cannot
mint grants. Local journal files, like other application state, require a trusted
OS account/filesystem. This is not a sandbox against code in the host process.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

from .local_calculator import calculate_local
from .memory import MemoryCore
from .self_task_queue import SelfTaskQueue
from .self_task_objectives import ObjectiveStore
from .self_task_value_verification import evaluate_execution_value

CAPABILITY = "calculator.labor"
ARCHETYPE = "execute_local_calculation"


class CalculationBoundaryError(ValueError):
    pass


class CalculationPersistenceError(OSError):
    pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class CalculationRequest:
    task_id: str
    request_id: str
    rate: str
    painters: int
    days: int
    hours_per_day: int

    def inputs(self):
        return {key: getattr(self, key) for key in ("rate", "painters", "days", "hours_per_day")}


def _expected(inputs):
    """Independent oracle: integer cents, no AST or calculator/Decimal reuse."""
    if set(inputs) != {"rate", "painters", "days", "hours_per_day"}:
        raise CalculationBoundaryError("invalid calculator fields")
    rate = inputs["rate"]
    if type(rate) is not str or re.fullmatch(r"(?:0|[1-9][0-9]{0,3})(?:\.[0-9]{1,2})?", rate) is None:
        raise CalculationBoundaryError("invalid USD hourly rate")
    whole, _, fraction = rate.partition(".")
    cents = int(whole) * 100 + int(fraction.ljust(2, "0") or "0")
    if cents == 0:
        raise CalculationBoundaryError("hourly rate must be positive")
    for key, limit in (("painters", 100), ("days", 366), ("hours_per_day", 24)):
        value = inputs[key]
        if type(value) is not int or not 1 <= value <= limit:
            raise CalculationBoundaryError("invalid calculator quantity: " + key)
        cents *= value
    text = f"{cents // 100}.{cents % 100:02d}"
    return text.rstrip("0").rstrip(".")


class OperatorCalculationSession:
    """One manual operator channel and one exclusively owned synthetic journal.

    `confirm` is a trusted UI/terminal function returning operator-entered text,
    never a model/tool callback. It must show the supplied exact request/challenge.
    No capability result, receipt or path is accepted as an execution argument.
    """

    def __init__(self, workspace, *, confirm=input, clock=time.monotonic):
        self.root = Path(workspace).absolute() / "verified-calculations-v1"
        self.confirm = confirm
        self.clock = clock
        self._requests = {}
        self._grants = {}
        self._closed = False
        self._lock = None
        self._check_paths()
        self.root.mkdir(parents=True, exist_ok=True)
        self._resolved_root = self.root.resolve()
        self._root_identity = (self.root.stat().st_dev, self.root.stat().st_ino)
        self.journal_path = self.root / "events.json"
        self._check_paths()
        # Advisory OS lock is released even on process death. Do not unlink it.
        self._lock = open(self.root / "session.lock", "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                if self._lock.seek(0, 2) == 0:
                    self._lock.write(b"0")
                    self._lock.flush()
                self._lock.seek(0)
                msvcrt.locking(self._lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.memory = self._read_memory()
            self._journal_digest = self._disk_digest()
            self._rebuild()
        except BaseException:
            self.close()
            raise

    def _check_paths(self):
        if self._closed:
            raise CalculationBoundaryError("session closed")
        for path in (self.root, *self.root.parents,
                     self.root / "events.json", self.root / "session.lock"):
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise CalculationBoundaryError("linked storage path refused")
        if hasattr(self, "_resolved_root") and self.root.resolve() != self._resolved_root:
            raise CalculationBoundaryError("storage path substituted")
        if hasattr(self, "_root_identity") and (self.root.stat().st_dev, self.root.stat().st_ino) != self._root_identity:
            raise CalculationBoundaryError("storage directory replaced")

    def _disk_digest(self):
        return hashlib.sha256(self.journal_path.read_bytes()).hexdigest() if self.journal_path.exists() else None

    def _read_memory(self):
        self._check_paths()
        memory = MemoryCore(filepath=str(self.journal_path), enable_timeline_logging=False,
                            enable_vector_search=False, enable_persist_mirror=False)
        if memory.last_load_error or memory.persistence_blocked:
            raise CalculationPersistenceError("journal unreadable; original evidence preserved")
        return memory

    def close(self):
        self._closed = True
        self._grants.clear()
        if self._lock is not None:
            self._lock.close()
            self._lock = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def prepare(self, *, rate, painters, days, hours_per_day):
        self._check_paths()
        inputs = dict(rate=rate, painters=painters, days=days, hours_per_day=hours_per_day)
        _expected(inputs)
        request = CalculationRequest("calc_" + uuid.uuid4().hex, uuid.uuid4().hex, **inputs)
        self._requests[request.task_id] = request
        return request

    def authorize(self, request, *, deadline=None):
        self._owned_request(request)
        challenge = "AUTHORIZE " + request.request_id
        description = (f"Task {request.task_id}; request {request.request_id}; {CAPABILITY}; "
                       f"USD {request.rate}/hour x {request.painters} painters x {request.days} days "
                       f"x {request.hours_per_day} hours/day. Computation only; no external effect.\n"
                       f"Type exactly '{challenge}' to authorize this one request: ")
        if self.confirm(description) != challenge:
            return None
        # Object identity, not a payload flag/token string, grants one dispatch.
        expires = self.clock() + 120
        if deadline is not None:
            expires = min(expires, deadline)
        if self.clock() >= expires:
            return None
        grant = object()
        self._grants[grant] = (request, expires)
        return grant

    def _owned_request(self, request):
        self._check_paths()
        if type(request) is not CalculationRequest or self._requests.get(request.task_id) is not request:
            raise CalculationBoundaryError("request was not prepared by this host session")
        if request.task_id in self.outcomes:
            raise CalculationBoundaryError("request already attempted; obtain new operator authorization")

    def _append(self, event):
        event = json.loads(_canonical(event))
        self._check_paths()
        if self._disk_digest() != self._journal_digest:
            raise CalculationPersistenceError("journal changed outside this session; evidence preserved")
        if self.memory.remember("Operator local calculation audit", category="operator_calculation",
                                priority=0.9, metadata={"calculation_v1": event}) is not True:
            raise CalculationPersistenceError("primary audit persistence failed")
        reloaded = self._read_memory()
        if not reloaded.memory_log or reloaded.memory_log[-1].get("metadata", {}).get("calculation_v1") != event:
            raise CalculationPersistenceError("audit reload mismatch")
        self.memory = reloaded
        self._journal_digest = self._disk_digest()
        self._rebuild()

    def execute(self, request, grant, *, selected_capability=CAPABILITY, dry_run=False):
        self._owned_request(request)
        try:
            issued = self._grants.pop(grant, None)
        except TypeError:
            issued = None
        authorized = bool(issued and issued[0] is request and self.clock() < issued[1]
                          and selected_capability == CAPABILITY)
        inputs = request.inputs()
        expected = _expected(inputs)
        # Establish task/capability/attempt/expected result BEFORE calling the tool.
        event = dict(task_id=request.task_id, request_id=request.request_id,
                     attempt_id=uuid.uuid4().hex, capability_id=CAPABILITY,
                     inputs=inputs, input_sha256=_digest(inputs), expected_result=expected,
                     operator_authorized=authorized, phase="finished", result=None,
                     verification_status="blocked", reason="operator_authorization_required",
                     effect_kind="computation", durable_effect_verified=False,
                     external_effect_verified=False, attempted=False)
        if not authorized:
            self._append(event)
            return self.outcomes[request.task_id]
        if dry_run:
            event.update(verification_status="partial", reason="dry_run_not_execution")
            self._append(event)
            return self.outcomes[request.task_id]
        event.update(phase="started", verification_status="attempted", reason="dispatch_started", attempted=True)
        self._append(event)  # Never execute without durable attempted state.
        expression = f"{request.rate} * {request.painters} * {request.days} * {request.hours_per_day}"
        try:
            result = calculate_local(expression)
        except (Exception, KeyboardInterrupt) as exc:
            event.update(phase="finished", verification_status="failed",
                         reason="interrupted" if isinstance(exc, KeyboardInterrupt) else "calculator_failed")
        else:
            # Success flags/dicts/receipts are not calculator results.
            matched = type(result) is str and result == expected
            event.update(phase="finished", result=result if type(result) is str else None,
                         verification_status="verified" if matched else "partial",
                         reason="independent_integer_cent_check" if matched else "calculator_result_mismatch")
        self._append(event)  # A return is verified only AFTER primary commit + reload.
        return self.outcomes[request.task_id]

    def read_outcomes(self):
        """Reload committed outcomes without restoring grants or invoking a tool."""
        self._check_paths()
        if self._disk_digest() != self._journal_digest:
            raise CalculationPersistenceError("journal changed outside this session; evidence preserved")
        self.memory = self._read_memory()
        self._rebuild()
        return json.loads(_canonical(list(self.outcomes.values())))

    def _rebuild(self):
        # These existing queue/objective algorithms are projections of the primary
        # audit log, not a second transaction. Replay cannot rerun the calculator
        # or increment objective progress twice. No global mission/autonomy hooks.
        latest = {}
        attempts = set()
        for row in self.memory.memory_log:
            event = row.get("metadata", {}).get("calculation_v1")
            if not isinstance(event, dict):
                raise CalculationPersistenceError("unexpected journal record")
            required = {"task_id", "request_id", "attempt_id", "capability_id", "inputs", "input_sha256",
                        "expected_result", "operator_authorized", "phase", "result", "verification_status",
                        "reason", "effect_kind", "durable_effect_verified", "external_effect_verified", "attempted"}
            if set(event) != required:
                raise CalculationPersistenceError("invalid journal fields")
            prior = latest.get(event["task_id"])
            try:
                expected = _expected(event["inputs"])
                valid = (event["capability_id"] == CAPABILITY and event["effect_kind"] == "computation"
                         and event["durable_effect_verified"] is False and event["external_effect_verified"] is False
                         and event["input_sha256"] == _digest(event["inputs"])
                         and event["expected_result"] == expected
                         and re.fullmatch(r"calc_[0-9a-f]{32}", event["task_id"])
                         and re.fullmatch(r"[0-9a-f]{32}", event["request_id"])
                         and re.fullmatch(r"[0-9a-f]{32}", event["attempt_id"]))
                valid = valid and type(event["operator_authorized"]) is bool and type(event["attempted"]) is bool
                if event["phase"] == "started":
                    valid = valid and (event["verification_status"] == "attempted"
                                       and event["operator_authorized"] is True and event["attempted"] is True
                                       and event["result"] is None and event["reason"] == "dispatch_started")
                elif event["verification_status"] == "blocked":
                    valid = valid and (prior is None and event["operator_authorized"] is False
                                       and event["attempted"] is False and event["result"] is None)
                elif event["verification_status"] == "partial" and event["reason"] == "dry_run_not_execution":
                    valid = valid and (prior is None and event["operator_authorized"] is True
                                       and event["attempted"] is False and event["result"] is None)
                else:
                    valid = valid and (prior is not None and event["operator_authorized"] is True
                                       and event["attempted"] is True
                                       and event["verification_status"] in {"verified", "failed", "partial"})
                if event["verification_status"] == "verified":
                    valid = valid and (event["result"] == expected and type(event["result"]) is str
                                      and event["operator_authorized"] is True and event["attempted"] is True
                                      and prior is not None and prior["phase"] == "started")
                if prior:
                    stable = set(required) - {"phase", "result", "verification_status", "reason"}
                    valid = valid and prior["phase"] == "started" and event["phase"] == "finished"
                    valid = valid and all(prior[k] == event[k] for k in stable)
                elif event["attempt_id"] in attempts:
                    valid = False
                valid = valid and event["phase"] in {"started", "finished"}
                valid = valid and event["verification_status"] in {"attempted", "partial", "failed", "blocked", "verified"}
            except (ValueError, TypeError, KeyError):
                valid = False
            if not valid:
                raise CalculationPersistenceError("invalid/replayed calculation evidence")
            attempts.add(event["attempt_id"])
            latest[event["task_id"]] = event
        self.queue = SelfTaskQueue(storage_path=self.root / "queue-view.json", in_memory=True)
        self.objectives = ObjectiveStore(storage_path=self.root / "objectives-view.json", in_memory=True)
        self.outcomes = {}
        for event in latest.values():
            verified = event["verification_status"] == "verified"
            status = event["verification_status"] if event["phase"] == "finished" else "attempted"
            outcome = dict(execution_attempted=event["attempted"],
                           execution_outcome="succeeded" if verified else "failed" if status in {"failed", "blocked"} else "partial",
                           verification_status=status, execution_reason=event["reason"],
                           execution_followup_needed=not verified, execution_artifact=None,
                           effect_kind="computation", durable_effect_verified=False, external_effect_verified=False)
            value = evaluate_execution_value(archetype=ARCHETYPE, adv_result={}, exec_result=outcome,
                                             artifact_path=None, execution_tier="strong", payload={})
            oid = self.objectives.create_lightweight(title="Authorized local calculation", goal="Return checked labor total")
            objective = self.objectives.get(oid)
            # Preserve an identity derived from the host task on every reload.
            oid = "objective_" + event["task_id"]
            objective["objective_id"] = oid
            objective["operator_ready"] = verified
            self.queue.enqueue(dict(task_id=event["task_id"], archetype=ARCHETYPE,
                                    objective_id=oid, title="Authorized local calculation"),
                               dedupe_key=event["task_id"], cooldown_sec=0)
            self.queue.claim(event["task_id"])
            self.queue.complete(event["task_id"], success=verified, useful=verified,
                                operator_ready=verified, **{k: v for k, v in outcome.items()
                                    if k not in {"effect_kind", "durable_effect_verified", "external_effect_verified"}}, **value)
            self.objectives.link_task(oid, event["task_id"])
            self.objectives.apply_post_execution_objective(oid, archetype=ARCHETYPE,
                                                         exec_result=outcome, value_result=value)
            evidence = dict(event)
            self.queue.get_by_id(event["task_id"])["execution_evidence"] = evidence
            objective["last_execution"]["execution_evidence"] = evidence
            self.outcomes[event["task_id"]] = dict(outcome, **value, evidence=evidence,
                                                   task_id=event["task_id"], objective_id=oid,
                                                   audit_persisted=True)

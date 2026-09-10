"""Persistent local task ledger with bounded claim/lease semantics.

Runtime-disabled integration primitive: this module performs only explicit local
SQLite operations. It does not invoke providers, execute Guardian runtime code,
use the network, merge branches, or deploy anything.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .dispatcher import Worker
from .verifier import select_verifier

ACTIVE_LEASE_STATES = {"claimed", "running"}
TERMINAL_STATES = {"completed", "rejected", "archived"}
NON_DISPATCHABLE_STATES = ACTIVE_LEASE_STATES | {"verifying", "review", "blocked", "human_review"} | TERMINAL_STATES
DEFAULT_MAX_ATTEMPTS = 3
SYSTEM_MAX_REJECTIONS = 2
# Soft risks may complete with identity-only packets; everything else is fail-closed.
_SOFT_EVIDENCE_RISKS = frozenset({"sandbox_write", "read_only"})
_SUBSTANTIVE_PREFIXES = ("artifact:", "commit:", "pr:", "pull_request:")


def _positive_limit(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError("retry limits must be positive integers")
    return value


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _integrity_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalize_refs(refs: Sequence[str]) -> list[str]:
    return [ref.strip() for ref in refs]


def is_substantive_write_ref(ref: str, *, packet_digest: str | None = None) -> bool:
    """Deterministic repository provenance only; packet self-hash is identity, not proof."""
    text = ref.strip()
    if not text:
        return False
    if packet_digest and text == packet_digest:
        return False
    lowered = text.lower()
    for prefix in _SUBSTANTIVE_PREFIXES:
        if lowered.startswith(prefix) and text[len(prefix):].strip():
            return True
    return False


def substantive_write_refs(refs: Sequence[str], *, packet_digest: str | None = None) -> list[str]:
    return [ref.strip() for ref in refs if is_substantive_write_ref(ref, packet_digest=packet_digest)]


def _risk_requires_substantive_evidence(risk_class: object) -> bool:
    if risk_class is None:
        return True
    return str(risk_class) not in _SOFT_EVIDENCE_RISKS


def _checks_satisfy_required(required_checks: Sequence[str], checks: Sequence[Mapping] | None) -> bool:
    by_name = {
        str(check["name"]): check
        for check in (checks or [])
        if isinstance(check, Mapping) and "name" in check
    }
    for name in required_checks:
        check = by_name.get(str(name))
        if check is None or check.get("result") != "pass":
            return False
    return True


def _build_completion_submission(
    *,
    packet_id: str,
    producer_worker_id: str,
    attempt: int,
    evidence_refs: Sequence[str],
    completion_checks: Sequence[Mapping] | None,
    task_payload: Mapping,
    commits: Sequence[str] | None = None,
    pull_requests: Sequence[str] | None = None,
    claims: Sequence[Mapping] | None = None,
) -> dict:
    required_checks = [str(name) for name in task_payload.get("required_checks", [])]
    return {
        "packet_id": packet_id,
        "producer_worker_id": producer_worker_id,
        "attempt": attempt,
        "evidence_refs": _normalize_refs(evidence_refs),
        "commits": list(commits or []),
        "pull_requests": list(pull_requests or []),
        "claims": [dict(claim) for claim in (claims or [])],
        "checks": [dict(check) for check in (completion_checks or [])],
        "risk_class": task_payload.get("risk_class"),
        "required_checks": required_checks,
        "human_approval_required": bool(task_payload.get("human_approval_required", False)),
        "required_review_roles": list(task_payload.get("required_review_roles", [])),
    }


def _submission_meets_minimum_evidence(submission: Mapping, *, packet_digest: str | None = None) -> bool:
    evidence = list(submission.get("evidence_refs") or [])
    evidence.extend(submission.get("commits") or [])
    evidence.extend(submission.get("pull_requests") or [])
    for claim in submission.get("claims") or []:
        if isinstance(claim, Mapping):
            evidence.extend(claim.get("evidence") or [])
    if _risk_requires_substantive_evidence(submission.get("risk_class")):
        if not substantive_write_refs(evidence, packet_digest=packet_digest):
            return False
        if not _checks_satisfy_required(list(submission.get("required_checks") or []), submission.get("checks")):
            return False
    return True


def _review_binds_producer(submission: Mapping, review_evidence: Sequence[str], *, packet_digest: str | None = None) -> bool:
    if not isinstance(review_evidence, list) or any(not isinstance(ref, str) or not ref.strip() for ref in review_evidence):
        return False
    if not review_evidence:
        return False
    required = substantive_write_refs(list(submission.get("evidence_refs") or []), packet_digest=packet_digest)
    required.extend(substantive_write_refs(list(submission.get("commits") or []), packet_digest=packet_digest))
    required.extend(substantive_write_refs(list(submission.get("pull_requests") or []), packet_digest=packet_digest))
    for claim in submission.get("claims") or []:
        if isinstance(claim, Mapping):
            required.extend(substantive_write_refs(list(claim.get("evidence") or []), packet_digest=packet_digest))
    # Preserve producer provenance: every admitted substantive ref must appear in review evidence.
    review_set = {ref.strip() for ref in review_evidence}
    return all(ref in review_set for ref in dict.fromkeys(required))


@dataclass(frozen=True)
class ClaimResult:
    claimed: bool
    task_id: str
    worker_id: str
    reason: str
    lease_expires_at: str | None = None


class TaskLedger:
    """Small auditable SQLite ledger suitable for deterministic orchestration tests."""

    def __init__(
        self,
        path: str | Path,
        *,
        verification_workers: Iterable[Worker] = (),
        independence_groups: Mapping[str, str] | None = None,
    ):
        self.path = str(path)
        self.verification_workers = {
            worker.worker_id: worker for worker in verification_workers
        }
        self.independence_groups = dict(independence_groups or {})
        self.conn = sqlite3.connect(self.path, timeout=5.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, status TEXT NOT NULL,
                attempt INTEGER NOT NULL DEFAULT 0, claimed_by TEXT, lease_expires_at TEXT,
                updated_at TEXT NOT NULL, produced_by TEXT, completion_packet_id TEXT,
                completion_evidence_json TEXT, verification_claimed_by TEXT,
                verification_lease_expires_at TEXT,
                verification_rejections INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                event_type TEXT NOT NULL, actor TEXT, detail_json TEXT NOT NULL,
                created_at TEXT NOT NULL, FOREIGN KEY(task_id) REFERENCES tasks(task_id)
            );
        """)
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(tasks)")}
        for name, definition in (
            ("produced_by", "TEXT"),
            ("completion_packet_id", "TEXT"),
            ("completion_evidence_json", "TEXT"),
            ("completion_submission_json", "TEXT"),
            ("completion_submission_digest", "TEXT"),
            ("verification_supplemental_evidence_json", "TEXT"),
            ("verification_claimed_by", "TEXT"),
            ("verification_lease_expires_at", "TEXT"),
            ("verification_rejections", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in existing:
                self.conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} {definition}")
        for name in ("execution_max_attempts", "verification_max_rejections"):
            if name not in existing:
                self.conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} INTEGER")
        # Snapshot legacy task policy once. Invalid legacy policy receives a zero
        # budget, routing acquisition to human review without deleting history.
        for row in self.conn.execute("SELECT task_id,payload_json FROM tasks WHERE execution_max_attempts IS NULL").fetchall():
            try:
                limit = _positive_limit(json.loads(row["payload_json"]).get("max_attempts", DEFAULT_MAX_ATTEMPTS))
            except (ValueError, TypeError, AttributeError):
                limit = 0
            self.conn.execute("UPDATE tasks SET execution_max_attempts=? WHERE task_id=?", (limit, row["task_id"]))
        self.conn.execute("UPDATE tasks SET verification_max_rejections=? WHERE verification_max_rejections IS NULL", (SYSTEM_MAX_REJECTIONS,))
        self.conn.commit()

    def put_task(self, task: Mapping) -> None:
        limit = _positive_limit(task.get("max_attempts", DEFAULT_MAX_ATTEMPTS))
        attempt = task.get("attempt", 0)
        if type(attempt) is not int or attempt < 0:
            raise ValueError("attempt must be a nonnegative integer")
        task_id=str(task["task_id"]); status=str(task.get("status","queued")); now=_iso(_utcnow()); payload=json.dumps(dict(task),sort_keys=True)
        with self.conn:
            self.conn.execute("""INSERT INTO tasks(task_id,payload_json,status,attempt,updated_at,execution_max_attempts,verification_max_rejections) VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(task_id) DO UPDATE SET
            updated_at=excluded.updated_at""",(task_id,payload,status,attempt,now,limit,SYSTEM_MAX_REJECTIONS))
            actual_status = self.conn.execute("SELECT status FROM tasks WHERE task_id=?", (task_id,)).fetchone()["status"]
            self._event(task_id,"task_upserted","ledger",{"status":actual_status,"requested_status":status},now)

    def get(self, task_id: str) -> dict | None:
        row=self.conn.execute("SELECT * FROM tasks WHERE task_id=?",(task_id,)).fetchone()
        if not row: return None
        result=json.loads(row["payload_json"])
        result["max_attempts"] = row["execution_max_attempts"]
        result["max_verification_rejections"] = row["verification_max_rejections"]
        keys = row.keys()
        result.update({
            "status": row["status"], "attempt": row["attempt"], "claimed_by": row["claimed_by"],
            "lease_expires_at": row["lease_expires_at"], "produced_by": row["produced_by"],
            "completion_packet_id": row["completion_packet_id"],
            "completion_evidence": json.loads(row["completion_evidence_json"] or "[]"),
            "completion_submission": json.loads(row["completion_submission_json"]) if ("completion_submission_json" in keys and row["completion_submission_json"]) else None,
            "completion_submission_digest": row["completion_submission_digest"] if "completion_submission_digest" in keys else None,
            "verification_supplemental_evidence": json.loads(row["verification_supplemental_evidence_json"] or "[]") if "verification_supplemental_evidence_json" in keys else [],
            "verification_claimed_by": row["verification_claimed_by"],
            "verification_lease_expires_at": row["verification_lease_expires_at"],
            "verification_rejections": row["verification_rejections"],
        })
        return result

    def claim(self, task_id: str, worker_id: str, lease_seconds: int=900, now: datetime|None=None) -> ClaimResult:
        if lease_seconds<=0: raise ValueError("lease_seconds must be positive")
        now=now or _utcnow(); now_s=_iso(now); expires=_iso(now+timedelta(seconds=lease_seconds))
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            renewed=self.conn.execute("UPDATE tasks SET status='claimed',lease_expires_at=?,updated_at=? WHERE task_id=? AND claimed_by=? AND lease_expires_at IS NOT NULL AND lease_expires_at>? AND status IN ('claimed','running')",(expires,now_s,task_id,worker_id,now_s))
            if renewed.rowcount==1:
                self._event(task_id,"lease_renewed",worker_id,{"expires":expires},now_s); return ClaimResult(True,task_id,worker_id,"renewed",expires)
            exhausted = self.conn.execute("""UPDATE tasks SET status='human_review',claimed_by=NULL,lease_expires_at=NULL,updated_at=?
                WHERE task_id=? AND (attempt>=execution_max_attempts OR verification_rejections>=verification_max_rejections)
                AND (status='queued' OR (status IN ('claimed','running') AND lease_expires_at<=?))""", (now_s, task_id, now_s))
            if exhausted.rowcount == 1:
                self._event(task_id, "retry_budget_exhausted", worker_id, {"status": "human_review"}, now_s)
                return ClaimResult(False, task_id, worker_id, "attempt_limit_reached")
            acquired=self.conn.execute("UPDATE tasks SET status='claimed',attempt=attempt+1,claimed_by=?,lease_expires_at=?,updated_at=? WHERE task_id=? AND ((status='queued' AND (claimed_by IS NULL OR lease_expires_at IS NULL OR lease_expires_at<=?)) OR (status IN ('claimed','running') AND lease_expires_at IS NOT NULL AND lease_expires_at<=?))",(worker_id,expires,now_s,task_id,now_s,now_s))
            if acquired.rowcount==1:
                self._event(task_id,"task_claimed",worker_id,{"expires":expires},now_s); return ClaimResult(True,task_id,worker_id,"claimed",expires)
            row=self.conn.execute("SELECT * FROM tasks WHERE task_id=?",(task_id,)).fetchone()
            if not row: return ClaimResult(False,task_id,worker_id,"task_not_found")
            if row["status"] in TERMINAL_STATES: return ClaimResult(False,task_id,worker_id,"terminal_task")
            lease_expiry = _parse(row["lease_expires_at"])
            if row["status"] in ACTIVE_LEASE_STATES and lease_expiry and lease_expiry > now:
                return ClaimResult(False,task_id,worker_id,"active_lease",row["lease_expires_at"])
            if row["status"]!="queued": return ClaimResult(False,task_id,worker_id,"state_not_claimable",row["lease_expires_at"])
            return ClaimResult(False,task_id,worker_id,"active_lease",row["lease_expires_at"])

    def submit_for_verification(
        self,
        task_id: str,
        producer_worker_id: str,
        packet_id: str,
        evidence_refs: list[str],
        now: datetime | None = None,
        *,
        completion_checks: list[dict] | None = None,
        commits: list[str] | None = None,
        pull_requests: list[str] | None = None,
        claims: list[dict] | None = None,
        packet_digest: str | None = None,
    ) -> bool:
        if not isinstance(packet_id, str) or not packet_id.strip():
            return False
        if not isinstance(evidence_refs, list) or any(not isinstance(ref, str) or not ref.strip() for ref in evidence_refs):
            return False
        now = now or _utcnow()
        now_s = _iso(now)
        evidence = _normalize_refs(evidence_refs)
        evidence_json = json.dumps(evidence, sort_keys=True)
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            row = self.conn.execute(
                "SELECT attempt,lease_expires_at,payload_json,claimed_by,status FROM tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
            if row is None:
                return False
            # Live execution lease is the only authority to submit this attempt.
            if (
                row["claimed_by"] != producer_worker_id
                or row["status"] not in ("claimed", "running")
                or row["lease_expires_at"] is None
                or _parse(row["lease_expires_at"]) <= now
            ):
                return False
            task_payload = json.loads(row["payload_json"])
            submission = _build_completion_submission(
                packet_id=packet_id,
                producer_worker_id=producer_worker_id,
                attempt=row["attempt"],
                evidence_refs=evidence,
                completion_checks=completion_checks,
                task_payload=task_payload,
                commits=commits,
                pull_requests=pull_requests,
                claims=claims,
            )
            submission_digest = _integrity_digest(submission)
            identity_digest = packet_digest or (packet_id if str(packet_id).startswith("sha256:") else None)
            sufficient = _submission_meets_minimum_evidence(submission, packet_digest=identity_digest)
            next_status = "verifying" if sufficient else "human_review"
            cursor = self.conn.execute(
                """UPDATE tasks SET status=?,produced_by=?,completion_packet_id=?,completion_evidence_json=?,
                   completion_submission_json=?,completion_submission_digest=?,
                   verification_supplemental_evidence_json=?,
                   claimed_by=NULL,lease_expires_at=NULL,verification_claimed_by=NULL,
                   verification_lease_expires_at=NULL,updated_at=?
                   WHERE task_id=? AND claimed_by=? AND status IN ('claimed','running')
                   AND lease_expires_at IS NOT NULL AND lease_expires_at>?""",
                (
                    next_status,
                    producer_worker_id,
                    packet_id,
                    evidence_json,
                    _canonical_json(submission),
                    submission_digest,
                    "[]",
                    now_s,
                    task_id,
                    producer_worker_id,
                    now_s,
                ),
            )
            if cursor.rowcount != 1:
                return False
            detail = {
                "packet_id": packet_id,
                "evidence_refs": evidence,
                "attempt": row["attempt"],
                "producer_lease_expires_at": row["lease_expires_at"],
                "checks": completion_checks or [],
                "submission_digest": submission_digest,
                "status": next_status,
            }
            self._event(task_id, "producer_completion_submitted", producer_worker_id, detail, now_s)
            if not sufficient:
                self._event(
                    task_id,
                    "evidence_binding_rejected",
                    producer_worker_id,
                    {"reason": "insufficient_substantive_evidence", "status": next_status, "packet_id": packet_id},
                    now_s,
                )
            return True

    def claim_verification(
        self,
        task_id: str,
        verifier_worker_id: str,
        lease_seconds: int = 900,
        now: datetime | None = None,
    ) -> ClaimResult:
        if lease_seconds<=0: raise ValueError("lease_seconds must be positive")
        now=now or _utcnow(); now_s=_iso(now); expires=_iso(now+timedelta(seconds=lease_seconds))
        with self.conn:
            row=self.conn.execute("SELECT payload_json,produced_by,completion_packet_id,attempt,verification_claimed_by,verification_lease_expires_at,status FROM tasks WHERE task_id=?",(task_id,)).fetchone()
            if not row: return ClaimResult(False,task_id,verifier_worker_id,"task_not_found")
            if row["status"]!="verifying": return ClaimResult(False,task_id,verifier_worker_id,"state_not_verifiable")
            if row["produced_by"]==verifier_worker_id: return ClaimResult(False,task_id,verifier_worker_id,"self_verification_forbidden")
            candidate = self.verification_workers.get(verifier_worker_id)
            producer_group = self.independence_groups.get(row["produced_by"])
            if candidate is None or producer_group is None:
                return ClaimResult(False,task_id,verifier_worker_id,"verification_registry_missing")
            task = json.loads(row["payload_json"])
            required_capabilities = frozenset(task.get("required_capabilities", [])) | {"verification"}
            risk_class = str(task.get("risk_class", "repo_write"))
            decision = select_verifier(
                producer_worker_id=row["produced_by"],
                producer_independence_group=producer_group,
                workers=self.verification_workers.values(),
                independence_groups=self.independence_groups,
                required_capabilities=frozenset(required_capabilities),
                risk_class=risk_class,
            )
            if decision.state != "verification_claim" or decision.worker_id != verifier_worker_id:
                return ClaimResult(False,task_id,verifier_worker_id,"verifier_not_independent")
            owner=row["verification_claimed_by"]; expiry=_parse(row["verification_lease_expires_at"])
            if owner==verifier_worker_id and expiry and expiry>now:
                self.conn.execute("UPDATE tasks SET verification_lease_expires_at=?,updated_at=? WHERE task_id=?",(expires,now_s,task_id)); self._event(task_id,"verification_lease_renewed",verifier_worker_id,{"expires":expires},now_s); return ClaimResult(True,task_id,verifier_worker_id,"renewed",expires)
            if owner and expiry and expiry>now: return ClaimResult(False,task_id,verifier_worker_id,"active_verification_lease",row["verification_lease_expires_at"])
            self.conn.execute("UPDATE tasks SET verification_claimed_by=?,verification_lease_expires_at=?,updated_at=? WHERE task_id=? AND status='verifying'",(verifier_worker_id,expires,now_s,task_id)); self._event(task_id,"verification_claimed",verifier_worker_id,{"expires":expires},now_s); return ClaimResult(True,task_id,verifier_worker_id,"claimed",expires)

    def accept_verification(self, task_id: str, verifier_worker_id: str, evidence_refs: list[str], now: datetime | None = None) -> bool:
        now = now or _utcnow()
        now_s = _iso(now)
        if not isinstance(evidence_refs, list) or any(not isinstance(ref, str) or not ref.strip() for ref in evidence_refs):
            return False
        review_evidence = _normalize_refs(evidence_refs)
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            row = self.conn.execute(
                """SELECT * FROM tasks WHERE task_id=? AND status='verifying'
                   AND verification_claimed_by=? AND verification_lease_expires_at IS NOT NULL
                   AND verification_lease_expires_at>?""",
                (task_id, verifier_worker_id, now_s),
            ).fetchone()
            if row is None:
                return False
            raw_submission = row["completion_submission_json"]
            stored_digest = row["completion_submission_digest"]
            if not raw_submission or not stored_digest:
                self._event(
                    task_id,
                    "verification_accept_denied",
                    verifier_worker_id,
                    {"reason": "missing_persisted_submission"},
                    now_s,
                )
                return False
            submission = json.loads(raw_submission)
            if _integrity_digest(submission) != stored_digest:
                self._event(
                    task_id,
                    "verification_accept_denied",
                    verifier_worker_id,
                    {"reason": "submission_digest_mismatch"},
                    now_s,
                )
                return False
            packet_digest = row["completion_packet_id"] if str(row["completion_packet_id"] or "").startswith("sha256:") else None
            if not _submission_meets_minimum_evidence(submission, packet_digest=packet_digest):
                self._event(
                    task_id,
                    "verification_accept_denied",
                    verifier_worker_id,
                    {"reason": "producer_evidence_insufficient"},
                    now_s,
                )
                return False
            if not _review_binds_producer(submission, review_evidence, packet_digest=packet_digest):
                self._event(
                    task_id,
                    "verification_accept_denied",
                    verifier_worker_id,
                    {"reason": "review_evidence_unbound", "evidence_refs": review_evidence},
                    now_s,
                )
                return False
            producer_refs = {ref.strip() for ref in (submission.get("evidence_refs") or [])}
            prior_supplemental = json.loads(row["verification_supplemental_evidence_json"] or "[]")
            added = [ref for ref in review_evidence if ref not in producer_refs and ref not in prior_supplemental]
            supplemental = list(prior_supplemental) + added
            cursor = self.conn.execute(
                """UPDATE tasks SET status='completed',verification_claimed_by=NULL,
                   verification_lease_expires_at=NULL,
                   verification_supplemental_evidence_json=?,updated_at=?
                   WHERE task_id=? AND status='verifying' AND verification_claimed_by=?
                   AND verification_lease_expires_at IS NOT NULL AND verification_lease_expires_at>?""",
                (json.dumps(supplemental, sort_keys=True), now_s, task_id, verifier_worker_id, now_s),
            )
            if cursor.rowcount != 1:
                return False
            self._event(
                task_id,
                "verification_accepted",
                verifier_worker_id,
                {
                    "evidence_refs": review_evidence,
                    "submission_digest": stored_digest,
                    "supplemental_evidence_refs": added,
                },
                now_s,
            )
            return True

    def reject_verification(self, task_id: str, verifier_worker_id: str, reason: str, evidence_refs: list[str], max_rejections: int=2, now: datetime|None=None) -> bool:
        # Retained only for source compatibility. Callers cannot set policy.
        # The persisted system ceiling is authoritative even for 0/9999/None.
        now=now or _utcnow(); now_s=_iso(now)
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            row=self.conn.execute("SELECT * FROM tasks WHERE task_id=? AND status='verifying' AND verification_claimed_by=? AND verification_lease_expires_at IS NOT NULL AND verification_lease_expires_at>?",(task_id,verifier_worker_id,now_s)).fetchone()
            if not row: return False
            count=int(row["verification_rejections"])+1
            next_status = "human_review" if count >= row["verification_max_rejections"] or row["attempt"] >= row["execution_max_attempts"] else "queued"
            self.conn.execute("UPDATE tasks SET status=?,verification_rejections=?,verification_claimed_by=NULL,verification_lease_expires_at=NULL,claimed_by=NULL,lease_expires_at=NULL,updated_at=? WHERE task_id=?",(next_status,count,now_s,task_id))
            self._event(task_id,"verification_rejected",verifier_worker_id,{"reason":reason,"evidence_refs":list(evidence_refs),"rejections":count,"next_status":next_status,"max_rejections":row["verification_max_rejections"],"attempt":row["attempt"]},now_s); return True

    def reap_expired_verification(self, now: datetime|None=None) -> list[str]:
        now=now or _utcnow(); now_s=_iso(now)
        rows=self.conn.execute("SELECT task_id,verification_claimed_by,verification_lease_expires_at FROM tasks WHERE status='verifying' AND verification_claimed_by IS NOT NULL AND verification_lease_expires_at IS NOT NULL AND verification_lease_expires_at<=? ORDER BY task_id",(now_s,)).fetchall()
        reaped=[]
        with self.conn:
            for row in rows:
                cursor=self.conn.execute("UPDATE tasks SET verification_claimed_by=NULL,verification_lease_expires_at=NULL,updated_at=? WHERE task_id=? AND status='verifying' AND verification_claimed_by=? AND verification_lease_expires_at=?",(now_s,row["task_id"],row["verification_claimed_by"],row["verification_lease_expires_at"]))
                if cursor.rowcount==1:
                    self._event(row["task_id"],"verification_lease_expired",row["verification_claimed_by"],{},now_s); reaped.append(row["task_id"])
        return reaped

    def release(self, task_id: str, worker_id: str, next_status: str="queued", now: datetime|None=None) -> bool:
        if next_status in ACTIVE_LEASE_STATES: raise ValueError("release next_status cannot retain an active lease state")
        if next_status not in {"queued", "review", "blocked", "human_review", "rejected", "completed"}:
            return False
        now_s=_iso(now or _utcnow())
        with self.conn:
            # Serialize policy inspection and mutation with other ledger writers.
            self.conn.execute("BEGIN IMMEDIATE")
            row = self.conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is None:
                return False
            task = json.loads(row["payload_json"])
            if next_status == "completed" and (
                task.get("risk_class") != "read_only"
                or task.get("human_approval_required", False)
                or task.get("required_review_roles")
                or task.get("required_checks")
                or "verification" in task.get("required_capabilities", [])
            ):
                return False
            if next_status == "queued" and (
                row["attempt"] >= row["execution_max_attempts"]
                or row["verification_rejections"] >= row["verification_max_rejections"]
            ):
                next_status = "human_review"
            cursor=self.conn.execute("UPDATE tasks SET status=?,claimed_by=NULL,lease_expires_at=NULL,updated_at=? WHERE task_id=? AND claimed_by=? AND status IN ('claimed','running') AND lease_expires_at>?",(next_status,now_s,task_id,worker_id,now_s))
            if cursor.rowcount!=1: return False
            self._event(task_id,"task_released",worker_id,{"status":next_status},now_s); return True

    def reap_expired(self, now: datetime|None=None) -> list[str]:
        now=now or _utcnow(); now_s=_iso(now)
        rows=self.conn.execute("SELECT task_id,claimed_by,lease_expires_at FROM tasks WHERE claimed_by IS NOT NULL AND status IN ('claimed','running')").fetchall(); expired=[r for r in rows if (_parse(r["lease_expires_at"]) or now)<=now]
        with self.conn:
            reaped=[]
            for row in expired:
                cursor=self.conn.execute("UPDATE tasks SET status=CASE WHEN attempt>=execution_max_attempts OR verification_rejections>=verification_max_rejections THEN 'human_review' ELSE 'queued' END,claimed_by=NULL,lease_expires_at=NULL,updated_at=? WHERE task_id=? AND claimed_by=? AND lease_expires_at=? AND status IN ('claimed','running')",(now_s,row["task_id"],row["claimed_by"],row["lease_expires_at"]))
                if cursor.rowcount==1:
                    status = self.conn.execute("SELECT status FROM tasks WHERE task_id=?", (row["task_id"],)).fetchone()["status"]
                    self._event(row["task_id"],"lease_expired",row["claimed_by"],{"status":status},now_s)
                    reaped.append(row["task_id"])
        return reaped

    def events(self, task_id: str) -> list[dict]:
        rows=self.conn.execute("SELECT event_type,actor,detail_json,created_at FROM events WHERE task_id=? ORDER BY event_id",(task_id,)).fetchall()
        return [{"event_type":r["event_type"],"actor":r["actor"],"detail":json.loads(r["detail_json"]),"created_at":r["created_at"]} for r in rows]

    def _event(self, task_id: str, event_type: str, actor: str|None, detail: Mapping, created_at: str) -> None:
        self.conn.execute("INSERT INTO events(task_id,event_type,actor,detail_json,created_at) VALUES(?,?,?,?,?)",(task_id,event_type,actor,json.dumps(dict(detail),sort_keys=True),created_at))

"""Persistent local task ledger with bounded claim/lease semantics.

Runtime-disabled integration primitive: this module performs only explicit local
SQLite operations. It does not invoke providers, execute Guardian runtime code,
use the network, merge branches, or deploy anything.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

from .verifier import VerificationDecision

ACTIVE_LEASE_STATES = {"claimed", "running"}
TERMINAL_STATES = {"completed", "rejected", "archived"}
NON_DISPATCHABLE_STATES = ACTIVE_LEASE_STATES | {"verifying", "review", "blocked", "human_review"} | TERMINAL_STATES


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True)
class ClaimResult:
    claimed: bool
    task_id: str
    worker_id: str
    reason: str
    lease_expires_at: str | None = None


class TaskLedger:
    """Small auditable SQLite ledger suitable for deterministic orchestration tests."""

    def __init__(self, path: str | Path):
        self.path = str(path)
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
        for name, definition in (("produced_by","TEXT"),("completion_packet_id","TEXT"),("completion_evidence_json","TEXT"),("verification_claimed_by","TEXT"),("verification_lease_expires_at","TEXT"),("verification_rejections","INTEGER NOT NULL DEFAULT 0")):
            if name not in existing:
                self.conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} {definition}")
        self.conn.commit()

    def put_task(self, task: Mapping) -> None:
        task_id=str(task["task_id"]); status=str(task.get("status","queued")); now=_iso(_utcnow()); payload=json.dumps(dict(task),sort_keys=True)
        with self.conn:
            self.conn.execute("""INSERT INTO tasks(task_id,payload_json,status,attempt,updated_at) VALUES(?,?,?,?,?)
            ON CONFLICT(task_id) DO UPDATE SET payload_json=excluded.payload_json,
            status=CASE WHEN tasks.status IN ('claimed','running','verifying','review','blocked','human_review','completed','rejected','archived') THEN tasks.status ELSE excluded.status END,
            updated_at=excluded.updated_at""",(task_id,payload,status,int(task.get("attempt",0)),now))
            self._event(task_id,"task_upserted","ledger",{"status":status},now)

    def get(self, task_id: str) -> dict | None:
        row=self.conn.execute("SELECT * FROM tasks WHERE task_id=?",(task_id,)).fetchone()
        if not row: return None
        result=json.loads(row["payload_json"])
        result.update({"status":row["status"],"attempt":row["attempt"],"claimed_by":row["claimed_by"],"lease_expires_at":row["lease_expires_at"],"produced_by":row["produced_by"],"completion_packet_id":row["completion_packet_id"],"completion_evidence":json.loads(row["completion_evidence_json"] or "[]"),"verification_claimed_by":row["verification_claimed_by"],"verification_lease_expires_at":row["verification_lease_expires_at"],"verification_rejections":row["verification_rejections"]})
        return result

    def claim(self, task_id: str, worker_id: str, lease_seconds: int=900, now: datetime|None=None) -> ClaimResult:
        if lease_seconds<=0: raise ValueError("lease_seconds must be positive")
        now=now or _utcnow(); now_s=_iso(now); expires=_iso(now+timedelta(seconds=lease_seconds))
        with self.conn:
            renewed=self.conn.execute("UPDATE tasks SET status='claimed',lease_expires_at=?,updated_at=? WHERE task_id=? AND claimed_by=? AND lease_expires_at IS NOT NULL AND lease_expires_at>? AND status IN ('claimed','running')",(expires,now_s,task_id,worker_id,now_s))
            if renewed.rowcount==1:
                self._event(task_id,"lease_renewed",worker_id,{"expires":expires},now_s); return ClaimResult(True,task_id,worker_id,"renewed",expires)
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

    def submit_for_verification(self, task_id: str, producer_worker_id: str, packet_id: str, evidence_refs: list[str], now: datetime|None=None) -> bool:
        now=now or _utcnow(); now_s=_iso(now); evidence_json=json.dumps(list(evidence_refs),sort_keys=True)
        with self.conn:
            # The current live execution lease is the authority to submit this attempt.
            # `produced_by` is therefore attempt-local current state, while the append-only
            # producer_completion_submitted events retain provenance for prior attempts.
            cursor=self.conn.execute("UPDATE tasks SET status='verifying',produced_by=?,completion_packet_id=?,completion_evidence_json=?,claimed_by=NULL,lease_expires_at=NULL,verification_claimed_by=NULL,verification_lease_expires_at=NULL,updated_at=? WHERE task_id=? AND claimed_by=? AND status IN ('claimed','running') AND lease_expires_at IS NOT NULL AND lease_expires_at>?",(producer_worker_id,packet_id,evidence_json,now_s,task_id,producer_worker_id,now_s))
            if cursor.rowcount!=1: return False
            self._event(task_id,"producer_completion_submitted",producer_worker_id,{"packet_id":packet_id,"evidence_refs":list(evidence_refs)},now_s); return True

    def claim_verification(
        self,
        task_id: str,
        verifier_worker_id: str,
        lease_seconds: int = 900,
        now: datetime | None = None,
        *,
        decision: VerificationDecision | None = None,
    ) -> ClaimResult:
        if lease_seconds<=0: raise ValueError("lease_seconds must be positive")
        now=now or _utcnow(); now_s=_iso(now); expires=_iso(now+timedelta(seconds=lease_seconds))
        with self.conn:
            row=self.conn.execute("SELECT produced_by,verification_claimed_by,verification_lease_expires_at,status FROM tasks WHERE task_id=?",(task_id,)).fetchone()
            if not row: return ClaimResult(False,task_id,verifier_worker_id,"task_not_found")
            if row["status"]!="verifying": return ClaimResult(False,task_id,verifier_worker_id,"state_not_verifiable")
            if row["produced_by"]==verifier_worker_id: return ClaimResult(False,task_id,verifier_worker_id,"self_verification_forbidden")
            if decision is None: return ClaimResult(False,task_id,verifier_worker_id,"verification_decision_required")
            if decision.state != "verification_claim": return ClaimResult(False,task_id,verifier_worker_id,"verifier_not_independent")
            if decision.worker_id != verifier_worker_id: return ClaimResult(False,task_id,verifier_worker_id,"verification_decision_mismatch")
            if decision.producer_worker_id != row["produced_by"]: return ClaimResult(False,task_id,verifier_worker_id,"verification_decision_mismatch")
            owner=row["verification_claimed_by"]; expiry=_parse(row["verification_lease_expires_at"])
            if owner==verifier_worker_id and expiry and expiry>now:
                self.conn.execute("UPDATE tasks SET verification_lease_expires_at=?,updated_at=? WHERE task_id=?",(expires,now_s,task_id)); self._event(task_id,"verification_lease_renewed",verifier_worker_id,{"expires":expires},now_s); return ClaimResult(True,task_id,verifier_worker_id,"renewed",expires)
            if owner and expiry and expiry>now: return ClaimResult(False,task_id,verifier_worker_id,"active_verification_lease",row["verification_lease_expires_at"])
            self.conn.execute("UPDATE tasks SET verification_claimed_by=?,verification_lease_expires_at=?,updated_at=? WHERE task_id=? AND status='verifying'",(verifier_worker_id,expires,now_s,task_id)); self._event(task_id,"verification_claimed",verifier_worker_id,{"expires":expires},now_s); return ClaimResult(True,task_id,verifier_worker_id,"claimed",expires)

    def accept_verification(self, task_id: str, verifier_worker_id: str, evidence_refs: list[str], now: datetime|None=None) -> bool:
        now=now or _utcnow(); now_s=_iso(now)
        with self.conn:
            cursor=self.conn.execute("UPDATE tasks SET status='completed',verification_claimed_by=NULL,verification_lease_expires_at=NULL,updated_at=? WHERE task_id=? AND status='verifying' AND verification_claimed_by=? AND verification_lease_expires_at IS NOT NULL AND verification_lease_expires_at>?",(now_s,task_id,verifier_worker_id,now_s))
            if cursor.rowcount!=1: return False
            self._event(task_id,"verification_accepted",verifier_worker_id,{"evidence_refs":list(evidence_refs)},now_s); return True

    def reject_verification(self, task_id: str, verifier_worker_id: str, reason: str, evidence_refs: list[str], max_rejections: int=2, now: datetime|None=None) -> bool:
        if max_rejections<=0: raise ValueError("max_rejections must be positive")
        now=now or _utcnow(); now_s=_iso(now)
        with self.conn:
            row=self.conn.execute("SELECT verification_rejections FROM tasks WHERE task_id=? AND status='verifying' AND verification_claimed_by=? AND verification_lease_expires_at IS NOT NULL AND verification_lease_expires_at>?",(task_id,verifier_worker_id,now_s)).fetchone()
            if not row: return False
            count=int(row["verification_rejections"])+1; next_status="human_review" if count>=max_rejections else "queued"
            self.conn.execute("UPDATE tasks SET status=?,verification_rejections=?,verification_claimed_by=NULL,verification_lease_expires_at=NULL,claimed_by=NULL,lease_expires_at=NULL,updated_at=? WHERE task_id=?",(next_status,count,now_s,task_id))
            self._event(task_id,"verification_rejected",verifier_worker_id,{"reason":reason,"evidence_refs":list(evidence_refs),"rejections":count,"next_status":next_status},now_s); return True

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
        now_s=_iso(now or _utcnow())
        with self.conn:
            cursor=self.conn.execute("UPDATE tasks SET status=?,claimed_by=NULL,lease_expires_at=NULL,updated_at=? WHERE task_id=? AND claimed_by=?",(next_status,now_s,task_id,worker_id))
            if cursor.rowcount!=1: return False
            self._event(task_id,"task_released",worker_id,{"status":next_status},now_s); return True

    def reap_expired(self, now: datetime|None=None) -> list[str]:
        now=now or _utcnow(); now_s=_iso(now)
        rows=self.conn.execute("SELECT task_id,claimed_by,lease_expires_at FROM tasks WHERE claimed_by IS NOT NULL AND status IN ('claimed','running')").fetchall(); expired=[r for r in rows if (_parse(r["lease_expires_at"]) or now)<=now]
        with self.conn:
            reaped=[]
            for row in expired:
                cursor=self.conn.execute("UPDATE tasks SET status='queued',claimed_by=NULL,lease_expires_at=NULL,updated_at=? WHERE task_id=? AND claimed_by=? AND lease_expires_at=? AND status IN ('claimed','running')",(now_s,row["task_id"],row["claimed_by"],row["lease_expires_at"]))
                if cursor.rowcount==1: self._event(row["task_id"],"lease_expired",row["claimed_by"],{},now_s); reaped.append(row["task_id"])
        return reaped

    def events(self, task_id: str) -> list[dict]:
        rows=self.conn.execute("SELECT event_type,actor,detail_json,created_at FROM events WHERE task_id=? ORDER BY event_id",(task_id,)).fetchall()
        return [{"event_type":r["event_type"],"actor":r["actor"],"detail":json.loads(r["detail_json"]),"created_at":r["created_at"]} for r in rows]

    def _event(self, task_id: str, event_type: str, actor: str|None, detail: Mapping, created_at: str) -> None:
        self.conn.execute("INSERT INTO events(task_id,event_type,actor,detail_json,created_at) VALUES(?,?,?,?,?)",(task_id,event_type,actor,json.dumps(dict(detail),sort_keys=True),created_at))

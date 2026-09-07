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
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                attempt INTEGER NOT NULL DEFAULT 0,
                claimed_by TEXT,
                lease_expires_at TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT,
                detail_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id)
            );
            """
        )
        self.conn.commit()

    def put_task(self, task: Mapping) -> None:
        task_id = str(task["task_id"])
        status = str(task.get("status", "queued"))
        now = _iso(_utcnow())
        payload = json.dumps(dict(task), sort_keys=True)
        with self.conn:
            self.conn.execute(
                """INSERT INTO tasks(task_id,payload_json,status,attempt,updated_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(task_id) DO UPDATE SET
                     payload_json=excluded.payload_json,
                     status=CASE WHEN tasks.status IN ('claimed','running','verifying','review','blocked','human_review','completed','rejected','archived')
                                 THEN tasks.status ELSE excluded.status END,
                     updated_at=excluded.updated_at""",
                (task_id, payload, status, int(task.get("attempt", 0)), now),
            )
            self._event(task_id, "task_upserted", "ledger", {"status": status}, now)

    def get(self, task_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            return None
        result = json.loads(row["payload_json"])
        result.update({
            "status": row["status"],
            "attempt": row["attempt"],
            "claimed_by": row["claimed_by"],
            "lease_expires_at": row["lease_expires_at"],
        })
        return result

    def claim(self, task_id: str, worker_id: str, lease_seconds: int = 900, now: datetime | None = None) -> ClaimResult:
        """Atomically renew an owned live lease or acquire a queued task.

        Acquisition is deliberately queued-only. Review/verifying/blocked states
        require an explicit state transition before another execution lease may be
        granted, preventing a stale caller from silently bypassing those gates.
        """
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = now or _utcnow()
        now_s = _iso(now)
        expires = _iso(now + timedelta(seconds=lease_seconds))

        with self.conn:
            renewed = self.conn.execute(
                """UPDATE tasks SET status='claimed', lease_expires_at=?, updated_at=?
                   WHERE task_id=? AND claimed_by=?
                     AND lease_expires_at IS NOT NULL AND lease_expires_at>?
                     AND status IN ('claimed','running')""",
                (expires, now_s, task_id, worker_id, now_s),
            )
            if renewed.rowcount == 1:
                self._event(task_id, "lease_renewed", worker_id, {"expires": expires}, now_s)
                return ClaimResult(True, task_id, worker_id, "renewed", expires)

            acquired = self.conn.execute(
                """UPDATE tasks
                   SET status='claimed', attempt=attempt+1, claimed_by=?, lease_expires_at=?, updated_at=?
                   WHERE task_id=? AND status='queued'
                     AND (claimed_by IS NULL OR lease_expires_at IS NULL OR lease_expires_at<=?)""",
                (worker_id, expires, now_s, task_id, now_s),
            )
            if acquired.rowcount == 1:
                self._event(task_id, "task_claimed", worker_id, {"expires": expires}, now_s)
                return ClaimResult(True, task_id, worker_id, "claimed", expires)

            row = self.conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if not row:
                return ClaimResult(False, task_id, worker_id, "task_not_found")
            if row["status"] in TERMINAL_STATES:
                return ClaimResult(False, task_id, worker_id, "terminal_task")
            if row["status"] != "queued":
                return ClaimResult(False, task_id, worker_id, "state_not_claimable", row["lease_expires_at"])
            return ClaimResult(False, task_id, worker_id, "active_lease", row["lease_expires_at"])

    def release(self, task_id: str, worker_id: str, next_status: str = "queued", now: datetime | None = None) -> bool:
        if next_status in ACTIVE_LEASE_STATES:
            raise ValueError("release next_status cannot retain an active lease state")
        now_s = _iso(now or _utcnow())
        with self.conn:
            cursor = self.conn.execute(
                """UPDATE tasks SET status=?, claimed_by=NULL, lease_expires_at=NULL, updated_at=?
                   WHERE task_id=? AND claimed_by=?""",
                (next_status, now_s, task_id, worker_id),
            )
            if cursor.rowcount != 1:
                return False
            self._event(task_id, "task_released", worker_id, {"status": next_status}, now_s)
            return True

    def reap_expired(self, now: datetime | None = None) -> list[str]:
        now = now or _utcnow()
        now_s = _iso(now)
        rows = self.conn.execute(
            "SELECT task_id, claimed_by, lease_expires_at FROM tasks WHERE claimed_by IS NOT NULL AND status IN ('claimed','running')"
        ).fetchall()
        expired = [r for r in rows if (_parse(r["lease_expires_at"]) or now) <= now]
        with self.conn:
            reaped: list[str] = []
            for row in expired:
                cursor = self.conn.execute(
                    """UPDATE tasks SET status='queued', claimed_by=NULL, lease_expires_at=NULL, updated_at=?
                       WHERE task_id=? AND claimed_by=? AND lease_expires_at=? AND status IN ('claimed','running')""",
                    (now_s, row["task_id"], row["claimed_by"], row["lease_expires_at"]),
                )
                if cursor.rowcount == 1:
                    self._event(row["task_id"], "lease_expired", row["claimed_by"], {}, now_s)
                    reaped.append(row["task_id"])
        return reaped

    def events(self, task_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT event_type,actor,detail_json,created_at FROM events WHERE task_id=? ORDER BY event_id",
            (task_id,),
        ).fetchall()
        return [{"event_type": r["event_type"], "actor": r["actor"], "detail": json.loads(r["detail_json"]), "created_at": r["created_at"]} for r in rows]

    def _event(self, task_id: str, event_type: str, actor: str | None, detail: Mapping, created_at: str) -> None:
        self.conn.execute(
            "INSERT INTO events(task_id,event_type,actor,detail_json,created_at) VALUES(?,?,?,?,?)",
            (task_id, event_type, actor, json.dumps(dict(detail), sort_keys=True), created_at),
        )

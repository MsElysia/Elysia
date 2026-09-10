"""Regression contract for additive AUTOPILOT-004 verifier-ledger migration.

These tests intentionally define the required upgrade behavior before the schema
migration is implemented. They use only a temporary local SQLite database.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from elysia_collective_seed.autopilot.task_ledger import TaskLedger


VERIFIER_COLUMNS = {
    "produced_by",
    "completion_packet_id",
    "completion_evidence_json",
    "completion_submission_json",
    "completion_submission_digest",
    "verification_supplemental_evidence_json",
    "verification_claimed_by",
    "verification_lease_expires_at",
    "verification_rejections",
}


def _legacy_ledger(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE tasks (
            task_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL,
            attempt INTEGER NOT NULL DEFAULT 0,
            claimed_by TEXT,
            lease_expires_at TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor TEXT,
            detail_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(task_id) REFERENCES tasks(task_id)
        );
        INSERT INTO tasks VALUES (
            'legacy-task', '{"task_id":"legacy-task","title":"preserve me"}',
            'queued', 2, NULL, NULL, '2026-09-08T00:00:00+00:00'
        );
        INSERT INTO events(task_id,event_type,actor,detail_json,created_at)
        VALUES ('legacy-task','legacy_event','legacy-worker','{"proof":"keep"}',
                '2026-09-08T00:00:01+00:00');
        """
    )
    conn.commit()
    conn.close()


def test_legacy_ledger_is_additively_migrated_without_history_loss(tmp_path: Path):
    db = tmp_path / "legacy.sqlite3"
    _legacy_ledger(db)

    ledger = TaskLedger(db)
    try:
        columns = {
            row["name"]
            for row in ledger.conn.execute("PRAGMA table_info(tasks)").fetchall()
        }
        assert VERIFIER_COLUMNS.issubset(columns)

        task = ledger.get("legacy-task")
        assert task is not None
        assert task["title"] == "preserve me"
        assert task["attempt"] == 2
        assert task["status"] == "queued"

        events = ledger.events("legacy-task")
        assert len(events) == 1
        assert events[0]["event_type"] == "legacy_event"
        assert events[0]["detail"] == {"proof": "keep"}
    finally:
        ledger.close()


def test_verifier_schema_initialization_is_idempotent(tmp_path: Path):
    db = tmp_path / "idempotent.sqlite3"
    _legacy_ledger(db)

    first = TaskLedger(db)
    first.close()
    second = TaskLedger(db)
    try:
        columns = [
            row["name"]
            for row in second.conn.execute("PRAGMA table_info(tasks)").fetchall()
        ]
        for column in VERIFIER_COLUMNS:
            assert columns.count(column) == 1
        assert len(second.events("legacy-task")) == 1
    finally:
        second.close()

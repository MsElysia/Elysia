# project_guardian/orchestration/telemetry/sqlite_store.py
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .events import LLMCallEvent

logger = logging.getLogger(__name__)


def prompt_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="replace")).hexdigest()[:32]


class TelemetrySqliteStore:
    """Orchestration-only SQLite telemetry."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        root = Path(__file__).resolve().parent.parent.parent.parent
        self.db_path = Path(db_path) if db_path else root / "data" / "orchestration_telemetry.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path), timeout=30)

    def _init_schema(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS llm_calls (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT,
                        task_type TEXT,
                        pipeline_id TEXT,
                        node_id TEXT,
                        provider TEXT,
                        model TEXT,
                        prompt_hash TEXT,
                        latency_ms REAL,
                        input_tokens_est INTEGER,
                        output_tokens_est INTEGER,
                        cost_estimate_usd REAL,
                        outcome_score REAL,
                        review_verdict TEXT,
                        success INTEGER,
                        ts REAL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_llm_calls_task ON llm_calls(task_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_llm_calls_model ON llm_calls(model)"
                )
                self._ensure_columns(
                    conn,
                    [
                        ("action_type", "TEXT"),
                        ("target_kind", "TEXT"),
                        ("target_name", "TEXT"),
                        ("execution_path", "TEXT"),
                        ("state_change_detected", "INTEGER"),
                        ("candidate_count", "INTEGER"),
                        ("chosen_target_in_candidates", "INTEGER"),
                        ("action_intent_valid", "INTEGER"),
                        ("validation_reason", "TEXT"),
                        ("fallback_mode", "TEXT"),
                    ],
                )
                conn.commit()
        except Exception as e:
            logger.debug("orchestration telemetry init: %s", e)

    def _ensure_columns(self, conn: sqlite3.Connection, specs: list) -> None:
        cur = conn.execute("PRAGMA table_info(llm_calls)")
        have = {row[1] for row in cur.fetchall()}
        for col, typ in specs:
            if col not in have:
                try:
                    conn.execute(f"ALTER TABLE llm_calls ADD COLUMN {col} {typ}")
                except Exception as e:
                    logger.debug("telemetry alter %s: %s", col, e)

    async def log_call(self, event: LLMCallEvent) -> None:
        try:
            with self._connect() as conn:
                self._ensure_columns(
                    conn,
                    [
                        ("action_type", "TEXT"),
                        ("target_kind", "TEXT"),
                        ("target_name", "TEXT"),
                        ("execution_path", "TEXT"),
                        ("state_change_detected", "INTEGER"),
                        ("candidate_count", "INTEGER"),
                        ("chosen_target_in_candidates", "INTEGER"),
                        ("action_intent_valid", "INTEGER"),
                        ("validation_reason", "TEXT"),
                        ("fallback_mode", "TEXT"),
                    ],
                )
                conn.execute(
                    """
                    INSERT INTO llm_calls (
                        task_id, task_type, pipeline_id, node_id, provider, model,
                        prompt_hash, latency_ms, input_tokens_est, output_tokens_est,
                        cost_estimate_usd, outcome_score, review_verdict, success, ts,
                        action_type, target_kind, target_name, execution_path, state_change_detected,
                        candidate_count, chosen_target_in_candidates, action_intent_valid,
                        validation_reason, fallback_mode
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        event.task_id,
                        event.task_type,
                        event.pipeline_id,
                        event.node_id,
                        event.provider,
                        event.model,
                        event.prompt_hash,
                        event.latency_ms,
                        event.input_tokens_est,
                        event.output_tokens_est,
                        event.cost_estimate_usd,
                        event.outcome_score,
                        event.review_verdict,
                        1 if event.success else 0,
                        time.time(),
                        event.action_type,
                        event.target_kind,
                        event.target_name,
                        event.execution_path,
                        self._tri_state_bool(event.state_change_detected),
                        event.candidate_count,
                        self._tri_state_bool(event.chosen_target_in_candidates),
                        self._tri_state_bool(event.action_intent_valid),
                        event.validation_reason,
                        event.fallback_mode,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.debug("orchestration telemetry log: %s", e)

    @staticmethod
    def _tri_state_bool(b: Optional[bool]) -> Optional[int]:
        if b is None:
            return None
        return 1 if b else 0

    async def recent_route_health(self, task_type: str, model: str) -> Dict[str, Any]:
        return {
            "task_type": task_type,
            "model": model,
            "avg_outcome": await self.average_outcome(task_type, model),
            "recent_failures_count": len(await self.recent_failures(model, limit=20)),
        }

    async def aggregate_route_metrics(
        self,
        *,
        task_type: str,
        pipeline_id: str,
        since_ts: float,
        planner_provider: Optional[str] = None,
        planner_model_short: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Rollups from llm_calls only (existing columns). planner_* filter applies to
        plan/execute/fanout rows; validation/review/outcome queries are unscoped by model.
        """
        out: Dict[str, Any] = {
            "llm_total": 0,
            "llm_ok": 0,
            "fanout_total": 0,
            "fanout_ok": 0,
            "validate_total": 0,
            "invalid_intents": 0,
            "intent_labeled": 0,
            "fallback_labeled": 0,
            "legacy_fallbacks": 0,
            "review_total": 0,
            "review_fail": 0,
            "avg_outcome_score": None,
            "avg_latency_ms": None,
        }
        try:
            with self._connect() as conn:
                llm_nodes = ("plan", "execute", "fanout_a", "fanout_b")
                ph = ",".join("?" * len(llm_nodes))

                if planner_provider and planner_model_short:
                    row = conn.execute(
                        f"""
                        SELECT COUNT(*), COALESCE(SUM(CASE WHEN success != 0 THEN 1 ELSE 0 END), 0)
                        FROM llm_calls
                        WHERE task_type = ? AND pipeline_id = ? AND ts >= ?
                          AND node_id IN ({ph})
                          AND provider = ? AND model = ?
                        """,
                        (task_type, pipeline_id, since_ts, *llm_nodes, planner_provider, planner_model_short),
                    ).fetchone()
                else:
                    row = conn.execute(
                        f"""
                        SELECT COUNT(*), COALESCE(SUM(CASE WHEN success != 0 THEN 1 ELSE 0 END), 0)
                        FROM llm_calls
                        WHERE task_type = ? AND pipeline_id = ? AND ts >= ?
                          AND node_id IN ({ph})
                        """,
                        (task_type, pipeline_id, since_ts, *llm_nodes),
                    ).fetchone()
                if row:
                    out["llm_total"] = int(row[0] or 0)
                    out["llm_ok"] = int(row[1] or 0)

                frow = conn.execute(
                    f"""
                    SELECT COUNT(*), COALESCE(SUM(CASE WHEN success != 0 THEN 1 ELSE 0 END), 0)
                    FROM llm_calls
                    WHERE task_type = ? AND pipeline_id = ? AND ts >= ?
                      AND node_id IN ('fanout_a', 'fanout_b')
                    """,
                    (task_type, pipeline_id, since_ts),
                ).fetchone()
                if frow:
                    out["fanout_total"] = int(frow[0] or 0)
                    out["fanout_ok"] = int(frow[1] or 0)

                vrow = conn.execute(
                    """
                    SELECT
                      COUNT(*),
                      COALESCE(SUM(CASE WHEN action_intent_valid IS NOT NULL AND action_intent_valid = 0 THEN 1 ELSE 0 END), 0),
                      COALESCE(SUM(CASE WHEN action_intent_valid IS NOT NULL THEN 1 ELSE 0 END), 0),
                      COALESCE(SUM(CASE WHEN fallback_mode IS NOT NULL AND TRIM(COALESCE(fallback_mode,'')) != '' THEN 1 ELSE 0 END), 0),
                      COALESCE(SUM(CASE WHEN fallback_mode = 'legacy_capability_loop' THEN 1 ELSE 0 END), 0)
                    FROM llm_calls
                    WHERE task_type = ? AND pipeline_id = ? AND ts >= ? AND node_id = 'validate'
                    """,
                    (task_type, pipeline_id, since_ts),
                ).fetchone()
                if vrow:
                    out["validate_total"] = int(vrow[0] or 0)
                    out["invalid_intents"] = int(vrow[1] or 0)
                    out["intent_labeled"] = int(vrow[2] or 0)
                    out["fallback_labeled"] = int(vrow[3] or 0)
                    out["legacy_fallbacks"] = int(vrow[4] or 0)

                rrow = conn.execute(
                    """
                    SELECT COUNT(*), COALESCE(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END), 0)
                    FROM llm_calls
                    WHERE task_type = ? AND pipeline_id = ? AND ts >= ? AND node_id = 'review_action'
                    """,
                    (task_type, pipeline_id, since_ts),
                ).fetchone()
                if rrow:
                    out["review_total"] = int(rrow[0] or 0)
                    out["review_fail"] = int(rrow[1] or 0)

                orow = conn.execute(
                    """
                    SELECT AVG(outcome_score), AVG(latency_ms)
                    FROM llm_calls
                    WHERE task_type = ? AND pipeline_id = ? AND ts >= ? AND outcome_score IS NOT NULL
                    """,
                    (task_type, pipeline_id, since_ts),
                ).fetchone()
                if orow and orow[0] is not None:
                    out["avg_outcome_score"] = float(orow[0])
                if orow and orow[1] is not None:
                    out["avg_latency_ms"] = float(orow[1])
        except Exception as e:
            logger.debug("aggregate_route_metrics: %s", e)
        return out

    async def recent_failures(self, model: str, limit: int = 20) -> list:
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    SELECT task_id, pipeline_id, node_id, ts
                    FROM llm_calls
                    WHERE model = ? AND success = 0
                    ORDER BY ts DESC LIMIT ?
                    """,
                    (model, limit),
                )
                return [{"task_id": r[0], "pipeline_id": r[1], "node_id": r[2], "ts": r[3]} for r in cur.fetchall()]
        except Exception as e:
            logger.debug("recent_failures: %s", e)
            return []

    async def average_outcome(self, task_type: str, model: str) -> Optional[float]:
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    SELECT AVG(outcome_score) FROM llm_calls
                    WHERE task_type = ? AND model = ? AND outcome_score IS NOT NULL
                    AND ts > ?
                    """,
                    (task_type, model, time.time() - 86400 * 7),
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    return round(float(row[0]), 4)
        except Exception as e:
            logger.debug("average_outcome: %s", e)
        return None

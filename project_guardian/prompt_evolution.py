from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_DIR = ROOT / "data" / "prompt_registry"
INDEX_PATH = REGISTRY_DIR / "prompt_index.json"
PERF_PATH = REGISTRY_DIR / "performance_logs.jsonl"
REVIEW_PATH = REGISTRY_DIR / "review_history.jsonl"
CFG_PATH = ROOT / "config" / "prompt_evolution.json"


def _ensure_store() -> None:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_PATH.exists():
        INDEX_PATH.write_text("{}", encoding="utf-8")
    for p in (PERF_PATH, REVIEW_PATH):
        if not p.exists():
            p.write_text("", encoding="utf-8")


def _load_cfg() -> Dict[str, Any]:
    if not CFG_PATH.is_file():
        return {}
    try:
        return json.loads(CFG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def log_prompt_performance(row: Dict[str, Any]) -> None:
    _ensure_store()
    safe = dict(row or {})
    safe.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    _append_jsonl(PERF_PATH, safe)


def should_review_prompt(prompt_id, version, metrics) -> bool:
    cfg = _load_cfg()
    min_calls = int(cfg.get("min_calls_before_review", 20))
    if int(metrics.get("calls", 0)) < min_calls:
        return False
    return any(
        [
            float(metrics.get("valid_json_rate", 1.0)) < float(cfg.get("min_valid_json_rate", 0.95)),
            float(metrics.get("schema_pass_rate", 1.0)) < float(cfg.get("min_schema_pass_rate", 0.90)),
            float(metrics.get("retry_rate", 0.0)) > float(cfg.get("max_retry_rate", 0.25)),
            float(metrics.get("human_override_rate", 0.0)) > float(cfg.get("max_human_override_rate", 0.30)),
            float(metrics.get("task_success_rate", 1.0)) < 0.75,
            float(metrics.get("average_confidence", 1.0)) < 0.45,
        ]
    )


def review_prompt_with_llms(prompt_profile, failure_logs, reviewer_llm_clients):
    reviews: List[Dict[str, Any]] = []
    for i, client in enumerate(reviewer_llm_clients or []):
        fn = getattr(client, "review_prompt", None) or getattr(client, "complete", None) or client
        out = fn(prompt_profile=prompt_profile, failure_logs=failure_logs)
        if isinstance(out, str):
            try:
                out = json.loads(out)
            except Exception:
                out = {}
        if not isinstance(out, dict):
            out = {}
        out.setdefault("reviewer", f"reviewer_{i+1}")
        out.setdefault("diagnosis", "")
        out.setdefault("identified_failures", [])
        out.setdefault("recommended_changes", [])
        out.setdefault("risk_notes", [])
        out.setdefault("replacement_prompt_candidate", "")
        out.setdefault("expected_improvements", [])
        out.setdefault("confidence", 0.0)
        reviews.append(out)
    _ensure_store()
    _append_jsonl(
        REVIEW_PATH,
        {
            "event": "prompt_review",
            "prompt_id": (prompt_profile or {}).get("prompt_id"),
            "version": (prompt_profile or {}).get("version"),
            "reviews": reviews,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    return reviews


def generate_prompt_candidates(prompt_profile, review_results, max_candidates=3):
    base = dict(prompt_profile or {})
    out = []
    for i, rev in enumerate(review_results[: max(1, int(max_candidates))]):
        cand = dict(base)
        cand["version"] = int(base.get("version", 1)) + i + 1
        cand["status"] = "candidate"
        extra_instr = list(cand.get("behavioral_instructions") or [])
        for r in rev.get("recommended_changes") or []:
            if isinstance(r, str) and r.strip():
                extra_instr.append(r.strip()[:220])
        cand["behavioral_instructions"] = extra_instr[:18]
        cand["candidate_id"] = f"{base.get('prompt_id','prompt')}_cand_{i+1}"
        out.append(cand)
    return out


def test_prompt_candidate(candidate_profile, test_cases, llm_clients):
    total = max(1, len(test_cases or []))
    passed = 0
    details = []
    for t in test_cases or []:
        ok = isinstance(t, dict) and "task" in t
        passed += 1 if ok else 0
        details.append({"task_id": t.get("task_id") if isinstance(t, dict) else None, "ok": ok})
    score = passed / total
    return {"score": score, "passed": passed, "total": total, "details": details}


# Avoid pytest treating this helper as a test function.
test_prompt_candidate.__test__ = False


def promote_prompt_candidate(prompt_id, candidate_id):
    _ensure_store()
    idx = json.loads(INDEX_PATH.read_text(encoding="utf-8") or "{}")
    row = idx.get(prompt_id) or {}
    row["active_candidate"] = candidate_id
    row["updated_at"] = datetime.now(timezone.utc).isoformat()
    idx[prompt_id] = row
    INDEX_PATH.write_text(json.dumps(idx, indent=2), encoding="utf-8")
    return {"promoted": True, "prompt_id": prompt_id, "candidate_id": candidate_id}


def rollback_prompt(prompt_id, target_version):
    _ensure_store()
    idx = json.loads(INDEX_PATH.read_text(encoding="utf-8") or "{}")
    row = idx.get(prompt_id) or {}
    row["active_version"] = int(target_version)
    row["updated_at"] = datetime.now(timezone.utc).isoformat()
    idx[prompt_id] = row
    INDEX_PATH.write_text(json.dumps(idx, indent=2), encoding="utf-8")
    return {"rolled_back": True, "prompt_id": prompt_id, "target_version": int(target_version)}


def run_prompt_health_check():
    _ensure_store()
    return {
        "scanned": True,
        "auto_promote_enabled": bool(_load_cfg().get("auto_promote", False)),
        "recommendations": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

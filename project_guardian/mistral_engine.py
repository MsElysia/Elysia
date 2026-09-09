# project_guardian/mistral_engine.py
# Local Mistral (via Ollama) decision engine for Elysia
#
# Mistral-owned: most high-level routing (what to do, which module, needs_memory, ask_user,
#   exploration vs exploit, stagnation alternatives). Python governor overrides when needed.

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Substrings for broker / pipeline errors that should count as local transport failure
# (same pool failover signal as direct Ollama HTTP failures in decide_next_action).
_TRANSPORT_FAILURE_NEEDLES: tuple[str, ...] = (
    "timeout",
    "timed out",
    "readtimeout",
    "connecttimeout",
    "connection refused",
    "connection reset",
    "actively refused",
    "unreachable",
    "name or service not known",
    "temporary failure",
    "network is unreachable",
    "errno",
    "broken pipe",
    "reset by peer",
    "503",
    "502",
    "500",
    "httpx",
    "httpstatus",
    "http error",
    "connecterror",
    "remote end closed",
)


def orchestration_broker_suggests_transport_failure(
    pr: Any = None,
    exc: Optional[BaseException] = None,
) -> bool:
    """
    True when orchestration broker / pipeline errors look like local HTTP transport
    (Ollama down, timeouts, connection refused), not review/validation-only failures.
    """
    parts: List[str] = []
    if exc is not None:
        parts.append(str(exc))
    if pr is not None:
        pe = getattr(pr, "error", None)
        if pe:
            el = str(pe).lower()
            soft = (
                "bounded_action_incomplete",
                "bounded_action",
                "validation",
                "unparseable",
                "review",
            )
            if not any(s in el for s in soft):
                parts.append(str(pe))
        for nr in getattr(pr, "node_results", None) or []:
            if (getattr(nr, "provider", "") or "").lower() != "ollama":
                continue
            err = getattr(nr, "error", None)
            if err:
                parts.append(str(err))
    blob = " ".join(parts).lower()
    if not blob.strip():
        return False
    return any(n in blob for n in _TRANSPORT_FAILURE_NEEDLES)


def _merged_context_pipeline_view(guardian_state: Dict[str, Any]) -> Dict[str, Any]:
    """Merge nested context_pipeline with top-level snapshot keys (tests and brokers may set either)."""
    raw = guardian_state.get("context_pipeline")
    cp: Dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    for key in (
        "context_pipeline_packet",
        "context_pipeline_online",
        "context_pipeline_summary",
        "context_pipeline_validation",
        "planner_injection",
    ):
        if guardian_state.get(key) is not None:
            cp[key] = guardian_state[key]
    if guardian_state.get("context_pipeline_packet") is None and guardian_state.get("prompt_packet") is not None:
        cp["context_pipeline_packet"] = guardian_state.get("prompt_packet")
    return cp


# Legacy: full chat URL still accepted in MistralEngine(ollama_url=...); normalized to base internally.
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"

# Schema for decide_next_action: Mistral returns this for runtime routing decisions.
_DECIDE_NEXT_ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "chosen_action": {"type": "string"},
        "chosen_module": {"type": "string"},
        "reasoning": {"type": "string"},
        "confidence": {"type": "number"},
        "needs_memory": {"type": "boolean"},
        "ask_user_question": {"type": "string"},
        "exploration_score": {"type": "number"},
        "fallback_action": {"type": "string"},
        "pre_recon_summary": {"type": "string"},
        "capability_route": {"type": "string"},
    },
    "required": ["chosen_action", "reasoning", "confidence"],
}

_LEARNING_TARGETS_SCHEMA = {
    "type": "object",
    "properties": {
        "twitter_queries": {"type": "array", "items": {"type": "string"}},
        "reddit_subreddits_new": {"type": "array", "items": {"type": "string"}},
        "reddit_searches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subreddit": {"type": "string"},
                    "q": {"type": "string"},
                },
                "required": ["subreddit", "q"],
            },
        },
        "wikipedia_titles": {"type": "array", "items": {"type": "string"}},
        "google_queries": {"type": "array", "items": {"type": "string"}},
        "reasoning": {"type": "string"},
    },
    "required": [
        "twitter_queries",
        "reddit_subreddits_new",
        "reddit_searches",
        "wikipedia_titles",
        "google_queries",
        "reasoning",
    ],
}

_DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "args": {"type": "object"},
                },
                "required": ["tool", "args"],
            },
        },
        "risk_level": {"type": "string"},
        "fallback": {"type": "string"},
    },
    "required": ["decision", "actions"],
}

_LEARNING_TARGET_CONTEXT_MAX_CHARS = 3200
_LEARNING_TARGET_HISTORY_MAX_ITEMS = 12
_LEARNING_TARGET_HISTORY_ITEM_MAX_CHARS = 90


def _clean_learning_history_values(
    values: Optional[List[str]],
    *,
    max_items: int = _LEARNING_TARGET_HISTORY_MAX_ITEMS,
    max_chars: int = _LEARNING_TARGET_HISTORY_ITEM_MAX_CHARS,
) -> List[str]:
    cleaned: List[str] = []
    seen: set[str] = set()
    for raw in list(values or [])[-max_items:]:
        text = re.sub(r"\s+", " ", str(raw or "")).strip()
        if not text:
            continue
        item = text[:max_chars]
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    return cleaned


def _compact_learning_context(context: str, *, max_chars: int = _LEARNING_TARGET_CONTEXT_MAX_CHARS) -> str:
    text = str(context or "").strip()
    if len(text) <= max_chars:
        return text
    separator = "\n\n...[trimmed for local planner]...\n\n"
    round_pos = text.rfind("\n\n--- After round")
    if round_pos >= 0:
        recent = text[round_pos:].strip()
        if len(recent) >= max_chars - 160:
            return recent[-max_chars:]
        head_budget = max_chars - len(separator) - len(recent)
        if head_budget <= 0:
            return recent[-max_chars:]
        head = text[:head_budget].rstrip()
        return (head + separator + recent)[:max_chars]
    available = max_chars - len(separator)
    if available <= 800:
        return text[:max_chars]
    tail_budget = min(max(1000, int(available * 0.32)), max(600, available - 1600))
    head_budget = available - tail_budget
    if head_budget < 800:
        head_budget = max(800, available // 2)
        tail_budget = max(400, available - head_budget)
    head = text[:head_budget].rstrip()
    tail = text[-tail_budget:].lstrip()
    return (head + separator + tail)[:max_chars]


class MistralEngine:
    """Local Mistral decision engine via Ollama."""

    def __init__(self, model: Optional[str] = None, ollama_url: str = OLLAMA_URL):
        from .ollama_health import normalize_ollama_base
        from .ollama_model_config import get_canonical_ollama_model

        raw_model = (model or "").strip()
        self.model = raw_model if raw_model else get_canonical_ollama_model(log_once=True)
        raw = (ollama_url or "").strip()
        if "/api/" in raw:
            raw = raw.split("/api/")[0].rstrip("/")
        self._ollama_base = normalize_ollama_base(raw or None)
        self._ollama_health = None
        self.ollama_url = f"{self._ollama_base}/api/chat"  # legacy attr for introspection

    def _ollama_http_timeout(self, default: float = 48.0) -> float:
        raw = (os.environ.get("MISTRAL_OLLAMA_TIMEOUT_SEC") or "").strip()
        try:
            base = max(12.0, float(raw or default))
        except ValueError:
            base = default
        try:
            from .planner_readiness import effective_planner_http_timeout_sec

            t = effective_planner_http_timeout_sec(base)
        except Exception:
            t = base
        try:
            from .startup_runtime_guard import early_runtime_budget_active

            if early_runtime_budget_active():
                try:
                    cap = float(os.environ.get("ELYSIA_EARLY_OLLAMA_TIMEOUT_CAP_SEC", "22"))
                except ValueError:
                    cap = 22.0
                t = min(t, max(12.0, cap))
        except Exception:
            pass
        return t

    def _ensure_ollama(self):
        from .ollama_health import verify_ollama_runtime

        if self._ollama_health is not None:
            return self._ollama_health
        self._ollama_health = verify_ollama_runtime(self._ollama_base, self.model)
        return self._ollama_health

    def _post_ollama(self, chat_payload: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]:
        """POST to /api/chat or /api/generate based on health probe."""
        import requests

        from .ollama_health import messages_to_prompt

        if timeout is None:
            timeout = self._ollama_http_timeout()
        h = self._ensure_ollama()
        if not h.ok:
            raise RuntimeError(h.detail)
        if not h.prefer_generate:
            r = requests.post(h.chat_url, json=chat_payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        messages = chat_payload.get("messages") or []
        prompt = messages_to_prompt(messages)
        gen_body: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": chat_payload.get("options") or {"temperature": 0.2},
        }
        if "format" in chat_payload:
            gen_body["format"] = chat_payload["format"]
        r = requests.post(h.generate_url, json=gen_body, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        text = (data.get("response") or "").strip()
        return {"message": {"content": text}}

    def decide(
        self,
        goal: str,
        state: Dict[str, Any],
        tools: List[Dict[str, Any]],
        memory: Optional[List] = None,
        constraints: Optional[List[str]] = None,
        task_description: Optional[str] = None,
        *,
        module_name: str,
        agent_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ask Mistral for a decision. Returns {decision, actions, risk_level?, fallback?}."""
        try:
            import requests
        except ImportError:
            raise ImportError("requests required for MistralEngine: pip install requests")

        from .llm.prompted_call import log_prompted_call, prepare_prompted_bundle, require_prompt_profile

        mod, ag, _ = require_prompt_profile(
            module_name, agent_name, caller="MistralEngine.decide", allow_legacy=False
        )

        tools_list = [t.get("name", t) if isinstance(t, dict) else str(t) for t in tools]

        orch: Dict[str, Any] = {}
        try:
            from .multi_api_router import evaluate_api_vs_local

            td = (task_description or goal or "")[:800]
            ev = evaluate_api_vs_local(td, registry=None)
            orch = {
                "api_vs_local": {
                    "use_api_suggested": bool(ev.get("use_api")),
                    "reason": (ev.get("reason") or "")[:200],
                    "task_class": ev.get("task_class"),
                },
                "tool_first_rule": (
                    "If any listed tool can satisfy the goal, you MUST emit actions using those tool names only — "
                    "do not substitute freeform 'reasoning' steps for tool execution."
                ),
            }
        except Exception as e:
            logger.debug("[Mistral] decide orchestration hint: %s", e)

        _decide_bundle = prepare_prompted_bundle(
            module_name=mod,
            agent_name=ag,
            task_text="Emit minimal safe tool actions for the goal; honor orchestration hints.",
            context={
                "goal": goal,
                "state": state,
                "tools": tools_list,
                "memory": (memory or [])[:20],
                "constraints": constraints or [],
                "orchestration": orch,
                "task_description": (task_description or "")[:1200],
            },
            output_schema={
                "type": "elysia_decision",
                "required": ["decision", "actions"],
                "optional": ["risk_level", "fallback"],
            },
            caller="MistralEngine.decide",
        )
        log_prompted_call(
            module_name=mod,
            agent_name=ag,
            task_type="decide",
            provider="ollama",
            model=self.model,
            bundle_meta=_decide_bundle["meta"],
            prompt_length=len(_decide_bundle["prompt_text"]),
            legacy_prompt_path=False,
        )

        payload = {
            "model": self.model,
            "stream": False,
            "format": _DECISION_SCHEMA,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return ONLY JSON matching the schema. No markdown.\n\n"
                        + _decide_bundle["prompt_text"]
                    ),
                },
                {"role": "user", "content": "Respond with JSON only."},
            ],
            "options": {"temperature": 0.2},
        }

        if not self._ensure_ollama().ok:
            raise RuntimeError(self._ollama_health.detail if self._ollama_health else "ollama_unavailable")
        data = self._post_ollama(payload, timeout=self._ollama_http_timeout(60.0))
        content = data.get("message", {}).get("content", "{}")
        if isinstance(content, dict):
            return content
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            payload["format"] = "json"
            data2 = self._post_ollama(payload, timeout=self._ollama_http_timeout(60.0))
            content2 = data2.get("message", {}).get("content", "{}")
            if isinstance(content2, dict):
                return content2
            return json.loads(content2)

    def complete_chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 500,
        temperature: float = 0.35,
        *,
        module_name: str,
        agent_name: Optional[str] = None,
        task_text: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        task_type: Optional[str] = None,
        call_id: Optional[str] = None,
        route_task_type: Optional[str] = None,
        attempt_index: Optional[int] = None,
        fallback_from: Optional[str] = None,
    ) -> str:
        """Plain Ollama chat for unified LLM routing; optional task_text/context/output_schema for structured tasks."""
        from .llm.prompted_call import (
            log_prompted_call,
            prepare_prompted_messages,
            prompt_payload_fingerprint,
            require_prompt_profile,
        )

        mod, ag, _ = require_prompt_profile(
            module_name, agent_name, caller="MistralEngine.complete_chat", allow_legacy=False
        )

        tt = (
            task_text
            if task_text is not None
            else "Unified chat completion: respond as the assistant to the conversation thread."
        )
        _prep = prepare_prompted_messages(
            messages,
            module_name=mod,
            agent_name=ag,
            task_text=tt,
            context=context,
            output_schema=output_schema,
            caller="MistralEngine.complete_chat",
        )
        log_prompted_call(
            module_name=mod,
            agent_name=ag,
            task_type=task_type or "unified_chat",
            provider="ollama",
            model=self.model,
            bundle_meta=_prep["meta"],
            prompt_length=len(_prep["system_text"]),
            legacy_prompt_path=False,
            call_id=call_id,
            route_task_type=route_task_type,
            attempt_index=attempt_index,
            fallback_from=fallback_from,
            prompt_hash=prompt_payload_fingerprint(_prep["messages"]),
        )
        msgs = _prep["messages"]

        payload = {
            "model": self.model,
            "stream": False,
            "messages": msgs,
            "options": {"temperature": temperature, "num_predict": max(int(max_tokens), 1)},
        }
        if not self._ensure_ollama().ok:
            raise RuntimeError(self._ollama_health.detail if self._ollama_health else "ollama_unavailable")
        tt_norm = (task_type or "").strip().lower()
        mod_norm = (module_name or "").strip().lower()
        call_timeout = self._ollama_http_timeout(120.0)
        if tt_norm == "compress_with_llm" or mod_norm == "summarizer":
            try:
                lo = float(os.environ.get("ELYSIA_LEARNING_OLLAMA_TIMEOUT_SEC", "210"))
            except ValueError:
                lo = 210.0
            if (os.environ.get("ELYSIA_LEARNING_LOCAL_PRIORITY", "").strip().lower() in ("1", "true", "yes", "on")):
                lo = max(lo, 270.0)
            call_timeout = self._ollama_http_timeout(max(90.0, min(360.0, lo)))
        data = self._post_ollama(payload, timeout=call_timeout)
        content = data.get("message", {}).get("content", "")
        return (content or "").strip()

    def _load_decider_config(self) -> Dict[str, Any]:
        """Load config/mistral_decider.json for routing knobs."""
        cfg_path = Path(__file__).parent.parent / "config" / "mistral_decider.json"
        if cfg_path.exists():
            try:
                with open(cfg_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "mistral_primary_decider_enabled": True,
            "mistral_decision_confidence_threshold": 0.5,
            "mistral_override_on_memory_pressure": True,
            "mistral_force_exploration_after_stagnation": True,
            "mistral_max_repeated_action_count": 3,
        }

    def decide_next_action(
        self,
        guardian_state: Dict[str, Any],
        governance_hints: Optional[List[str]] = None,
        *,
        module_name: str,
        agent_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Mistral-owned routing: decide next action, module, needs_memory, ask_user, exploration.
        Python governor may override based on hard rules (pressure, cooldown, block).
        Returns: chosen_action, chosen_module, reasoning, confidence, needs_memory,
        ask_user_question, exploration_score, fallback_action, pre_recon_summary, capability_route.
        """
        try:
            import requests
        except ImportError:
            raise ImportError("requests required for MistralEngine: pip install requests")

        from .local_planner_breaker import (
            allow_planner_call,
            note_planner_failure,
            note_planner_success,
        )
        from .llm.prompted_call import require_prompt_profile

        mod, ag, _ = require_prompt_profile(
            module_name, agent_name, caller="MistralEngine.decide_next_action", allow_legacy=False
        )

        candidates = guardian_state.get("candidates", [])
        if not candidates:
            return self._decide_fallback_empty(guardian_state)

        if not allow_planner_call():
            logger.info(
                "[PlannerBreaker] Skipping planner call (circuit open; avoiding long Ollama stall)"
            )
            return self._decide_fallback_empty(guardian_state)

        _t_planner = time.perf_counter()
        _lat_box: List[bool] = [False]

        def _planner_body() -> Dict[str, Any]:
            broker_transport_hint = False
            tools_list = [
                {
                    "action": c.get("action", ""),
                    "source": c.get("source", ""),
                    "reason": (c.get("reason", "") or "")[:120],
                    "priority_score": c.get("priority_score", 0),
                }
                for c in candidates
            ]

            orch = {
                "recon": guardian_state.get("orchestration_recon") or {},
                "capability_digest": (guardian_state.get("capability_digest") or "")[:3200],
                "pre_decision_task_context": (guardian_state.get("pre_decision_task_context") or "")[:800],
                "relevant_capabilities": (guardian_state.get("relevant_capabilities") or [])[:14],
            }
            extra_rules: List[str] = []
            try:
                from .startup_runtime_guard import early_runtime_budget_active

                if early_runtime_budget_active():
                    extra_rules.append(
                        "SYSTEM_BOOT_WINDOW: Prefer fast, concrete tool/module/capability actions over long speculative "
                        "reasoning; avoid choices that imply a slow multi-step local think."
                    )
            except Exception:
                pass

            from .llm.prompted_call import log_prompted_call, prepare_prompted_bundle

            _planner_bundle = prepare_prompted_bundle(
                module_name=mod,
                agent_name=ag,
                task_text=(
                    "Select exactly one `chosen_action` from `available_actions` in STATE. "
                    "Return JSON only matching the host schema."
                ),
                extra_rules=extra_rules,
                output_schema={
                    "type": "decide_next_action",
                    "fields": [
                        "chosen_action",
                        "chosen_module",
                        "reasoning",
                        "confidence",
                        "needs_memory",
                        "ask_user_question",
                        "exploration_score",
                        "fallback_action",
                        "pre_recon_summary",
                        "capability_route",
                    ],
                },
                caller="MistralEngine.decide_next_action",
            )
            _stack_text = _planner_bundle["prompt_text"]
            _stack_meta = _planner_bundle["meta"]

            cp = _merged_context_pipeline_view(guardian_state)
            pkt = cp.get("context_pipeline_packet") or cp.get("prompt_packet")
            online_safe = cp.get("context_pipeline_online") or cp.get("structured_online")
            summ = cp.get("context_pipeline_summary") or {}
            retr = summ.get("retrieval") if isinstance(summ, dict) else {}
            evid = retr.get("evidence_snippets") if isinstance(retr, dict) else []
            inj = (cp.get("planner_injection") or "").strip() if isinstance(cp, dict) else ""
            use_struct = bool(pkt) or bool(online_safe)
            state_snap_cap = 1500 if use_struct else 2400

            prompt_parts = [
                "Mandatory sequence: read objective + memory hints + capability digest + scored actions, then choose.",
                "HARD RULE: If relevant_capabilities lists a tool/module/API with good match_score and health ok for this task, pick suggested_action (or equivalent) — do NOT default to vague local reasoning.",
                "Use H_api_vs_local in recon: when use_api is true and keys exist, prefer actions that route work to cloud tools (e.g. consider_prompt_evolution, consider_learning) over raw guessing.",
                "Priority: (1) internal specialized modules (2) registered agents/plugins (3) external APIs when keys on and task benefits (4) local reasoning only if nothing else fits.",
                "Do not spam APIs; prefer internal tools when they clearly fit.",
                "",
                "ORCHESTRATION_RECON (use this):",
                json.dumps(orch, indent=0)[:4200],
                "",
            ]
            if use_struct:
                prompt_parts.extend(
                    [
                        "STRUCTURED_CONTEXT_PACKET — authoritative distilled context (JSON). Treat as first-class state: "
                        "do not ignore; do not invent fields outside the schema; anything not grounded in facts/evidence is your inference only.",
                        json.dumps(pkt, ensure_ascii=False, indent=0)[:9000] if isinstance(pkt, dict) else "{}",
                        "",
                        "STRUCTURED_ONLINE_DECISION_SUPPORT — optional JSON (claim-validated; may omit unsafe fields). "
                        "Advisory only; not executable commands; unsupported remote claims were filtered out before this prompt.",
                        json.dumps(online_safe, ensure_ascii=False, indent=0)[:5000] if isinstance(online_safe, dict) else "{}",
                        "",
                        "SELECTED_EVIDENCE (traceability snippets):",
                        json.dumps(evid[:18], ensure_ascii=False, indent=0)[:6500],
                        "",
                    ]
                )
                logger.info(
                    "[DecisionLoop] structured_prompt_sections packet=%s online=%s evidence_n=%s",
                    bool(pkt),
                    bool(online_safe),
                    len(evid) if isinstance(evid, list) else 0,
                )
            elif inj:
                prompt_parts.extend(
                    [
                        "CONTEXT_PIPELINE_LEGACY_FALLBACK (text; use only if no structured packet above):",
                        inj[:8500],
                        "",
                    ]
                )
                logger.info("[DecisionLoop] planner_prompt_legacy_injection chars=%s", min(len(inj), 8500))
            prompt_parts.extend(
                [
                "State snapshot:",
                json.dumps({
                    "active_goal": guardian_state.get("active_goal"),
                    "recent_actions": guardian_state.get("recent_actions", [])[-5:],
                    "recent_outcomes": guardian_state.get("recent_outcomes", [])[-3:],
                    "last_action_outcome": guardian_state.get("last_action_outcome"),
                    "pending_operator_question": guardian_state.get("pending_operator_question"),
                    "memory_pressure_high": guardian_state.get("memory_pressure_high", False),
                    "memory_count": guardian_state.get("memory_count"),
                    "stagnation_count": guardian_state.get("stagnation_count", 0),
                    "memory_block_cycles_remaining": guardian_state.get("memory_block_cycles_remaining", 0),
                    "consecutive_memory_actions": guardian_state.get("consecutive_memory_actions", 0),
                    "available_actions": tools_list,
                    "module_cooldowns": guardian_state.get("module_cooldowns", {}),
                    "uncertainty_level": guardian_state.get("uncertainty_level", "unknown"),
                    "recent_governor_overrides": guardian_state.get("recent_governor_overrides", [])[-8:],
                    "active_override_penalties": guardian_state.get("active_override_penalties", [])[:12],
                    "adversarial_priority_penalty": guardian_state.get("adversarial_priority_penalty", 0),
                    "decision_cycle": guardian_state.get("decision_cycle", 0),
                    "moltbook_guidance": guardian_state.get("moltbook_guidance"),
                    "moltbook_guidance_captured_at": guardian_state.get("moltbook_guidance_captured_at"),
                    "moltbook_pages_visited": guardian_state.get("moltbook_pages_visited"),
                    "moltbook_stop_reason": guardian_state.get("moltbook_stop_reason"),
                    "chatlog_guidance": guardian_state.get("chatlog_guidance"),
                    "chatlog_guidance_captured_at": guardian_state.get("chatlog_guidance_captured_at"),
                }, indent=0)[:state_snap_cap],
                "",
                "Constraints: Pick ONLY from available_actions. Return valid JSON.",
                "Set needs_memory=true only if memory search/dream/learning is clearly needed.",
                "Set ask_user_question if the system should ask the operator (empty string otherwise).",
                "Set exploration_score 0.0-1.0 (higher = prefer underused/novel actions).",
                "",
                "MOLBOOK (automatic decision input): moltbook_guidance is a bounded read-only MoltBook scan summarizing "
                "operator-facing themes. Treat it as first-class external signal when non-empty: prefer actions that "
                "apply it (consider_mutation, execute_self_task, work_on_objective, consider_prompt_evolution, "
                "consider_learning, delegate_openclaw when it matches the goal). If guidance is empty/stale or "
                "moltbook_stop_reason suggests a thin readout, you may pick consider_moltbook_direction to refresh "
                "before large mutations or self-tasks.",
                "",
                "CRITICAL: Repetition is failure. Do NOT pick the same action as recent_actions.",
                "When stagnation_count > 0 or recent actions repeat: strongly prefer novel/underused actions.",
                "Exploration beats exploitation when progress is flat. Penalize repeated actions.",
                "",
                "Use E_scored_actions in recon: higher expected_value suggests better orchestration fit (usefulness minus cost/risk).",
                "If understanding_ready is false, strongly prefer code_analysis or tool_registry_pulse to map the system.",
                "Set pre_recon_summary to one line: what you learned from recon + which capability you will lean on.",
                "Set capability_route to one of: internal_module | agent_plugin | external_api | local_only",
                "",
                "Explore modules and agents: Prefer actions that run different subsystems (consider_learning, consider_dream_cycle, "
                "consider_prompt_evolution, consider_adversarial_learning, code_analysis, question_probe, harvest_income_report, "
                "income_modules_pulse, tool_registry_pulse, delegate_openclaw) to discover system state. "
                "When uncertain, choose an exploratory action over execute_task or work_on_objective.",
                "",
                "If recent_governor_overrides lists (action, reason) for the same action you were about to pick, choose a DIFFERENT action "
                "that matches the constraint (e.g. needs_memory=true for learning/dream when memory actions were blocked for needs_memory_false; "
                "avoid dream when memory_pressure_high; prefer fractalmind_planning, code_analysis, question_probe when learning was repeatedly overridden).",
                "Do NOT repeat an action listed in active_override_penalties with the same reason you just violated.",
            ]
            )

            decider_cfg = self._load_decider_config()
            base_temp = float(decider_cfg.get("mistral_decision_temperature", 0.3))
            override_temp = float(decider_cfg.get("mistral_decision_temperature_after_overrides", 0.42))
            recent_ov = guardian_state.get("recent_governor_overrides") or []
            temperature = override_temp if len(recent_ov) >= 1 else base_temp
            if temperature != base_temp:
                logger.debug("[Mistral] temperature=%.2f (elevated: recent governor overrides=%d)", temperature, len(recent_ov))

            user_blob = "\n".join(prompt_parts)
            use_broker = bool(decider_cfg.get("use_llm_orchestration_broker", True))
            governance_hints = list(governance_hints or []) if governance_hints is not None else []

            _combined_len = len(_stack_text) + len(user_blob)
            log_prompted_call(
                module_name=mod,
                agent_name=ag,
                task_type="decide_next_action",
                provider="ollama_orchestration_broker" if use_broker else "ollama",
                model=self.model,
                bundle_meta=_stack_meta,
                prompt_length=_combined_len,
                legacy_prompt_path=False,
            )

            if use_broker:
                pr = None
                try:
                    from .orchestration import TaskRequest, get_orchestration_broker

                    req = TaskRequest(
                        task_id=f"decider_{guardian_state.get('decision_cycle', 0)}",
                        task_type="reasoning",
                        prompt=_stack_text + "\n\n---\n\n" + user_blob,
                        context={
                            "uncertainty_level": guardian_state.get("uncertainty_level", "unknown"),
                        },
                        metadata={
                            "governance_hints": governance_hints,
                            "ollama_json_schema": _DECIDE_NEXT_ACTION_SCHEMA,
                            "review_rubric_keys": ["chosen_action", "reasoning", "confidence"],
                            "executor_temperature": temperature,
                            "planner_temperature": min(0.45, temperature + 0.05),
                            "context_pipeline_packet": guardian_state.get("context_pipeline_packet"),
                            "context_pipeline_online": guardian_state.get("context_pipeline_online"),
                        },
                    )
                    pr = get_orchestration_broker().run_task_sync(req)
                    out: Dict[str, Any]
                    if pr.success and pr.final_output is not None:
                        fo = pr.final_output
                        if isinstance(fo, dict):
                            out = fo
                        elif isinstance(fo, str) and fo.strip():
                            try:
                                out = json.loads(fo)
                            except Exception:
                                out = {}
                        else:
                            out = {}
                        if out:
                            parsed = self._parse_decide_response(out, candidates, guardian_state)
                            note_planner_success()
                            _lat_box[0] = True
                            return parsed
                        note_planner_failure("broker_no_valid_output", is_timeout=False)
                        broker_transport_hint = broker_transport_hint or orchestration_broker_suggests_transport_failure(
                            pr
                        )
                    else:
                        note_planner_failure("broker_pipeline_failed", is_timeout=False)
                        broker_transport_hint = broker_transport_hint or orchestration_broker_suggests_transport_failure(
                            pr
                        )
                except Exception as e:
                    logger.debug("[Mistral] orchestration broker failed, using direct Ollama: %s", e)
                    note_planner_failure("broker_exception", is_timeout=False)
                    broker_transport_hint = broker_transport_hint or orchestration_broker_suggests_transport_failure(
                        pr, e
                    )

            if broker_transport_hint:
                logger.info(
                    "[Mistral] Broker path reported transport-like failure; trying direct Ollama (model=%s)",
                    self.model,
                )

            h = self._ensure_ollama()
            if not h.ok:
                logger.error("[Mistral] Direct planner path unavailable (Ollama): %s", h.detail)
                note_planner_failure("ollama_health", is_timeout=False)
                return self._decide_fallback_empty(
                    guardian_state,
                    planner_transport_failed=True,
                    broker_upstream_transport_hint=broker_transport_hint,
                )

            payload = {
                "model": self.model,
                "stream": False,
                "format": _DECIDE_NEXT_ACTION_SCHEMA,
                "messages": [
                    {
                        "role": "system",
                        "content": _stack_text
                        + "\n\nYou return ONLY valid JSON matching the schema. No markdown.",
                    },
                    {"role": "user", "content": user_blob},
                ],
                "options": {"temperature": temperature},
            }

            to = self._ollama_http_timeout()
            try:
                data = self._post_ollama(payload, timeout=to)
                content = data.get("message", {}).get("content", "{}")
                if isinstance(content, dict):
                    out = content
                else:
                    out = json.loads(content) if isinstance(content, str) else {}
            except Exception as e:
                is_to = False
                try:
                    import requests

                    is_to = isinstance(e, requests.exceptions.Timeout)
                except Exception:
                    is_to = "timeout" in str(e).lower()
                logger.warning("[Mistral] decide_next_action request failed: %s", e)
                note_planner_failure("ollama_request", is_timeout=is_to)
                return self._decide_fallback_empty(
                    guardian_state,
                    planner_transport_failed=True,
                    broker_upstream_transport_hint=broker_transport_hint,
                )

            parsed = self._parse_decide_response(out, candidates, guardian_state)
            note_planner_success()
            _lat_box[0] = True
            return parsed

        try:
            return _planner_body()
        finally:
            try:
                from .planner_readiness import record_planner_latency_ms

                record_planner_latency_ms(
                    (time.perf_counter() - _t_planner) * 1000,
                    success=_lat_box[0],
                )
            except Exception:
                pass

    def _parse_decide_response(
        self, raw: Dict[str, Any], candidates: List[Dict], state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parse and validate Mistral response; fill defaults if malformed."""
        action_names = {c.get("action") for c in candidates if c.get("action")}
        chosen_raw = (raw.get("chosen_action") or "").strip()
        chosen = chosen_raw
        if chosen not in action_names:
            chosen = raw.get("fallback_action") or ""
        if chosen not in action_names and candidates:
            chosen = candidates[0].get("action", "")

        confidence = raw.get("confidence")
        if confidence is None or not isinstance(confidence, (int, float)):
            confidence = 0.5
        confidence = max(0.0, min(1.0, float(confidence)))

        ask_user_question = (raw.get("ask_user_question") or "").strip()[:200]
        pre_recon_summary = (raw.get("pre_recon_summary") or "").strip()[:300]
        cp = _merged_context_pipeline_view(state)
        so = cp.get("context_pipeline_online") or cp.get("structured_online")
        val = cp.get("context_pipeline_validation") or {}
        decision_safe = bool(val.get("decision_safe"))
        risk_safe = bool(val.get("risk_safe"))
        structured_online_decision: Optional[str] = None
        structured_online_risks: List[str] = []
        merge_ok = isinstance(so, dict) and decision_safe
        risk_merge_ok = isinstance(so, dict) and risk_safe
        merge_mi = val.get("mergeable_missing_info") if isinstance(val, dict) else None
        merge_ns = val.get("mergeable_next_steps") if isinstance(val, dict) else None
        merge_rk = val.get("mergeable_risks") if isinstance(val, dict) else None
        if merge_ok:
            structured_online_decision = (so.get("decision") or "").strip()[:500] or None
            mi = merge_mi if isinstance(merge_mi, list) and merge_mi else (so.get("missing_info") or [])
            if mi:
                extra = "; ".join(str(x) for x in mi[:4] if str(x).strip())
                if extra and extra not in ask_user_question:
                    ask_user_question = (ask_user_question + " | " + extra).strip()[:200]
            ns = merge_ns if isinstance(merge_ns, list) and merge_ns else (so.get("next_steps") or [])
            if ns:
                join = "; ".join(str(x) for x in ns[:3] if str(x).strip())
                if join:
                    pre_recon_summary = (pre_recon_summary + " | online_next: " + join).strip()[:300]
        if risk_merge_ok:
            rk_src = merge_rk if isinstance(merge_rk, list) and merge_rk else (so.get("risks") or [])
            structured_online_risks = [str(x)[:200] for x in rk_src[:8] if str(x).strip()]  # type: ignore[union-attr]
        elif isinstance(so, dict) and so and not risk_safe:
            logger.info("[DecisionLoop] structured_online_risks_skipped risk_safe=false")

        if isinstance(so, dict) and so and not decision_safe:
            logger.info(
                "[DecisionLoop] structured_online_present_but_not_merged decision_safe=%s risk_safe=%s",
                decision_safe,
                risk_safe,
            )

        pkt = cp.get("context_pipeline_packet") or cp.get("prompt_packet")
        used_packet = bool(pkt)
        used_online = bool(so) and (merge_ok or risk_merge_ok)
        changed = False
        if merge_ok and structured_online_decision:
            od = structured_online_decision.lower()
            if od and (od in chosen_raw.lower() or chosen_raw.lower() in od):
                changed = True
        if not changed and merge_ok and isinstance(so, dict):
            ns_join = " ".join(str(x) for x in (so.get("next_steps") or [])[:6]).lower()
            if chosen_raw and chosen_raw.lower() in ns_join:
                changed = True
        if not changed and risk_merge_ok and isinstance(so, dict):
            rk_join = " ".join(str(x) for x in (so.get("risks") or [])[:6]).lower()
            if chosen_raw and chosen_raw.replace("_", " ").lower() in rk_join:
                changed = True
        basis_parts: List[str] = []
        if used_packet:
            basis_parts.append("local_packet")
        if merge_ok:
            basis_parts.append("online_guidance")
        elif risk_merge_ok:
            basis_parts.append("online_risks_only")
        if not basis_parts:
            basis_parts.append("raw_state")

        out = {
            "chosen_action": chosen,
            "chosen_module": raw.get("chosen_module", ""),
            "reasoning": raw.get("reasoning", "No reasoning")[:200],
            "confidence": confidence,
            "needs_memory": bool(raw.get("needs_memory", False)),
            "ask_user_question": ask_user_question,
            "exploration_score": max(0.0, min(1.0, float(raw.get("exploration_score", 0.5)))),
            "fallback_action": raw.get("fallback_action") or (candidates[1].get("action") if len(candidates) > 1 else ""),
            "pre_recon_summary": pre_recon_summary,
            "capability_route": (raw.get("capability_route") or "").strip()[:80],
        }
        if structured_online_decision:
            out["structured_online_decision"] = structured_online_decision
        if structured_online_risks:
            out["structured_online_risks"] = structured_online_risks
        trace = {
            "used_context_pipeline_packet": used_packet,
            "used_structured_online_support": used_online,
            "structured_support_changed_decision": changed,
            "decision_basis_summary": ",".join(basis_parts),
            "raw_state_only": not used_packet and not used_online,
        }
        out["_pipeline_trace"] = trace
        out["used_context_pipeline_packet"] = used_packet
        out["used_structured_online_support"] = used_online
        out["structured_support_changed_decision"] = changed
        out["decision_basis_summary"] = trace["decision_basis_summary"]
        logger.info(
            "[DecisionLoop] used_packet=%s used_online=%s changed_decision=%s parsed_chosen=%s conf=%.2f",
            used_packet,
            used_online,
            changed,
            chosen,
            confidence,
        )
        return out

    def suggest_learning_targets(
        self,
        context: str,
        round_index: int,
        already_tried: Optional[Dict[str, List[str]]] = None,
        *,
        module_name: str,
        agent_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Plan next X / Reddit / Wikipedia / Google (Custom Search API) lookups from prior context
        (ChatGPT snippets, memory, last round).
        Returns keys: twitter_queries, reddit_subreddits_new, reddit_searches, wikipedia_titles,
        google_queries, reasoning.
        """
        already_tried = already_tried or {}
        tw = _clean_learning_history_values(already_tried.get("twitter"))
        rs = _clean_learning_history_values(already_tried.get("reddit_search"))
        wiki = _clean_learning_history_values(already_tried.get("wikipedia"))
        ggl = _clean_learning_history_values(already_tried.get("google"))
        context_excerpt = _compact_learning_context(context)
        try:
            import requests
        except ImportError:
            logger.warning("[Mistral] suggest_learning_targets: requests not installed")
            return {}

        try:
            from .startup_runtime_guard import early_runtime_budget_active, startup_memory_thin_mode_active

            if early_runtime_budget_active() or startup_memory_thin_mode_active():
                logger.info(
                    "[Mistral] suggest_learning_targets skipped (early_runtime_budget or memory-thin)"
                )
                return {}
        except Exception:
            pass

        from .llm.prompted_call import log_prompted_call, prepare_prompted_bundle, require_prompt_profile

        mod, ag, _ = require_prompt_profile(
            module_name, agent_name, caller="MistralEngine.suggest_learning_targets", allow_legacy=False
        )

        _lt_bundle = prepare_prompted_bundle(
            module_name=mod,
            agent_name=ag,
            task_text=f"Plan the NEXT web learning fetches. Round {round_index + 1}.",
            context={
                "already_tried": {"twitter": tw, "reddit_search": rs, "wikipedia": wiki, "google": ggl},
                "context_excerpt": context_excerpt,
            },
            extra_rules=[
                "Execution uses external APIs (X, Reddit, Wikipedia, Google Custom Search when operator configured keys) — choose targets/queries only; do not replace fetchers with generic chat answers.",
                "Use snippets and memory to pick NEW queries; avoid repeating already_tried.",
                "twitter_queries: simple phrases; reddit_subreddits_new: names for /new; reddit_searches: subreddit+q objects; wikipedia_titles: English titles; google_queries: short web search phrases (same style as a Google search box).",
                "Prefer AI, systems, automation, and threads that deepen context.",
                "Keep the plan tight: at most 1 twitter_query, 2 reddit_subreddits_new, 2 reddit_searches, 1 wikipedia_title, and 1 google_query.",
                "Keep reasoning short and concrete.",
            ],
            output_schema={"type": "learning_targets", "schema": "see _LEARNING_TARGETS_SCHEMA"},
            caller="MistralEngine.suggest_learning_targets",
        )
        log_prompted_call(
            module_name=mod,
            agent_name=ag,
            task_type="suggest_learning_targets",
            provider="ollama",
            model=self.model,
            bundle_meta=_lt_bundle["meta"],
            prompt_length=len(_lt_bundle["prompt_text"]),
            legacy_prompt_path=False,
        )
        user = _lt_bundle["prompt_text"]
        payload = {
            "model": self.model,
            "stream": False,
            "format": _LEARNING_TARGETS_SCHEMA,
            "messages": [
                {"role": "system", "content": "You return ONLY valid JSON matching the schema. No markdown."},
                {"role": "user", "content": user},
            ],
            "options": {"temperature": 0.25},
        }
        try:
            if not self._ensure_ollama().ok:
                raise RuntimeError(self._ollama_health.detail if self._ollama_health else "ollama_unavailable")
            try:
                lt_cap = float(os.environ.get("ELYSIA_LEARNING_TARGET_OLLAMA_TIMEOUT_SEC", "90"))
            except ValueError:
                lt_cap = 90.0
            if (os.environ.get("ELYSIA_LEARNING_LOCAL_PRIORITY", "").strip().lower() in ("1", "true", "yes", "on")):
                lt_cap = max(lt_cap, 150.0)
            lt_cap = min(300.0, max(24.0, lt_cap))
            data = self._post_ollama(payload, timeout=self._ollama_http_timeout(max(18.0, lt_cap)))
            content = data.get("message", {}).get("content", "{}")
            if isinstance(content, dict):
                return content
            return json.loads(content) if isinstance(content, str) else {}
        except Exception as e:
            logger.warning("[Mistral] suggest_learning_targets failed: %s", e)
            return {}

    def _decide_fallback_empty(
        self,
        guardian_state: Dict[str, Any],
        *,
        planner_transport_failed: bool = False,
        broker_upstream_transport_hint: bool = False,
    ) -> Dict[str, Any]:
        """Fallback when no candidates or Mistral unavailable."""
        out: Dict[str, Any] = {
            "chosen_action": "continue_monitoring",
            "chosen_module": "",
            "reasoning": "No candidates or Mistral unavailable",
            "confidence": 0.0,
            "needs_memory": False,
            "ask_user_question": "",
            "exploration_score": 0.0,
            "fallback_action": "continue_monitoring",
            "pre_recon_summary": "",
            "capability_route": "local_only",
        }
        if planner_transport_failed or broker_upstream_transport_hint:
            out["_planner_transport_failed"] = True
        return out


def warm_mistral_model(model: Optional[str] = None, ollama_url: Optional[str] = None) -> bool:
    """Verify Ollama at startup: tags + canonical install + health (delegates to planner_readiness)."""
    from .planner_readiness import run_startup_planner_probe

    snap = run_startup_planner_probe(log_tags_on_fail=True)
    return bool(snap.get("startup_health_ok") and snap.get("model_installed"))


if __name__ == "__main__":
    # Temporary test - run when Ollama is available: python -m project_guardian.mistral_engine
    engine = MistralEngine()
    try:
        result = engine.decide(
            goal="Fix failing system loop",
            state={"failures": 3},
            tools=[
                {"name": "run_diagnostic"},
                {"name": "create_task"},
                {"name": "ask_user"},
            ],
            module_name="router",
        )
        print(result)
    except Exception as e:
        print(f"Error (Ollama may not be running): {e}")

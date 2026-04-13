"""
AI Tool Registry - Manages AI tools, capabilities, and routing
Integrated from old modules.
"""

import datetime
import json
import logging
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Non–health-probe TaskRouter.route_task calls only (observability; does not affect routing).
_TASK_ROUTER_REAL_ROUTE_METRICS: Dict[str, Any] = {
    "real_route_events": 0,
    "tie_at_winner_count_gt1": 0,
    "by_task_type": defaultdict(int),  # type: ignore[arg-type]
}
_TASK_ROUTER_ROUTE_METRICS_LOG_EVERY = 25


def get_task_router_real_route_metrics_snapshot() -> Dict[str, Any]:
    m = _TASK_ROUTER_REAL_ROUTE_METRICS
    return {
        "real_route_events": int(m["real_route_events"]),
        "tie_at_winner_count_gt1": int(m["tie_at_winner_count_gt1"]),
        "by_task_type": dict(m["by_task_type"]),
    }


def reset_task_router_real_route_metrics() -> None:
    """Zero cumulative counters (tests / manual diagnostics)."""
    m = _TASK_ROUTER_REAL_ROUTE_METRICS
    m["real_route_events"] = 0
    m["tie_at_winner_count_gt1"] = 0
    m["by_task_type"] = defaultdict(int)


class ToolRegistry:
    """Registry for managing AI tools and their capabilities"""
    
    def __init__(self):
        self.tools = {}
        self.revoked = set()
        self.log = []
    
    def add_tool(self, tool_id: str, metadata: Dict[str, Any]) -> str:
        """
        Add a tool to the registry.
        
        Args:
            tool_id: Unique tool identifier
            metadata: Tool metadata (provider, capabilities, benchmarks, etc.)
        
        Returns:
            Status message
        """
        if tool_id in self.revoked:
            return f"Tool {tool_id} is revoked and cannot be re-added."
        
        self.tools[tool_id] = {
            "id": tool_id,
            "added_at": str(datetime.datetime.now()),
            **metadata
        }
        
        entry = f"[{datetime.datetime.now()}] Added tool {tool_id}: {metadata.get('provider', 'unknown')}"
        self.log.append(entry)
        logging.info(entry)
        
        return f"Tool {tool_id} added successfully."
    
    def revoke_tool(self, tool_id: str) -> str:
        """
        Revoke a tool from the registry.
        
        Args:
            tool_id: Tool identifier to revoke
        
        Returns:
            Status message
        """
        if tool_id in self.tools:
            self.revoked.add(tool_id)
            del self.tools[tool_id]
            entry = f"[{datetime.datetime.now()}] Revoked tool {tool_id}"
            self.log.append(entry)
            logging.info(entry)
            return f"Tool {tool_id} revoked and removed."
        return f"Tool {tool_id} not found."
    
    def get_tool(self, tool_id: str) -> Dict[str, Any]:
        """Get tool metadata by ID"""
        return self.tools.get(tool_id, {"status": "not_found"})
    
    def tools_map(self) -> Dict[str, Dict[str, Any]]:
        """Active tool id -> metadata (revoked excluded); safe for export / routing."""
        out: Dict[str, Dict[str, Any]] = {}
        try:
            for tid in list(self.tools.keys()):
                if tid in self.revoked:
                    continue
                meta = self.tools.get(tid)
                if isinstance(meta, dict):
                    out[tid] = meta
                else:
                    out[tid] = {"id": tid, "raw": meta}
        except Exception as e:
            logging.getLogger(__name__).debug("tools_map: %s", e)
        return out

    def list_tools(self) -> List[str]:
        """Tool ids for orchestration (must be a list — callers slice [:n]; dict[:n] raises KeyError)."""
        try:
            return [tid for tid in self.tools if tid not in self.revoked]
        except Exception:
            return []

    def tool_registry_diagnostic_counts(self) -> Dict[str, int]:
        """
        Compact population counts for toolsurface logs.
        storage_entries = len(self.tools); active_listed = ids returned by list_tools();
        revoked_ids_tracked = len(self.revoked) (historical revokes; entries are removed from tools).
        """
        try:
            storage = len(self.tools)
            active = len([tid for tid in self.tools if tid not in self.revoked])
            return {
                "storage_entries": storage,
                "active_listed": active,
                "revoked_ids_tracked": len(self.revoked),
            }
        except Exception:
            return {"storage_entries": -1, "active_listed": -1, "revoked_ids_tracked": -1}

    def ensure_minimal_builtin_tools(self) -> None:
        """
        Idempotent stub tools so orchestration sees a non-empty catalog (no external APIs).
        Mirrors project_guardian.ai_tool_registry_engine.ensure_minimal_builtin_tools intent.
        """
        builtins: List[Tuple[str, Dict[str, Any]]] = [
            (
                "elysia_builtin_llm",
                {
                    "provider": "builtin",
                    "capabilities": ["llm", "chat", "completion", "general"],
                    "api_endpoint": "local://llm",
                    "builtin_stub": True,
                },
            ),
            (
                "elysia_builtin_web",
                {
                    "provider": "builtin",
                    "capabilities": ["web", "http", "fetch", "general"],
                    "api_endpoint": "local://web",
                    "builtin_stub": True,
                },
            ),
            (
                "elysia_builtin_exec",
                {
                    "provider": "builtin",
                    "capabilities": ["exec", "run", "script", "general"],
                    "api_endpoint": "local://exec",
                    "builtin_stub": True,
                },
            ),
            (
                "elysia_bounded_browser",
                {
                    "provider": "builtin",
                    # Intentionally no "fetch"/"web"/"general" — avoids stealing simple URL fetches.
                    "capabilities": ["bounded_browse"],
                    "api_endpoint": "local://bounded_browser",
                    "builtin_stub": True,
                },
            ),
            (
                "elysia_moltbook_browser",
                {
                    "provider": "builtin",
                    "capabilities": ["moltbook_browse"],
                    "api_endpoint": "local://moltbook_browser",
                    "builtin_stub": True,
                },
            ),
            (
                "elysia_social_intel",
                {
                    "provider": "builtin",
                    "capabilities": ["social_moltbook_observe"],
                    "api_endpoint": "local://social_intel",
                    "builtin_stub": True,
                },
            ),
        ]
        log = logging.getLogger(__name__)
        for name, meta in builtins:
            if name in self.tools:
                continue
            try:
                self.add_tool(name, meta)
            except Exception as e:
                log.debug("ensure_minimal_builtin_tools %s: %s", name, e)
    
    def get_log(self, limit: Optional[int] = None) -> List[str]:
        """Get registry log entries"""
        if limit:
            return self.log[-limit:]
        return self.log
    
    def export_registry_json(self) -> str:
        """Export registry as JSON string"""
        return json.dumps({
            "tools": self.tools_map(),
            "revoked": list(self.revoked),
            "log": self.log[-50:]  # Last 50 entries
        }, indent=2)
    
    def identify_mutation_candidates(self, threshold_score: float = 50.0) -> List[Tuple[str, float]]:
        """
        Identify tools that may need mutation/improvement.
        
        Args:
            threshold_score: Minimum score threshold
        
        Returns:
            List of (tool_id, score) tuples
        """
        candidates = []
        for tid, tool in self.tools_map().items():
            benchmarks = tool.get('benchmarks', {})
            score = ToolScorer.score_tool_static(benchmarks)
            if score < threshold_score:
                candidates.append((tid, score))
        return candidates


class CapabilityBenchmark:
    """Benchmark tool capabilities"""
    
    def __init__(self, tool_id: str):
        self.tool_id = tool_id
        self.results = {}
    
    def run_tests(self, test_suite: Dict[str, callable]) -> Dict[str, Any]:
        """
        Run benchmark tests.
        
        Args:
            test_suite: Dictionary of test_name -> test_function
        
        Returns:
            Test results dictionary
        """
        for test_name, test_func in test_suite.items():
            try:
                self.results[test_name] = test_func()
            except Exception as e:
                self.results[test_name] = f"Error: {str(e)}"
        return self.results


class ToolScorer:
    """Score tools based on benchmarks"""
    
    @staticmethod
    def score_tool_static(benchmarks: Dict[str, Any]) -> float:
        """
        Calculate tool score from benchmarks.
        
        Scoring formula:
        - Accuracy: 40% weight
        - Speed: 30% weight (faster = better)
        - Cost: 30% weight (cheaper = better)
        
        Args:
            benchmarks: Dictionary with speed, accuracy, cost
        
        Returns:
            Score (0-100)
        """
        try:
            # Parse speed (e.g., "120ms" -> 120)
            speed_str = str(benchmarks.get("speed", "0ms"))
            speed = float(speed_str.replace("ms", "").strip())
            
            # Parse accuracy (e.g., "92%" -> 92)
            accuracy_str = str(benchmarks.get("accuracy", "0%"))
            accuracy = float(accuracy_str.replace("%", "").strip())
            
            # Parse cost (e.g., "$0.002/call" -> 0.002)
            cost_str = str(benchmarks.get("cost", "$0"))
            cost = float(cost_str.replace("$", "").replace("/call", "").strip())
            
            # Calculate weighted score
            accuracy_score = accuracy * 0.4
            speed_score = max(0, (1000 - speed) / 10) * 0.3  # Normalize speed
            cost_score = max(0, (1.0 - cost) * 100) * 0.3  # Normalize cost
            
            score = accuracy_score + speed_score + cost_score
            return min(100.0, max(0.0, score))
        except Exception as e:
            logging.error(f"Error scoring tool: {e}")
            return 0.0


class MetaCoderAdapter:
    """Adapter generator for tools"""
    
    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry
    
    def generate_adapter(self, tool_id: str, api_docs: str) -> str:
        """
        Generate adapter code for a tool.
        
        Args:
            tool_id: Tool identifier
            api_docs: API documentation string
        
        Returns:
            Generated adapter code
        """
        adapter_code = f"""# Auto-generated adapter for {tool_id}
# Generated: {datetime.datetime.now()}
# Based on API docs: {api_docs[:200]}...

class {tool_id}Adapter:
    def __init__(self):
        self.tool_id = "{tool_id}"
    
    def execute(self, method: str, payload: dict):
        # TODO: Implement adapter logic
        pass
"""
        
        if tool_id in self.tool_registry.tools:
            self.tool_registry.tools[tool_id]['adapter_code'] = adapter_code
        
        entry = f"[{datetime.datetime.now()}] Adapter generated for {tool_id}"
        self.tool_registry.log.append(entry)
        logging.info(entry)
        
        return adapter_code
    
    def queue_mutations_for_weak_tools(self, threshold: float = 50.0) -> List[str]:
        """
        Queue mutations for tools with low scores.
        
        Args:
            threshold: Score threshold
        
        Returns:
            List of queued tool IDs
        """
        weak_tools = self.tool_registry.identify_mutation_candidates(threshold)
        queued = []
        
        for tid, score in weak_tools:
            entry = f"[{datetime.datetime.now()}] Queued mutation to improve adapter for {tid} (score={score:.2f})"
            self.tool_registry.log.append(entry)
            queued.append(tid)
            logging.info(entry)
        
        return queued


def _first_tool_id_in_map_order(tools: Dict[str, Any], candidates: List[str]) -> str:
    """Among candidates, return the first tool id in tools iteration order (legacy tie behavior)."""
    cset = set(candidates)
    for tid in tools.keys():
        if tid in cset:
            return tid
    return candidates[0]


class TaskRouter:
    """Route tasks to appropriate tools"""
    
    def __init__(self, tool_registry: ToolRegistry, priority_registry: Optional[Dict[str, Any]] = None):
        """
        Initialize Task Router.
        
        Args:
            tool_registry: Tool registry instance
            priority_registry: Optional priority settings
        """
        self.tool_registry = tool_registry
        self.priority_registry = priority_registry or {}

    def _candidate_route_score(self, task_type: str, data: Dict[str, Any]) -> Optional[float]:
        """Score for one tool if it matches task_type (or 'general'); else None. Same formula as route_task loop."""
        capabilities = data.get('capabilities', [])
        if not (task_type in capabilities or 'general' in capabilities):
            return None
        benchmarks = data.get('benchmarks', {})
        score = ToolScorer.score_tool_static(benchmarks)
        if self.priority_registry.get("cost_sensitive"):
            score *= 0.9
        if self.priority_registry.get("accuracy_required"):
            score *= 1.1
        if self.priority_registry.get("speed_required"):
            speed = float(str(benchmarks.get("speed", "1000ms")).replace("ms", ""))
            if speed < 500:
                score *= 1.1
        return score

    def _resolve_tie_among_winners(
        self,
        task_type: str,
        winners: List[str],
        tools: Dict[str, Dict[str, Any]],
        *,
        is_health_probe: bool,
    ) -> Tuple[str, str]:
        """
        Pick one winner among tools tied at the max score.
        Health probe: unchanged legacy behavior (first tool id in registry map order).
        Real tasks: prefer explicit capability tag matches, then light keyword hints,
        then web→exec→llm for generic stub ties (reduces LLM-first collapse on `general`-only matches).
        """
        if len(winners) == 1:
            return winners[0], "unique_winner"
        if is_health_probe:
            return _first_tool_id_in_map_order(tools, winners), "health_probe_map_order"
        tt = (task_type or "").strip()
        tt_l = tt.lower()
        ws = set(winners)
        # Prefer a single tool that lists this exact task_type in capabilities (not via general alone).
        explicit = [w for w in winners if tt in (tools.get(w) or {}).get("capabilities", [])]
        if len(explicit) == 1:
            return explicit[0], "sole_explicit_capability_tag"
        # Keyword hints on task_type string (narrow; does not change global scoring).
        if tt_l == "bounded_browse" and "elysia_bounded_browser" in ws:
            return "elysia_bounded_browser", "keyword_hint_bounded_browse"
        if tt_l == "social_moltbook_observe" and "elysia_social_intel" in ws:
            return "elysia_social_intel", "keyword_hint_social_moltbook_observe"
        if tt_l == "moltbook_browse" and "elysia_moltbook_browser" in ws:
            return "elysia_moltbook_browser", "keyword_hint_moltbook_browse"
        if any(k in tt_l for k in ("web", "http", "fetch", "url", "browse", "scrape")):
            if "elysia_builtin_web" in ws:
                return "elysia_builtin_web", "keyword_hint_web"
        if any(k in tt_l for k in ("exec", "shell", "script", "run", "python", "bash")):
            if "elysia_builtin_exec" in ws:
                return "elysia_builtin_exec", "keyword_hint_exec"
        if any(
            k in tt_l
            for k in ("text-gen", "chat", "completion", "llm", "reasoning", "summarize", "unified", "prompt")
        ):
            if "elysia_builtin_llm" in ws:
                return "elysia_builtin_llm", "keyword_hint_llm"
        # Generic orchestration task types: stub ties often match only via "general" — rotate away from pure LLM-first.
        if tt_l == "self_task" or (tt_l.endswith("_task") and "routing_probe" not in tt_l):
            for pref in ("elysia_builtin_web", "elysia_builtin_exec", "elysia_builtin_llm"):
                if pref in ws:
                    return pref, "general_stub_tie_order_web_exec_llm"
        return _first_tool_id_in_map_order(tools, winners), "map_order_fallback"
    
    def route_task(self, task_type: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Route a task to the best available tool.
        
        Args:
            task_type: Type of task (e.g., "text-gen", "image-gen")
            context: Optional context dictionary
        
        Returns:
            Routing result dictionary
        """
        tools = self.tool_registry.tools_map()
        ctx = context if isinstance(context, dict) else {}
        is_health_probe = bool(ctx.get("_guardian_router_health_probe"))

        scores: Dict[str, float] = {}
        for tid, data in tools.items():
            s = self._candidate_route_score(task_type, data)
            if s is not None:
                scores[tid] = s

        tie_break_reason = "no_candidates"
        if not scores:
            best_tool, best_score = None, -1.0
        else:
            best_score = max(scores.values())
            winners = [tid for tid, sc in scores.items() if abs(float(sc) - float(best_score)) < 1e-9]
            best_tool, tie_break_reason = self._resolve_tie_among_winners(
                task_type,
                winners,
                tools,
                is_health_probe=is_health_probe,
            )
        
        route_entry = f"[{datetime.datetime.now()}] Routed task '{task_type}' to tool: {best_tool if best_tool else 'No suitable tool found'}"
        self.tool_registry.log.append(route_entry)
        logging.info(route_entry)
        
        out: Dict[str, Any] = {
            "task_type": task_type,
            "routed_to": best_tool,
            "score": best_score,
            "available_tools": len([t for t in tools.values() if task_type in t.get('capabilities', [])]),
        }
        # Real tasks only: surface who won and nearby scores (health probe unchanged).
        if not is_health_probe:
            scored: List[Tuple[str, float]] = []
            for tid, data in tools.items():
                s = self._candidate_route_score(task_type, data)
                if s is not None:
                    scored.append((tid, round(float(s), 4)))
            scored.sort(key=lambda x: -x[1])
            top_scored = scored[:6]
            near_tie = [
                (tid, sc)
                for tid, sc in scored
                if best_tool is not None and abs(sc - float(best_score)) < 1e-6
            ]
            logger.info(
                "[TaskRouter] real_task_route task_type=%s routed_to=%s score=%s "
                "strict_capability_tag_matches=%s top_scored=%s tied_at_winner=%s tie_break=%s",
                task_type,
                best_tool,
                best_score,
                out["available_tools"],
                top_scored,
                near_tie,
                tie_break_reason,
            )
            rm = _TASK_ROUTER_REAL_ROUTE_METRICS
            rm["real_route_events"] = int(rm["real_route_events"]) + 1
            if len(near_tie) > 1:
                rm["tie_at_winner_count_gt1"] = int(rm["tie_at_winner_count_gt1"]) + 1
            rm["by_task_type"][str(task_type)] += 1
            ne = int(rm["real_route_events"])
            if ne % _TASK_ROUTER_ROUTE_METRICS_LOG_EVERY == 0:
                logger.info(
                    "[TaskRouter] real_route_metrics cumulative=%s",
                    get_task_router_real_route_metrics_snapshot(),
                )
        # Guardian registry health probe only: explain ties / pick rule without changing routed_to.
        if ctx.get("_guardian_router_health_probe") and best_tool is not None:
            tied = []
            for tid, data in tools.items():
                s = self._candidate_route_score(task_type, data)
                if s is not None and abs(s - best_score) < 1e-9:
                    tied.append(tid)
            out["diagnostic_tied_tools_at_winner_score"] = tied
            out["diagnostic_pick_rule"] = "max_score_then_first_in_tools_map_order"
        return out


# Example usage
if __name__ == "__main__":
    registry = ToolRegistry()
    
    # Add a tool with benchmarks
    benchmark = CapabilityBenchmark("example_ai")
    results = benchmark.run_tests({
        "speed": lambda: "120ms",
        "accuracy": lambda: "92%",
        "cost": lambda: "$0.002/call"
    })
    
    registry.add_tool("example_ai", {
        "provider": "OpenAI",
        "capabilities": ["text-gen", "general"],
        "benchmarks": results,
        "api_doc_url": "https://api.example.com/docs"
    })
    
    # Generate adapter
    metacoder = MetaCoderAdapter(registry)
    adapter_code = metacoder.generate_adapter("example_ai", "Sample API doc content...")
    print("Generated Adapter:")
    print(adapter_code)
    
    # Route a task
    priority = {"cost_sensitive": True, "accuracy_required": True}
    router = TaskRouter(registry, priority_registry=priority)
    routing_result = router.route_task("text-gen")
    print("\nRouting Result:")
    print(json.dumps(routing_result, indent=2))
    
    # Export registry
    print("\n=== Tool Registry Export ===")
    print(registry.export_registry_json())


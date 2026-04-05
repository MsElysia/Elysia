"""
AI Tool Registry - Manages AI tools, capabilities, and routing
Integrated from old modules.
"""

import datetime
import json
import logging
from typing import Dict, List, Any, Optional, Tuple


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
        best_tool = None
        best_score = -1.0
        
        for tid, data in tools.items():
            capabilities = data.get('capabilities', [])
            if task_type in capabilities or 'general' in capabilities:
                benchmarks = data.get('benchmarks', {})
                score = ToolScorer.score_tool_static(benchmarks)
                
                # Apply priority modifiers
                if self.priority_registry.get("cost_sensitive"):
                    score *= 0.9
                if self.priority_registry.get("accuracy_required"):
                    score *= 1.1
                if self.priority_registry.get("speed_required"):
                    speed = float(str(benchmarks.get("speed", "1000ms")).replace("ms", ""))
                    if speed < 500:
                        score *= 1.1
                
                if score > best_score:
                    best_tool = tid
                    best_score = score
        
        route_entry = f"[{datetime.datetime.now()}] Routed task '{task_type}' to tool: {best_tool if best_tool else 'No suitable tool found'}"
        self.tool_registry.log.append(route_entry)
        logging.info(route_entry)
        
        return {
            "task_type": task_type,
            "routed_to": best_tool,
            "score": best_score,
            "available_tools": len([t for t in tools.values() if task_type in t.get('capabilities', [])])
        }


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


# project_guardian/adapters.py
# Module Adapters for ElysiaLoop-Core Integration
# Wraps existing Guardian modules to work with the event loop system

from typing import Dict, Any, List, Optional
from .elysia_loop_core import BaseModuleAdapter
from .memory import MemoryCore
from .mutation import MutationEngine
from .safety import DevilsAdvocate
from .trust import TrustMatrix
from .tasks import TaskEngine
from .consensus import ConsensusEngine


class MemoryAdapter(BaseModuleAdapter):
    """Adapter for MemoryCore module."""
    
    def __init__(self, memory: MemoryCore):
        self.memory = memory
        
    def get_module_name(self) -> str:
        return "memory"
        
    def get_capabilities(self) -> List[str]:
        return ["remember", "recall", "search", "forget"]
        
    def execute(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if method == "remember":
                thought = payload.get("thought", "")
                category = payload.get("category", "general")
                priority = payload.get("priority", 0.5)
                self.memory.remember(thought, category, priority)
                return {"success": True, "message": "Memory stored"}
                
            elif method == "recall_last":
                count = payload.get("count", 1)
                category = payload.get("category")
                memories = self.memory.recall_last(count, category)
                return {"success": True, "memories": memories}
                
            elif method == "search_memories":
                keyword = payload.get("keyword", "")
                limit = payload.get("limit", 10)
                results = self.memory.search_memories(keyword, limit)
                return {"success": True, "results": results}
                
            elif method == "get_memories_by_category":
                category = payload.get("category", "")
                memories = self.memory.get_memories_by_category(category)
                return {"success": True, "memories": memories}
                
            elif method == "get_memory_stats":
                stats = self.memory.get_memory_stats()
                return {"success": True, "stats": stats}
                
            else:
                return {"success": False, "error": f"Unknown method: {method}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}


class MutationAdapter(BaseModuleAdapter):
    """Adapter for MutationEngine module."""
    
    def __init__(self, mutation: MutationEngine):
        self.mutation = mutation
        
    def get_module_name(self) -> str:
        return "mutation"
        
    def get_capabilities(self) -> List[str]:
        return ["propose_mutation", "get_mutation_stats", "get_recent_mutations"]
        
    def execute(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if method == "propose_mutation":
                filename = payload.get("filename", "")
                new_code = payload.get("new_code", "")
                result = self.mutation.propose_mutation(filename, new_code)
                return {"success": True, "result": result}
                
            elif method == "get_mutation_stats":
                stats = self.mutation.get_mutation_stats()
                return {"success": True, "stats": stats}
                
            elif method == "get_recent_mutations":
                limit = payload.get("limit", 10)
                mutations = self.mutation.get_recent_mutations(limit)
                return {"success": True, "mutations": mutations}
                
            else:
                return {"success": False, "error": f"Unknown method: {method}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}


class SafetyAdapter(BaseModuleAdapter):
    """Adapter for DevilsAdvocate module."""
    
    def __init__(self, safety: DevilsAdvocate):
        self.safety = safety
        
    def get_module_name(self) -> str:
        return "safety"
        
    def get_capabilities(self) -> List[str]:
        return ["review_mutation", "challenge", "check_system_health", "get_safety_report"]
        
    def execute(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if method == "review_mutation":
                code_list = payload.get("code", [])
                result = self.safety.review_mutation(code_list)
                return {"success": True, "result": result}
                
            elif method == "challenge":
                statement = payload.get("statement", "")
                context = payload.get("context", "")
                result = self.safety.challenge(statement, context)
                return {"success": True, "result": result}
                
            elif method == "check_system_health":
                metrics = payload.get("metrics", {})
                result = self.safety.check_system_health(metrics)
                return {"success": True, "result": result}
                
            elif method == "get_safety_report":
                report = self.safety.get_safety_report()
                return {"success": True, "report": report}
                
            else:
                return {"success": False, "error": f"Unknown method: {method}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}


class TrustAdapter(BaseModuleAdapter):
    """Adapter for TrustMatrix module."""
    
    def __init__(self, trust: TrustMatrix):
        self.trust = trust
        
    def get_module_name(self) -> str:
        return "trust"
        
    def get_capabilities(self) -> List[str]:
        return [
            "update_trust", "get_trust", "validate_trust_for_action",
            "get_trust_report", "get_low_trust_components", "decay_all"
        ]
        
    def execute(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if method == "update_trust":
                component = payload.get("component", "")
                trust_value = payload.get("trust_value", 0.5)
                reason = payload.get("reason", "")
                self.trust.update_trust(component, trust_value, reason)
                return {"success": True, "message": "Trust updated"}
                
            elif method == "get_trust":
                component = payload.get("component", "")
                trust_value = self.trust.get_trust(component)
                return {"success": True, "trust_value": trust_value}
                
            elif method == "validate_trust_for_action":
                component = payload.get("component", "")
                action = payload.get("action", "")
                is_valid = self.trust.validate_trust_for_action(component, action)
                return {"success": True, "is_valid": is_valid}
                
            elif method == "get_trust_report":
                report = self.trust.get_trust_report()
                return {"success": True, "report": report}
                
            elif method == "get_low_trust_components":
                threshold = payload.get("threshold", 0.5)
                components = self.trust.get_low_trust_components(threshold)
                return {"success": True, "components": components}
                
            elif method == "decay_all":
                decay_rate = payload.get("decay_rate", 0.01)
                self.trust.decay_all(decay_rate)
                return {"success": True, "message": "Trust decay applied"}
                
            else:
                return {"success": False, "error": f"Unknown method: {method}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}


class TaskAdapter(BaseModuleAdapter):
    """Adapter for TaskEngine module."""
    
    def __init__(self, tasks: TaskEngine):
        self.tasks = tasks
        
    def get_module_name(self) -> str:
        return "tasks"
        
    def get_capabilities(self) -> List[str]:
        return [
            "create_task", "get_task", "update_task_status", "complete_task",
            "get_active_tasks", "get_task_stats"
        ]
        
    def execute(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if method == "create_task":
                name = payload.get("name", "")
                description = payload.get("description", "")
                priority = payload.get("priority", 0.5)
                category = payload.get("category", "general")
                task = self.tasks.create_task(name, description, priority, category)
                return {"success": True, "task": task}
                
            elif method == "get_task":
                task_id = payload.get("task_id")
                task = self.tasks.get_task(task_id)
                if task:
                    return {"success": True, "task": task}
                else:
                    return {"success": False, "error": "Task not found"}
                    
            elif method == "update_task_status":
                task_id = payload.get("task_id")
                status = payload.get("status", "")
                result = self.tasks.update_task_status(task_id, status)
                return {"success": result}
                
            elif method == "complete_task":
                task_id = payload.get("task_id")
                result = self.tasks.complete_task(task_id)
                return {"success": result}
                
            elif method == "get_active_tasks":
                category = payload.get("category")
                tasks = self.tasks.get_active_tasks(category)
                return {"success": True, "tasks": tasks}
                
            elif method == "get_task_stats":
                stats = self.tasks.get_task_stats()
                return {"success": True, "stats": stats}
                
            else:
                return {"success": False, "error": f"Unknown method: {method}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}


class ConsensusAdapter(BaseModuleAdapter):
    """Adapter for ConsensusEngine module."""
    
    def __init__(self, consensus: ConsensusEngine):
        self.consensus = consensus
        
    def get_module_name(self) -> str:
        return "consensus"
        
    def get_capabilities(self) -> List[str]:
        return [
            "register_agent", "cast_vote", "decide", "get_agent_stats",
            "clear_votes"
        ]
        
    def execute(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if method == "register_agent":
                name = payload.get("name", "")
                agent_type = payload.get("agent_type", "")
                weight = payload.get("weight", 1.0)
                capabilities = payload.get("capabilities", [])
                self.consensus.register_agent(name, agent_type, weight, capabilities)
                return {"success": True, "message": "Agent registered"}
                
            elif method == "cast_vote":
                agent_name = payload.get("agent_name", "")
                decision = payload.get("decision", "")
                confidence = payload.get("confidence", 0.5)
                reasoning = payload.get("reasoning", "")
                self.consensus.cast_vote(agent_name, decision, confidence, reasoning)
                return {"success": True, "message": "Vote cast"}
                
            elif method == "decide":
                decision_name = payload.get("decision_name", "")
                result = self.consensus.decide(decision_name)
                return {"success": True, "decision": result}
                
            elif method == "get_agent_stats":
                stats = self.consensus.get_agent_stats()
                return {"success": True, "stats": stats}
                
            elif method == "clear_votes":
                self.consensus.clear_votes()
                return {"success": True, "message": "Votes cleared"}
                
            else:
                return {"success": False, "error": f"Unknown method: {method}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}


# project_guardian/tool_executor.py
# Execute Mistral decision actions with guardian delegation

import logging
from typing import Dict, Any, List, Set

logger = logging.getLogger(__name__)


def execute_action(
    action: Dict[str, Any],
    allowed_tools: Set[str],
    guardian: Any,
) -> Dict[str, Any]:
    """
    Execute a single action from Mistral's decision. Blocks unknown tools.
    """
    tool = action.get("tool", "")
    args = action.get("args") or {}

    if tool not in allowed_tools:
        raise ValueError(f"Blocked tool: {tool}")

    if tool == "run_diagnostic":
        return _run_diagnostic(guardian, **args)

    if tool == "create_task":
        return _create_task(guardian, **args)

    if tool == "search_memory":
        return _search_memory(guardian, **args)

    if tool == "ask_user":
        return _ask_user(guardian, **args)

    if tool == "execute_task":
        return _execute_task(guardian, **args)

    if tool == "consider_learning":
        return _consider_learning(guardian, **args)

    if tool == "consider_adversarial_learning":
        return _consider_adversarial_learning(guardian, **args)

    if tool == "rebuild_vector":
        return _rebuild_vector(guardian, **args)

    if tool == "continue_monitoring":
        return {"status": "ok", "action": "continue_monitoring"}

    raise ValueError(f"Unknown tool: {tool}")


def _run_diagnostic(guardian, **kwargs: Any) -> Dict[str, Any]:
    """Run diagnostic - delegates to task execution or adversarial cycle."""
    try:
        from .adversarial_self_learning import run_adversarial_cycle, TRIGGER_PERIODIC
        result = run_adversarial_cycle(guardian, triggered_by=TRIGGER_PERIODIC)
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.debug("run_diagnostic: %s", e)
        return {"status": "error", "error": str(e)}


def _create_task(guardian, name: str = "", description: str = "", priority: float = 0.7, **kwargs: Any) -> Dict[str, Any]:
    """Create a task via guardian.tasks."""
    try:
        tasks = getattr(guardian, "tasks", None)
        if not tasks or not hasattr(tasks, "create_task"):
            return {"status": "error", "error": "TaskEngine not available"}
        t = tasks.create_task(
            name=name or "Mistral task",
            description=description or "",
            priority=priority,
            category=kwargs.get("category", "general"),
        )
        return {"status": "ok", "task_id": t.get("id")}
    except Exception as e:
        logger.debug("create_task: %s", e)
        return {"status": "error", "error": str(e)}


def _search_memory(guardian, query: str = "", limit: int = 10, **kwargs: Any) -> Dict[str, Any]:
    """Search memory via guardian.memory_search or memory.get_recent_memories."""
    try:
        mem_search = getattr(guardian, "memory_search", None)
        if mem_search and hasattr(mem_search, "search"):
            results = mem_search.search(query or "recent", limit=limit)
            return {"status": "ok", "results": [r.get("thought", str(r))[:100] for r in (results or [])[:limit]]}
        memory = getattr(guardian, "memory", None)
        if memory and hasattr(memory, "get_recent_memories"):
            recent = list(memory.get_recent_memories(limit=limit, load_if_needed=True))
            return {"status": "ok", "results": [r.get("thought", str(r))[:100] for r in recent]}
        return {"status": "ok", "results": []}
    except Exception as e:
        logger.debug("search_memory: %s", e)
        return {"status": "error", "error": str(e)}


def _ask_user(guardian, message: str = "", **kwargs: Any) -> Dict[str, Any]:
    """Ask user - logs for now; UI can implement escalation."""
    logger.info("[Mistral] Ask user: %s", message or "Decision requires user input")
    return {"status": "deferred", "message": message or "User input required"}


def _execute_task(guardian, task_id: int = None, **kwargs: Any) -> Dict[str, Any]:
    """Execute a task - stub that triggers autonomy path."""
    return {"status": "ok", "action": "execute_task", "task_id": task_id}


def _consider_learning(guardian, **kwargs: Any) -> Dict[str, Any]:
    """Trigger learning cycle."""
    try:
        if hasattr(guardian, "_trigger_introspection_learning"):
            guardian._trigger_introspection_learning()
        return {"status": "ok", "action": "consider_learning"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _consider_adversarial_learning(guardian, **kwargs: Any) -> Dict[str, Any]:
    """Trigger adversarial self-learning cycle."""
    try:
        from .adversarial_self_learning import run_adversarial_cycle, TRIGGER_PERIODIC
        run_adversarial_cycle(guardian, triggered_by=TRIGGER_PERIODIC)
        return {"status": "ok", "action": "consider_adversarial_learning"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _rebuild_vector(guardian, **kwargs: Any) -> Dict[str, Any]:
    """Rebuild vector memory."""
    try:
        if hasattr(guardian, "rebuild_vector_memory_if_pending"):
            result = guardian.rebuild_vector_memory_if_pending()
            return {"status": "ok", "result": result}
        return {"status": "ok", "action": "rebuild_vector"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

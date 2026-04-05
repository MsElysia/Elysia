# project_guardian/orchestration/router/task_types.py
REASONING = "reasoning"
CODING = "coding"
SUMMARIZATION = "summarization"
CRITIQUE = "critique"
MEMORY_COMPRESSION = "memory_compression"
TOOL_SELECTION = "tool_selection"
BOUNDED_ACTION = "bounded_action"

TASK_TYPES = frozenset(
    {
        REASONING,
        CODING,
        SUMMARIZATION,
        CRITIQUE,
        MEMORY_COMPRESSION,
        TOOL_SELECTION,
        BOUNDED_ACTION,
    }
)

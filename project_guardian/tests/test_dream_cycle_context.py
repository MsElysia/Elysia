import asyncio
import datetime

from project_guardian.creativity import DreamEngine as CreativeDreamEngine
from project_guardian.dream_engine import ReflectiveDreamEngine
from project_guardian.dream_engine import DreamEngine as ReflectiveDreamEngineAlias
from project_guardian.dream_engine import DreamType

assert ReflectiveDreamEngineAlias is ReflectiveDreamEngine


def _entry(thought, category="autonomy"):
    return {
        "time": datetime.datetime.now().isoformat(),
        "thought": thought,
        "category": category,
        "priority": 0.7,
        "metadata": {},
    }


class FakeMemory:
    def __init__(self, entries=None):
        self.entries = list(entries or [])
        self.remembered = []

    def get_recent_memories(self, limit=50, category=None, load_if_needed=True):
        entries = self.entries + self.remembered
        if category:
            entries = [entry for entry in entries if entry.get("category") == category]
        return entries[-limit:]

    def recall_last(self, count=1, category=None, use_timeline=False):
        return self.get_recent_memories(limit=count, category=category)

    def get_memories_by_category(self, category):
        return [entry for entry in self.entries + self.remembered if entry.get("category") == category]

    def get_memory_count(self, load_if_needed=False):
        return len(self.entries) + len(self.remembered)

    def remember(self, thought, category="general", priority=0.5, metadata=None):
        self.remembered.append({
            "time": datetime.datetime.now().isoformat(),
            "thought": thought,
            "category": category,
            "priority": priority,
            "metadata": metadata or {},
        })


def test_core_dream_cycle_uses_recent_operational_signal():
    memory = FakeMemory([
        _entry("Resource limit exceeded: memory at 96.7% and cleanup skips continue"),
        _entry("[Guardian Task] Created: Adversarial: review_cleanup_threshold"),
    ])
    engine = CreativeDreamEngine(memory)

    dream = engine.compose_dream()

    assert "memory-pressure" in dream
    assert "evidence-backed action" in dream
    assert "stars look like" not in dream.lower()


def test_core_dream_cycle_records_contextual_thought():
    memory = FakeMemory([
        _entry("[SelfTask] artifact saved revenue shortlist with first buyer offer"),
    ])
    engine = CreativeDreamEngine(memory)

    dreams = engine.begin_dream_cycle(cycles=1)

    assert len(dreams) == 1
    assert "buyer-facing validation" in dreams[0]
    assert memory.remembered[-1]["category"] == "creativity"
    assert memory.remembered[-1]["thought"].startswith("[Dream] ")


def test_reflective_planning_dream_uses_context_and_persists(tmp_path):
    storage = tmp_path / "dreams.json"
    engine = ReflectiveDreamEngine(storage_path=str(storage))

    dream = asyncio.run(engine.dream(
        DreamType.PLANNING,
        context={
            "pending_tasks": 4,
            "memory_pressure": 0.93,
            "underused_modules": ["harvest_engine"],
        },
    ))

    joined = " ".join(dream.insights)
    assert "4 pending task" in joined
    assert "93%" in joined
    assert "harvest_engine" in joined
    assert storage.exists()


def test_reflective_emotional_dream_without_context_does_not_error(tmp_path):
    engine = ReflectiveDreamEngine(storage_path=str(tmp_path / "dreams.json"))

    dream = asyncio.run(engine.dream(DreamType.EMOTIONAL))

    joined = " ".join(dream.insights).lower()
    assert "encountered an error" not in joined
    assert "emotional memory processed" in joined


def test_reflective_optimizer_uses_context_metrics(tmp_path):
    engine = ReflectiveDreamEngine(storage_path=str(tmp_path / "dreams.json"))

    dream = asyncio.run(engine.dream(
        DreamType.OPTIMIZATION,
        context={
            "memory_usage": 0.91,
            "recent_errors": 2,
            "api_rate_limit_hits": 3,
        },
    ))

    joined = " ".join(dream.insights)
    assert "91%" in joined
    assert "3 recent rate-limit" in joined
    assert "2 recent error" in joined

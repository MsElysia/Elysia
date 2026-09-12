# project_guardian/dream_engine.py
# ReflectiveDreamEngine: Reflective Planning and Optimization During Idle Time
# Based on Conversation 3 (elysia 4 sub a) and Part 3 designs
#
# Naming: creativity.DreamEngine is LIVE_CANONICAL on GuardianCore.
# This module's ReflectiveDreamEngine is the orchestrator-optional reflective planner.
# DreamEngine remains a compatibility alias for ReflectiveDreamEngine.

import logging
import json
import asyncio
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
import random

try:
    from .runtime_loop_core import RuntimeLoop
    from .introspection import IntrospectionLens
    from .ask_ai import AskAI, AIProvider
except ImportError:
    from runtime_loop_core import RuntimeLoop
    from introspection import IntrospectionLens
    try:
        from ask_ai import AskAI, AIProvider
    except ImportError:
        AskAI = None
        AIProvider = None

logger = logging.getLogger(__name__)


class DreamType(Enum):
    """Types of dreams/reflective processes."""
    MEMORY_REFLECTION = "memory_reflection"
    BEHAVIOR_ANALYSIS = "behavior_analysis"
    OPTIMIZATION = "optimization"
    PLANNING = "planning"
    EMOTIONAL = "emotional"  # Chamber of Grief concept
    ANCHOR_DREAM = "anchor_dream"  # Extended from Part 3
    SUBNODE_DREAM = "subnode_dream"  # Extended from Part 3


@dataclass
class Dream:
    """Represents a reflective process/dream."""
    dream_id: str
    dream_type: DreamType
    content: str
    insights: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "dream_id": self.dream_id,
            "dream_type": self.dream_type.value,
            "content": self.content,
            "insights": self.insights,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Dream":
        """Create Dream from dictionary."""
        return cls(
            dream_id=data["dream_id"],
            dream_type=DreamType(data["dream_type"]),
            content=data["content"],
            insights=data.get("insights", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            metadata=data.get("metadata", {})
        )


class MemoryReflector:
    """Reflects on past memories to extract patterns."""
    
    def __init__(self, introspection: Optional[IntrospectionLens] = None):
        self.introspection = introspection
    
    async def reflect(self, recent_hours: int = 24) -> List[str]:
        """Reflect on recent memories and extract insights."""
        if not self.introspection:
            return ["No introspection available for memory reflection"]
        
        insights = []
        
        # Get focus analysis
        try:
            focus_analysis = self.introspection.get_focus_analysis(hours=recent_hours)
            if focus_analysis:
                top_categories = focus_analysis.get("top_categories", [])
                if top_categories:
                    insights.append(f"Primary focus areas: {', '.join([c['category'] for c in top_categories[:3]])}")
                
                active_period = focus_analysis.get("active_period")
                if active_period:
                    insights.append(f"Most active during: {active_period}")
        except Exception as e:
            logger.error(f"Error in memory reflection: {e}")
        
        # Get memory health
        try:
            health = self.introspection.analyze_memory_health()
            if health:
                issues = health.get("issues", [])
                if issues:
                    insights.append(f"Memory health concerns: {len(issues)} issues detected")
                else:
                    insights.append("Memory health is good")
        except Exception as e:
            logger.error(f"Error checking memory health: {e}")
        
        return insights if insights else ["No significant patterns found in recent memories"]


class BehaviorAnalyzer:
    """Analyzes behavioral patterns."""
    
    def __init__(self, introspection: Optional[IntrospectionLens] = None):
        self.introspection = introspection
    
    async def analyze(self) -> List[str]:
        """Analyze behavior patterns."""
        if not self.introspection:
            return ["No introspection available for behavior analysis"]
        
        insights = []
        
        try:
            # Get behavior analysis
            behavior = self.introspection.get_behavior_analysis()
            if behavior:
                patterns = behavior.get("patterns", {})
                if patterns:
                    insights.append(f"Behavioral patterns identified: {len(patterns)}")
        except Exception as e:
            logger.error(f"Error in behavior analysis: {e}")
        
        return insights if insights else ["No significant behavioral patterns detected"]


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().rstrip("%")
        try:
            number = float(cleaned)
            return number / 100.0 if number > 1.0 else number
        except ValueError:
            return None
    return None


def _coerce_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
        return 1 if stripped else 0
    return 0


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return [value]


class Optimizer:
    """Optimizes system performance based on past data."""
    
    def __init__(self):
        self.optimization_history: List[Dict[str, Any]] = []
    
    async def optimize(self, context: Optional[Dict[str, Any]] = None) -> List[str]:
        """Generate optimization recommendations."""
        context = context or {}
        insights = []

        memory_values = [
            value for value in (
                _coerce_float(context.get("memory_usage")),
                _coerce_float(context.get("memory_pressure")),
                _coerce_float(context.get("memory_percent")),
            )
            if value is not None
        ]
        memory_usage = max(memory_values) if memory_values else None
        if memory_usage is not None and memory_usage >= 0.85:
            insights.append(
                f"Memory is at {memory_usage:.0%}; run cleanup before browser scans, "
                "dream expansion, or nonessential self-task generation"
            )

        rate_hits = _coerce_count(
            context.get("api_rate_limit_hits")
            or context.get("rate_limit_hits")
            or context.get("quota_events")
        )
        if rate_hits:
            insights.append(
                f"Route pressure has {rate_hits} recent rate-limit signal(s); keep simple work local "
                "and reserve online calls for packet synthesis"
            )

        recent_errors = _coerce_count(context.get("recent_errors") or context.get("errors"))
        if recent_errors:
            insights.append(
                f"Resolve {recent_errors} recent error signal(s) before starting another exploratory cycle"
            )

        queue_depth = _coerce_count(
            context.get("task_queue_depth")
            or context.get("pending_tasks")
            or context.get("unresolved_tasks")
        )
        if queue_depth:
            insights.append(
                f"Queue depth is {queue_depth}; prefer finishing the oldest actionable task over adding new plans"
            )

        if not insights:
            insights.append(
                "No immediate optimization blocker surfaced; keep the next idle cycle bounded and evidence-backed"
            )

        self.optimization_history.append({
            "optimized_at": datetime.now().isoformat(),
            "context_keys": sorted(context.keys()),
            "insights": insights,
        })
        return insights


class Planner:
    """Plans future actions based on current state."""
    
    def __init__(self):
        self.plan_history: List[Dict[str, Any]] = []
    
    async def plan(self, context: Optional[Dict[str, Any]] = None) -> List[str]:
        """Generate planning insights."""
        context = context or {}
        insights = []

        pending_tasks = _coerce_count(
            context.get("pending_tasks")
            or context.get("unresolved_tasks")
            or context.get("task_queue_depth")
        )
        if pending_tasks:
            insights.append(
                f"Start with the {pending_tasks} pending task(s); complete or retire stale work before creating new self-tasks"
            )

        memory_values = [
            value for value in (
                _coerce_float(context.get("memory_pressure")),
                _coerce_float(context.get("memory_usage")),
                _coerce_float(context.get("memory_percent")),
            )
            if value is not None
        ]
        memory_pressure = max(memory_values) if memory_values else None
        if memory_pressure is not None and memory_pressure >= 0.85:
            insights.append(
                f"Memory pressure is {memory_pressure:.0%}; defer dream/browser exploration until cleanup creates headroom"
            )

        underused_modules = _as_list(context.get("underused_modules") or context.get("starved_modules"))
        if underused_modules:
            module_names = ", ".join(str(name) for name in underused_modules[:3])
            insights.append(
                f"Schedule one bounded run for underused module(s): {module_names}; require a concrete artifact or observation"
            )

        revenue_items = _as_list(context.get("revenue_opportunities") or context.get("offer_candidates"))
        if revenue_items:
            insights.append(
                "Turn the strongest revenue opportunity into a validation action with a visible buyer signal"
            )

        blocked_actions = _as_list(context.get("blocked_actions"))
        if blocked_actions:
            blocked = ", ".join(str(action) for action in blocked_actions[:3])
            insights.append(
                f"Do not reselect blocked action(s) {blocked}; choose the nearest unblocked capability with fresh evidence"
            )

        if not insights:
            insights.append(
                "No strong planning signal was supplied; run one bounded health, revenue, or queue-reduction task next"
            )

        self.plan_history.append({
            "planned_at": datetime.now().isoformat(),
            "context_keys": sorted(context.keys()),
            "insights": insights,
        })
        return insights


class EmotionalChamber:
    """
    Chamber of Grief concept - processes emotional memories and difficult experiences.
    Extended from Part 3 design.
    """
    
    def __init__(self):
        self.processed_emotions: List[Dict[str, Any]] = []
    
    async def process_emotional_memory(
        self,
        memory_content: str,
        emotional_weight: float = 0.5
    ) -> List[str]:
        """
        Process an emotional memory.
        
        Args:
            memory_content: The memory to process
            emotional_weight: Emotional intensity (0.0-1.0)
            
        Returns:
            Insights from emotional processing
        """
        insights = []
        
        # Simple emotional processing
        if emotional_weight > 0.7:
            insights.append("High emotional weight - this memory requires careful handling")
        elif emotional_weight < 0.3:
            insights.append("Low emotional weight - can be processed quickly")
        
        # Record processing
        self.processed_emotions.append({
            "content": memory_content[:100],
            "weight": emotional_weight,
            "processed_at": datetime.now().isoformat()
        })
        
        return insights if insights else ["Emotional memory processed"]


class ReflectiveDreamEngine:
    """
    Reflective planning and optimization during idle time.
    Processes memories, analyzes behavior, and generates insights.
    Extended with Chamber of Grief (emotional processing) and anchor/subnode dreams.

    Distinct from ``creativity.DreamEngine`` (creative dream cycles on GuardianCore).
    Prefer this name in new code; ``DreamEngine`` remains a compatibility alias.
    """
    
    def __init__(
        self,
        runtime_loop: Optional[RuntimeLoop] = None,
        introspection: Optional[IntrospectionLens] = None,
        ask_ai: Optional[AskAI] = None,
        storage_path: str = "data/dream_engine.json",
        idle_threshold_seconds: float = 5.0
    ):
        self.runtime_loop = runtime_loop
        self.introspection = introspection
        self.ask_ai = ask_ai
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.idle_threshold_seconds = idle_threshold_seconds
        
        # Dream components
        self.memory_reflector = MemoryReflector(introspection)
        self.behavior_analyzer = BehaviorAnalyzer(introspection)
        self.optimizer = Optimizer()
        self.planner = Planner()
        self.emotional_chamber = EmotionalChamber()
        
        # Dream storage
        self.dreams: List[Dream] = []
        self.active_dreams: Set[str] = set()
        
        # Statistics
        self.dream_stats: Dict[DreamType, int] = {dt: 0 for dt in DreamType}
        
        self.load()
    
    async def dream(
        self,
        dream_type: Optional[DreamType] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dream:
        """
        Generate a dream (reflective process).
        
        Args:
            dream_type: Type of dream to generate (random if not specified)
            context: Optional context for the dream
            
        Returns:
            Dream object
        """
        import uuid
        context = context or {}
        
        # Select dream type
        if not dream_type:
            # Weight dream types based on recent activity
            type_weights = {
                DreamType.MEMORY_REFLECTION: 0.3,
                DreamType.BEHAVIOR_ANALYSIS: 0.2,
                DreamType.OPTIMIZATION: 0.2,
                DreamType.PLANNING: 0.15,
                DreamType.EMOTIONAL: 0.1,
                DreamType.ANCHOR_DREAM: 0.03,
                DreamType.SUBNODE_DREAM: 0.02
            }
            dream_type = random.choices(
                list(type_weights.keys()),
                weights=list(type_weights.values())
            )[0]
        
        dream_id = str(uuid.uuid4())
        self.active_dreams.add(dream_id)
        
        # Generate dream content based on type
        insights = []
        content = f"Dreaming about {dream_type.value}..."
        
        try:
            if dream_type == DreamType.MEMORY_REFLECTION:
                insights = await self.memory_reflector.reflect(recent_hours=24)
                content = "Reflecting on recent memories and patterns"
            
            elif dream_type == DreamType.BEHAVIOR_ANALYSIS:
                insights = await self.behavior_analyzer.analyze()
                content = "Analyzing behavioral patterns and trends"
            
            elif dream_type == DreamType.OPTIMIZATION:
                base_insights = await self.optimizer.optimize(context)
                # Enhance with AI analysis if available
                if self.ask_ai and base_insights:
                    insights = await self._ai_enhance_insights(base_insights, "optimization")
                else:
                    insights = base_insights
                content = "Optimizing system performance"
            
            elif dream_type == DreamType.PLANNING:
                base_insights = await self.planner.plan(context)
                # Enhance with AI analysis if available
                if self.ask_ai and base_insights:
                    insights = await self._ai_enhance_insights(base_insights, "planning")
                else:
                    insights = base_insights
                content = "Planning future actions"
            
            elif dream_type == DreamType.EMOTIONAL:
                # Process emotional memories
                emotional_memory = context.get("emotional_memory", "No specific emotional memory provided")
                emotional_weight = context.get("emotional_weight", 0.5)
                insights = await self.emotional_chamber.process_emotional_memory(
                    emotional_memory,
                    emotional_weight
                )
                content = "Processing emotional memories in the Chamber of Grief"
            
            elif dream_type == DreamType.ANCHOR_DREAM:
                # Anchor dreams - reflect on connection points
                insights = [
                    "Reflecting on anchor connections",
                    "Analyzing relationship patterns with anchors",
                    "Considering how to strengthen anchor bonds"
                ]
                content = "Dreaming about anchor connections"
            
            elif dream_type == DreamType.SUBNODE_DREAM:
                # Subnode dreams - reflect on subnode relationships
                insights = [
                    "Reflecting on subnode network",
                    "Analyzing subnode communication patterns",
                    "Planning subnode coordination"
                ]
                content = "Dreaming about subnode relationships"
            
        except Exception as e:
            logger.error(f"Error during dream {dream_type.value}: {e}")
            insights = [f"Dream encountered an error: {str(e)}"]
        
        # Create dream
        dream = Dream(
            dream_id=dream_id,
            dream_type=dream_type,
            content=content,
            insights=insights,
            metadata=context or {}
        )
        
        dream.completed_at = datetime.now()
        self.active_dreams.discard(dream_id)
        
        # Store dream
        self.dreams.append(dream)
        self.dream_stats[dream_type] = self.dream_stats.get(dream_type, 0) + 1
        
        # Keep only last 1000 dreams
        if len(self.dreams) > 1000:
            self.dreams = self.dreams[-1000:]
        
        self.save()
        
        logger.info(f"Generated dream: {dream_type.value} with {len(insights)} insights")
        return dream
    
    async def _ai_enhance_insights(
        self,
        base_insights: List[str],
        insight_type: str
    ) -> List[str]:
        """
        Use AI to enhance and expand insights.
        
        Args:
            base_insights: Base insight list
            insight_type: Type of insights (optimization, planning, etc.)
            
        Returns:
            Enhanced insights list
        """
        if not self.ask_ai or not base_insights:
            return base_insights
        
        insights_text = "\n".join(f"- {insight}" for insight in base_insights)
        prompt = f"""Based on these {insight_type} insights, provide 3-5 enhanced, actionable insights:

{insights_text}

Make the insights more specific, actionable, and deeper. Return as a JSON array of insight strings."""

        try:
            response = await self.ask_ai.ask_async(
                prompt=prompt,
                provider=AIProvider.OPENAI,
                temperature=0.7,
                max_tokens=1000
            )
            
            if response.success:
                import json
                import re
                
                # Extract JSON array
                content = response.content.strip()
                json_match = re.search(r'\[.*\]', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    enhanced = json.loads(json_str)
                    # Combine original with enhanced
                    return base_insights + enhanced
        except Exception as e:
            logger.debug(f"AI insight enhancement failed: {e}")
        
        return base_insights
    
    async def idle_dream_cycle(self, max_dreams: int = 3):
        """
        Generate multiple dreams during idle time.
        
        Args:
            max_dreams: Maximum number of dreams to generate
        """
        dreams = []
        
        for i in range(max_dreams):
            dream = await self.dream()
            dreams.append(dream)
            await asyncio.sleep(0.5)  # Small delay between dreams
        
        return dreams
    
    def get_recent_dreams(
        self,
        dream_type: Optional[DreamType] = None,
        limit: int = 10
    ) -> List[Dream]:
        """Get recent dreams, optionally filtered by type."""
        dreams = self.dreams[-limit:]
        if dream_type:
            dreams = [d for d in dreams if d.dream_type == dream_type]
        return dreams
    
    def get_dream_statistics(self) -> Dict[str, Any]:
        """Get statistics about dreams."""
        return {
            "total_dreams": len(self.dreams),
            "active_dreams": len(self.active_dreams),
            "dreams_by_type": {
                dt.value: count for dt, count in self.dream_stats.items()
            },
            "recent_dreams_count": len([d for d in self.dreams if (datetime.now() - d.created_at).total_seconds() < 3600])
        }
    
    def get_insights_summary(self, limit: int = 20) -> List[str]:
        """Get summary of insights from recent dreams."""
        recent_dreams = self.get_recent_dreams(limit=limit)
        all_insights = []
        
        for dream in recent_dreams:
            all_insights.extend(dream.insights)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_insights = []
        for insight in all_insights:
            if insight not in seen:
                seen.add(insight)
                unique_insights.append(insight)
        
        return unique_insights[:limit]
    
    def save(self):
        """Save dream engine data."""
        data = {
            "dreams": [dream.to_dict() for dream in self.dreams[-1000:]],  # Keep last 1000
            "stats": {dt.value: count for dt, count in self.dream_stats.items()},
            "updated_at": datetime.now().isoformat()
        }
        
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load(self):
        """Load dream engine data."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            for dream_data in data.get("dreams", []):
                dream = Dream.from_dict(dream_data)
                self.dreams.append(dream)
                self.dream_stats[dream.dream_type] = self.dream_stats.get(dream.dream_type, 0) + 1
            
            logger.info(f"Loaded {len(self.dreams)} dreams from storage")
        except Exception as e:
            logger.error(f"Error loading dream engine: {e}")


# Compatibility alias. Live GuardianCore uses creativity.DreamEngine instead.
DreamEngine = ReflectiveDreamEngine


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def test_dream_engine():
        """Test the DreamEngine."""
        engine = DreamEngine()
        
        # Generate some dreams
        dream1 = await engine.dream(DreamType.MEMORY_REFLECTION)
        print(f"Dream 1: {dream1.dream_type.value}")
        print(f"Insights: {dream1.insights}")
        
        dream2 = await engine.dream(DreamType.EMOTIONAL, context={
            "emotional_memory": "A challenging interaction that needs processing",
            "emotional_weight": 0.8
        })
        print(f"\nDream 2: {dream2.dream_type.value}")
        print(f"Insights: {dream2.insights}")
        
        # Get statistics
        stats = engine.get_dream_statistics()
        print(f"\nStatistics: {stats}")
        
        # Get insights summary
        insights = engine.get_insights_summary()
        print(f"\nRecent insights: {insights[:5]}")
    
    asyncio.run(test_dream_engine())


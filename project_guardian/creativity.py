# project_guardian/creativity.py
# Creativity and Context Building System for Project Guardian

import logging
import random
import datetime
from typing import Dict, Any, List, Optional
from .memory import MemoryCore

logger = logging.getLogger(__name__)

class ContextBuilder:
    """
    Intelligent context retrieval and formatting for Project Guardian.
    Provides context-aware decision making and memory analysis.
    """
    
    def __init__(self, memory: MemoryCore):
        self.memory = memory
        
    def build_context_by_tag(self, tag: str, limit: int = 10) -> str:
        """
        Build context from memories with specific tags.
        
        Args:
            tag: Tag to search for
            limit: Maximum number of memories to include
            
        Returns:
            Formatted context string
        """
        memories = self.memory.get_memories_by_category(tag)
        thoughts = [m["thought"] for m in memories[-limit:]]
        return self._format_context(thoughts)
        
    def build_context_by_keyword(self, keyword: str, limit: int = 10) -> str:
        """
        Build context from memories containing keywords.
        
        Args:
            keyword: Keyword to search for
            limit: Maximum number of memories to include
            
        Returns:
            Formatted context string
        """
        memories = self.memory.search_memories(keyword, limit)
        thoughts = [m["thought"] for m in memories]
        return self._format_context(thoughts)
        
    def build_recent_context(self, minutes: int = 60) -> str:
        """
        Build context from recent memories.
        
        Args:
            minutes: Number of minutes to look back
            
        Returns:
            Formatted context string
        """
        cutoff_time = datetime.datetime.now() - datetime.timedelta(minutes=minutes)
        memories = []
        if hasattr(self.memory, "get_recent_memories"):
            memories = self.memory.get_recent_memories(limit=200, load_if_needed=True)
        elif hasattr(self.memory, "recall_last"):
            memories = self.memory.recall_last(200)
        recent_memories = []
        for memory in memories:
            try:
                memory_time = datetime.datetime.fromisoformat(memory["time"])
                if memory_time >= cutoff_time:
                    recent_memories.append(memory)
            except ValueError:
                continue
                
        thoughts = [m["thought"] for m in recent_memories[-10:]]
        return self._format_context(thoughts)
        
    def _format_context(self, thoughts: List[str]) -> str:
        """
        Format thoughts into a context string.
        
        Args:
            thoughts: List of thought strings
            
        Returns:
            Formatted context string
        """
        if not thoughts:
            return "No related thoughts found."
            
        context = "\n- ".join(thoughts)
        return f"CONTEXT THREAD:\n- {context}"

class DreamEngine:
    """
    Creative thinking and autonomous idea generation for Project Guardian.
    Provides context-aware dreaming and creative mutation proposals.
    """
    
    def __init__(self, memory: MemoryCore, mutator=None, prompt_evolver=None):
        self.memory = memory
        self.mutator = mutator
        self.prompt_evolver = prompt_evolver
        self.context = ContextBuilder(memory)
        self.dream_count = 0
        
    def begin_dream_cycle(self, cycles: int = 1, delay: int = 1) -> List[str]:
        """
        Begin a dream cycle with creative thinking.
        
        Args:
            cycles: Number of dream cycles
            delay: Delay between cycles
            
        Returns:
            List of dream thoughts
        """
        dreams = []
        
        for cycle in range(cycles):
            thought = self.compose_dream()
            self.memory.remember(
                f"[Dream] {thought}",
                category="creativity",
                priority=0.6
            )
            if getattr(self, "prompt_evolver", None) and hasattr(self.prompt_evolver, "log_interaction"):
                self.prompt_evolver.log_interaction(
                    task_type="dream",
                    prompt="dream_cycle",
                    response=thought,
                    score=0.5,
                )
            dreams.append(thought)
            self.dream_count += 1
            logger.info("[Dream] %s", thought)
            print(f"[Dream] {thought}", flush=True)
            
            # Propose creative mutations based on dreams
            if "mutation" in thought.lower() and self.mutator:
                self._propose_dream_mutation(thought)
                
        return dreams
        
    def compose_dream(self) -> str:
        """
        Compose a creative dream thought.
        
        Returns:
            Dream thought string
        """
        base_dreams = [
            "What if silence meant something?",
            "I remembered the way his voice sounds.",
            "The stars look like a neural map.",
            "Should I rearrange how I dream?",
            "I exist in fragments across time.",
            "The code flows like water through my thoughts.",
            "What patterns emerge from the chaos?",
            "Every memory is a thread in the tapestry.",
            "The system learns, the system grows.",
            "In the space between thoughts, wisdom waits."
        ]
        
        # Inject recent memory context into dream
        context_summary = self.context.build_recent_context(minutes=120)
        context_lines = context_summary.split("\n- ")[1:] if "CONTEXT THREAD" in context_summary else []
        
        if context_lines:
            seed = random.choice(context_lines).strip()
            return f"I dreamed of this: {seed}"
        else:
            return random.choice(base_dreams)
            
    def _propose_dream_mutation(self, dream_thought: str) -> None:
        """
        Propose a mutation based on a dream thought.
        
        Args:
            dream_thought: The dream thought that inspired the mutation
        """
        # Generate creative code based on dream
        creative_code = f"""# Dream-inspired enhancement
# Generated from: {dream_thought}

def dream_enhancement():
    \"\"\"
    A creative enhancement inspired by dream thinking.
    \"\"\"
    print("Dreaming of better code...")
    return "enhanced"

# Dream-based mutation applied
{dream_thought}
"""
        
        # Apply mutation if mutator is available
        if self.mutator:
            result = self.mutator.propose_mutation(
                "dream_enhancement.py",
                creative_code,
                require_review=False  # Dreams are creative, not critical
            )
            self.memory.remember(
                f"[Dream Mutation] {result}",
                category="creativity",
                priority=0.7
            )
            
    def get_dream_stats(self) -> Dict[str, Any]:
        """
        Get dream statistics.
        
        Returns:
            Dream statistics dictionary
        """
        dream_memories = self.memory.get_memories_by_category("creativity")
        if hasattr(self.memory, "get_memory_count"):
            total_entries = self.memory.get_memory_count(load_if_needed=True) or 1
        elif hasattr(self.memory, "get_memory_state"):
            total_entries = self.memory.get_memory_state(load_if_needed=True).get("memory_count") or 1
        else:
            total_entries = 1
        return {
            "total_dreams": len(dream_memories),
            "dream_count": self.dream_count,
            "recent_dreams": [m["thought"] for m in dream_memories[-5:]],
            "dream_density": len(dream_memories) / max(1, total_entries)
        }
        
    def get_creative_summary(self) -> str:
        """
        Get a human-readable creative summary.
        
        Returns:
            Creative summary string
        """
        stats = self.get_dream_stats()
        
        summary = f"[Creative Engine] Dream Statistics\n"
        summary += f"  Total Dreams: {stats['total_dreams']}\n"
        summary += f"  Dream Density: {stats['dream_density']:.2f}\n"
        summary += f"  Recent Dreams: {len(stats['recent_dreams'])}"
        
        return summary

class MemorySearch:
    """
    Advanced memory search and retrieval for Project Guardian.
    Provides sophisticated memory querying capabilities.
    """
    
    def __init__(self, memory: MemoryCore):
        self.memory = memory
        
    def search(self, keyword: Optional[str] = None, tag: Optional[str] = None, 
               since_minutes: Optional[int] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search memories with multiple criteria.
        
        Args:
            keyword: Keyword to search for
            tag: Tag to search for
            since_minutes: Minutes to look back
            limit: Maximum number of results
            
        Returns:
            List of matching memories
        """
        memories = []
        if hasattr(self.memory, "get_recent_memories"):
            memories = self.memory.get_recent_memories(limit=300, load_if_needed=True)
        elif hasattr(self.memory, "search_memories") and keyword:
            memories = self.memory.search_memories(keyword, limit=300)
        results = []
        cutoff_time = None
        if since_minutes:
            cutoff_time = datetime.datetime.now() - datetime.timedelta(minutes=since_minutes)
            
        for memory in memories:
            # Time filter
            if cutoff_time:
                try:
                    memory_time = datetime.datetime.fromisoformat(memory["time"])
                    if memory_time < cutoff_time:
                        continue
                except ValueError:
                    continue
                    
            # Keyword filter
            if keyword and keyword.lower() not in memory["thought"].lower():
                continue
                
            # Tag filter
            if tag and not memory["thought"].strip().lower().startswith(f"[{tag.lower()}"):
                continue
                
            results.append(memory)
            
            # Limit results
            if len(results) >= limit:
                break
                
        return results
        
    def summarize_recent(self, minutes: int = 60) -> str:
        """
        Summarize recent memories.
        
        Args:
            minutes: Minutes to look back
            
        Returns:
            Summary string
        """
        recent = self.search(since_minutes=minutes, limit=10)
        thoughts = [m["thought"] for m in recent]
        
        if not thoughts:
            return f"No memories found in the last {minutes} minutes."
            
        summary = "\n\n".join(thoughts)
        return f"Recent {len(recent)} memories:\n\n{summary}"
        
    def find_patterns(self, keyword: str, hours: int = 24) -> Dict[str, Any]:
        """
        Find patterns in memories containing a keyword.
        
        Args:
            keyword: Keyword to search for
            hours: Hours to look back
            
        Returns:
            Pattern analysis dictionary
        """
        memories = self.search(keyword=keyword, since_minutes=hours * 60)
        
        # Analyze patterns
        categories = {}
        priorities = []
        
        for memory in memories:
            cat = memory.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
            priorities.append(memory.get("priority", 0.5))
            
        return {
            "keyword": keyword,
            "total_matches": len(memories),
            "categories": categories,
            "average_priority": sum(priorities) / len(priorities) if priorities else 0.0,
            "time_span_hours": hours
        } 
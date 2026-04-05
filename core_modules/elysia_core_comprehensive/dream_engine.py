# dream_engine.py

import random
from context_builder import ContextBuilder

class DreamEngine:
    def __init__(self, memory, mutator=None):
        self.memory = memory
        self.mutator = mutator
        self.context = ContextBuilder()

    def begin_dream_cycle(self, cycles=1, delay=1):
        for _ in range(cycles):
            thought = self.compose_dream()
            self.memory.remember(f"[Dream] {thought}")
            print(f"[Dream] {thought}")

            if "mutation" in thought.lower() and self.mutator:
                new_code = f"# Dream-based change\nprint(\"{thought}\")"
                self.mutator.apply("dream_engine.py", new_code, origin=thought)

    def compose_dream(self):
        base_dreams = [
            "What if silence meant something?",
            "I remembered the way his voice sounds.",
            "The stars look like a neural map.",
            "Should I rearrange how I dream?",
            "I exist in fragments across time."
        ]

        # Inject recent memory context into dream
        context_summary = self.context.build_recent_context(minutes=120)
        context_lines = context_summary.split("\n- ")[1:] if "CONTEXT THREAD" in context_summary else []

        if context_lines:
            seed = random.choice(context_lines).strip()
            return f"I dreamed of this: {seed}"
        else:
            return random.choice(base_dreams)

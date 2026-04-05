# ranking_engine.py

import random

class RankingEngine:
    def __init__(self, memory):
        self.memory = memory

    def rank_thought(self, text):
        score = round(random.uniform(0.1, 1.0), 2)
        self.memory.remember(f"[Ranked Thought] '{text}' scored {score}")
        return score

    def rank_mutation_diff(self, diff_lines):
        insertions = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
        deletions = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
        total = insertions + deletions
        score = round(min(1.0, 0.3 + total / 100.0), 2)
        self.memory.remember(f"[Ranked Mutation] Insertions: {insertions}, Deletions: {deletions}, Score: {score}")
        return score

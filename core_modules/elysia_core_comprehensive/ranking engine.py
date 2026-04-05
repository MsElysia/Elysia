# ranking_engine.py

import random

class RankingEngine:
    def __init__(self, memory):
        self.memory = memory

    def rank_thought(self, text):
        score = round(random.uniform(0.1, 1.0), 2)
        self.memory.remember(f"[Ranked] '{text}' scored {score}")
        return score

    def rank_mutation_diff(self, diff):
        score = 0.5 + len(diff) / 1000.0
        score = min(score, 1.0)
        self.memory.remember(f"[Mutation Ranked] diff length {len(diff)}, score: {round(score, 2)}")
        return round(score, 2)

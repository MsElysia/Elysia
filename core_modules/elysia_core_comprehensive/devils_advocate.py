# devils_advocate.py

import random

class DevilsAdvocate:
    def __init__(self, memory):
        self.memory = memory

    def challenge(self, claim, context="unspecified"):
        flaws = [
            "relies on unfounded assumptions",
            "ignores side effects",
            "creates unnecessary complexity",
            "has unclear benefits",
            "could introduce regressions",
            "is ethically questionable",
            "conflicts with prior behavior",
            "invites unintended consequences"
        ]

        flaw = random.choice(flaws)
        rebuttal = (
            f"[DevilsAdvocate] '{claim}' may be flawed — it {flaw}. "
            f"Context: {context}."
        )

        self.memory.remember(rebuttal)
        print(rebuttal)
        return rebuttal

    def review_mutation(self, mutation_diff):
        if not mutation_diff:
            return "[DevilsAdvocate] No mutation diff provided."

        red_flags = ["import os", "exec(", "eval(", "open(", "memory.forget"]
        flagged_lines = [
            line for line in mutation_diff if any(flag in line for flag in red_flags)
        ]

        if flagged_lines:
            warning = f"[DevilsAdvocate] ⚠️ Mutation contains suspicious patterns: {flagged_lines}"
            self.memory.remember(warning)
            return warning

        self.memory.remember("[DevilsAdvocate] Mutation passed basic scrutiny.")
        return "[DevilsAdvocate] No immediate objection."


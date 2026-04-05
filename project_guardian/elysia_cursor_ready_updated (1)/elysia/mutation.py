# mutation.py

import random

class MutationFlow:
    def __init__(self, drift_threshold: float = 0.2):
        self.drift_threshold = drift_threshold
        self.history = []

    def mutate_identity(self, identity_anchor):
        new_tone_weights = {
            tone: max(0.01, weight + random.uniform(-0.05, 0.05))
            for tone, weight in identity_anchor.tone_weights.items()
        }
        total = sum(new_tone_weights.values())
        normalized = {k: v / total for k, v in new_tone_weights.items()}
        mutated = identity_anchor.__class__(
            name=identity_anchor.name + "_mutated",
            core_traits=identity_anchor.core_traits,
            tone_weights=normalized,
            mode="subnode"
        )
        self.history.append(mutated.describe())
        return mutated

# identity.py

class IdentityAnchor:
    def __init__(self, name: str, core_traits: list, tone_weights: dict, mode: str = "core"):
        self.name = name
        self.core_traits = core_traits
        self.tone_weights = tone_weights
        self.mode = mode

    def describe(self):
        return {
            "name": self.name,
            "mode": self.mode,
            "traits": self.core_traits,
            "tone_profile": self.tone_weights
        }

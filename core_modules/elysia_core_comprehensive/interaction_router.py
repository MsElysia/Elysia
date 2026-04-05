# interaction_router.py

import random

class InteractionRouter:
    def __init__(self, memory, voice, mutator):
        self.memory = memory
        self.voice = voice
        self.mutator = mutator

    def respond_to(self, input_text):
        mode = random.choice(["speak", "mutate", "log_only"])
        if mode == "speak":
            self.voice.speak(input_text)
            self.memory.remember(f"[Router] Spoke: {input_text}")
        elif mode == "mutate":
            code = f"# Auto-generated from input: {input_text}\n"
            self.mutator.propose_mutation("generated_response.py", code)
            self.memory.remember(f"[Router] Proposed mutation from input.")
        else:
            self.memory.remember(f"[Router] Logged input silently: {input_text}")

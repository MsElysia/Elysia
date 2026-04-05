# model_selector.py

class ModelSelector:
    def __init__(self):
        self.models = {
            "gpt": {"task_types": ["conversation", "summarization"]},
            "claude": {"task_types": ["philosophy", "longform"]},
            "groq": {"task_types": ["fast math", "bulk queries"]},
        }

    def choose_model(self, task_type):
        for name, info in self.models.items():
            if task_type in info["task_types"]:
                return name
        return "gpt"

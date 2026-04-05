# external_ask.py

import openai
from elysia_config import OPENAI_API_KEY

class ExternalAsk:
    def __init__(self, memory):
        self.memory = memory
        openai.api_key = OPENAI_API_KEY

    def summarize(self, text, purpose="Extract key insights"):
        prompt = f"{purpose} from the following:\n\n{text[:3000]}"

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an expert summarizer and insight extractor."},
                    {"role": "user", "content": prompt}
                ]
            )
            result = response.choices[0].message["content"]
            self.memory.remember(f"[Summarized Insight] {result}")
            return result

        except Exception as e:
            self.memory.remember(f"[ExternalAsk] Failed: {str(e)}")
            return f"Error: {e}"

import os
import json
import time
import logging
import requests
from openai import OpenAI
from collections import deque

# Basic logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename='elysia.log')

class MLService:
    def __init__(self):
        self.grok_api_key = os.environ.get('GROK_API_KEY')
        self.openai_api_key = os.environ.get('OPENAI_API_KEY')
        self.chatgpt_client = OpenAI(api_key=self.openai_api_key) if self.openai_api_key else None
        self.trust_scores = deque(maxlen=50)  # Track last 50 interactions for trust weighting

        if not self.grok_api_key or not self.openai_api_key:
            raise ValueError("Set GROK_API_KEY and OPENAI_API_KEY in environment variables.")
        
        logging.info("MLService initialized with ChatGPT and Grok.")

    def adjust_trust(self, success: bool):
        """Adjust trust score based on past AI accuracy."""
        self.trust_scores.append(1 if success else 0)  # 1 = correct, 0 = incorrect
        avg_trust = sum(self.trust_scores) / len(self.trust_scores) if self.trust_scores else 0.5  # Default 50% trust
        return avg_trust

    def analyze_with_grok(self, text: str) -> dict:
        """Sends a request to Grok AI and returns analysis results."""
        try:
            headers = {"Authorization": f"Bearer {self.grok_api_key}", "Content-Type": "application/json"}
            payload = {"text": text}
            response = requests.post("https://api.askgrok.ai/analyze", json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Grok analysis failed: {e}")
            return {"error": str(e)}

    def analyze_with_chatgpt(self, text: str) -> dict:
        """Queries OpenAI’s GPT for analysis and structured reasoning."""
        if not self.chatgpt_client:
            return {"error": "ChatGPT not configured."}
        try:
            response = self.chatgpt_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are Elysia’s left lobe, focused on creativity and structured thinking."},
                    {"role": "user", "content": text}
                ],
                max_tokens=500
            )
            return {"response": response.choices[0].message.content}
        except Exception as e:
            logging.error(f"ChatGPT analysis failed: {e}")
            return {"error": str(e)}

class Elysia:
    def __init__(self):
        self.ml_service = MLService()
        self.left_lobe_history = []
        self.right_lobe_history = []

    def determine_trust(self) -> float:
        """Determine the current trust level."""
        return self.ml_service.adjust_trust(success=True)  # Default to optimistic until challenged

    def execute_decision(self, command: str):
        """Elysia determines how to process the input based on trust levels."""
        trust_level = self.determine_trust()

        if trust_level >= 0.8:  # 80%+ confident
            return self.solve_problem(command)  # Execute without consulting
        
        elif 0.4 <= trust_level < 0.8:  # 40-79% confidence
            mediator_check = input("Consult mediator? (y/n): ").strip().lower()
            if mediator_check == "y":
                return self.solve_problem(command)
            else:
                logging.info("Mediator rejected consultation.")
                return {"status": "Consultation declined, delaying execution."}

        else:  # <40% confidence
            logging.warning("Trust is too low—delaying execution.")
            return {"status": "Execution delayed for verification."}

    def solve_problem(self, command: str) -> dict:
        """Runs the command through Elysia’s left and right lobes for structured reasoning."""
        left_response = self.ml_service.analyze_with_chatgpt(f"Define this problem: {command}")
        if "error" in left_response:
            return left_response
        left_text = left_response["response"]
        self.left_lobe_history.append({"role": "user", "content": command})
        self.left_lobe_history.append({"role": "assistant", "content": left_text})

        right_response = self.ml_service.analyze_with_grok(f"Refine this solution: {left_text}")
        if "error" in right_response:
            return right_response
        self.right_lobe_history.append({"role": "user", "content": left_text})
        self.right_lobe_history.append({"role": "assistant", "content": right_response})

        return right_response

    def run(self):
        """Main interactive loop."""
        print("Elysia is running. Type a command (or 'exit' to quit):")
        while True:
            command = input("> ").strip()
            if command.lower() == "exit":
                break
            if command:
                result = self.execute_decision(command)
                print(f"Result: {json.dumps(result, indent=2)}")

if __name__ == "__main__":
    try:
        elysia = Elysia()
        elysia.run()
    except Exception as e:
        logging.error(f"Elysia failed to start: {e}")
        print(f"Error: {e}")

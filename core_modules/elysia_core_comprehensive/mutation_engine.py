# mutation_engine.py

import os
import datetime
import openai
from sandbox import Sandbox
from ranking_engine import RankingEngine
from elysia_config import OPENAI_API_KEY

# Project Guardian Safety Integration
try:
    from project_guardian.safety import DevilsAdvocate as GuardianDevilsAdvocate
    from project_guardian.trust import TrustMatrix as GuardianTrustMatrix
    GUARDIAN_SAFETY_AVAILABLE = True
except ImportError:
    GUARDIAN_SAFETY_AVAILABLE = False
    print("[Warning] Project Guardian safety components not available.")


class MutationEngine:
    def __init__(self, memory):
        self.memory = memory
        self.sandbox = Sandbox(memory)
        self.ranker = RankingEngine(memory)
        openai.api_key = OPENAI_API_KEY

    def apply(self, filename, new_code, origin=None):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                old_code = f.read()

            backup_name = f"backups/{filename}.bak.{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.makedirs("backups", exist_ok=True)
            with open(backup_name, "w", encoding="utf-8") as backup:
                backup.write(old_code)

            with open(filename, "w", encoding="utf-8") as f:
                f.write(new_code)

            summary = f"[Mutation Applied] {filename} updated from dream."
            if origin:
                summary += f" Origin: {origin}"
            self.memory.remember(summary)
            print(summary)
            return summary

        except Exception as e:
            error_msg = f"[Mutation Error] {str(e)}"
            self.memory.remember(error_msg)
            print(error_msg)
            return error_msg

    def review_with_gpt(self, new_code, filename):
        prompt = f"""
You are a senior AI engineer reviewing a proposed mutation to the file '{filename}'.
Determine whether the mutation improves functionality, maintains safety, and avoids breaking logic.
If it is beneficial and safe, respond with "approve". If it is risky, unclear, or harmful, respond with "reject".

---
Code:
{new_code}
---

Your response:
"""
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an expert software safety reviewer."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=10,
                temperature=0.2,
            )
            reply = response.choices[0].message.content.strip().lower()
            self.memory.remember(f"[GPT Review] {reply}")
            return "approve" if "approve" in reply else "reject"

        except Exception as e:
            self.memory.remember(f"[GPT Review Error] {str(e)}")
            return "reject"

    def propose_mutation(self, filename, new_code):
        # Project Guardian Safety Review
        if GUARDIAN_SAFETY_AVAILABLE:
            if not hasattr(self, 'guardian_safety'):
                self.guardian_safety = GuardianDevilsAdvocate(self.memory)
                self.guardian_trust = GuardianTrustMatrix(self.memory)
            
            # Safety review
            safety_result = self.guardian_safety.review_mutation([new_code])
            if "suspicious" in safety_result.lower():
                return f"[Mutation Blocked] Safety review failed: {safety_result}"
            
            # Trust validation
            if not self.guardian_trust.validate_trust_for_action("mutation_engine", "mutation"):
                return "[Mutation Blocked] Insufficient trust for mutation operation"

        # Project Guardian Safety Review
        if GUARDIAN_SAFETY_AVAILABLE:
            if not hasattr(self, 'guardian_safety'):
                self.guardian_safety = GuardianDevilsAdvocate(self.memory)
                self.guardian_trust = GuardianTrustMatrix(self.memory)
            
            # Safety review
            safety_result = self.guardian_safety.review_mutation([new_code])
            if "suspicious" in safety_result.lower():
                return f"[Mutation Blocked] Safety review failed: {safety_result}"
            
            # Trust validation
            if not self.guardian_trust.validate_trust_for_action("mutation_engine", "mutation"):
                return "[Mutation Blocked] Insufficient trust for mutation operation"

        self.memory.remember(f"[Mutation Proposed] {filename}")

        score = self.ranker.rank(new_code)
        self.memory.remember(f"[Ranked Mutation] {score}")

        result = self.sandbox.simulate(filename, new_code)
        if not result:
            return "[Sandbox Failed] Mutation rejected."

        self.memory.remember(f"[Sandbox] âœ… {filename} passed simulation.")

        review = self.review_with_gpt(new_code, filename)
        if review != "approve":
            self.memory.remember(f"[Mutation Rejected by GPT] {review}")
            return "[GPT Review Failed] Mutation rejected."

        return self.apply(filename, new_code, origin="propose_mutation")

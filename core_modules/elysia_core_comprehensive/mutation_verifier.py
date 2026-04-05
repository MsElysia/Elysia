# mutation_verifier.py

class MutationVerifier:
    def __init__(self, memory):
        self.memory = memory

    def verify(self, filename, origin, diff_lines):
        summary = "\n".join(diff_lines[:10]) + ("\n..." if len(diff_lines) > 10 else "")
        decision = self.evaluate_diff(filename, origin, summary)
        self.memory.remember(f"[Verifier] {decision['message']}")
        return decision["approve"]

    def evaluate_diff(self, filename, origin, summary):
        # Very simple local emulation of what an AI review might do
        if "print(\"Refined logic.\")" in summary:
            return {
                "approve": False,
                "message": f"Rejected: {filename} contains trivial change from origin: {origin}"
            }
        if "class" not in summary:
            return {
                "approve": False,
                "message": f"Rejected: {filename} has no class definition. Origin: {origin}"
            }
        return {
            "approve": True,
            "message": f"Approved: {filename} mutation appears structured. Origin: {origin}"
        }

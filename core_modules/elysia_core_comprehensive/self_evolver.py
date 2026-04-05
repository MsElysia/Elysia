# self_evolver.py

from mutation_sandbox import MutationSandbox
from mutation_verifier import MutationVerifier

class SelfEvolver:
    def __init__(self, mutator, ranker, rollback, memory):
        self.mutator = mutator
        self.ranker = ranker
        self.rollback = rollback
        self.memory = memory
        self.sandbox = MutationSandbox(memory)
        self.verifier = MutationVerifier(memory)

    def evolve(self, filename, new_code):
        result = self.mutator.propose_mutation(filename, new_code)
        diff = self.mutator.mutation_log[-1]["diff"]
        score = self.ranker.rank_mutation_diff(diff)

        if score < 0.3:
            self.memory.remember(f"[SelfEvolver] Score too low ({score}), rolling back.")
            return self.rollback.restore_backup(filename, self.rollback.list_backups(filename)[0])

        # 🧪 Run simulation before approval
        if not self.sandbox.simulate(filename, new_code):
            self.memory.remember("[SelfEvolver] ❌ Mutation blocked in sandbox.")
            return "[SelfEvolver] Mutation blocked."

        diff = self.mutator.mutation_log[-1]["diff"]
        if not self.verifier.verify(filename, self.mutator.last_origin, diff):
            self.memory.remember("[SelfEvolver] ❌ Mutation blocked by verifier.")
            return "[SelfEvolver] Mutation blocked."

            return self.mutator.approve_last()

# consensus_engine.py

class ConsensusEngine:
    def __init__(self):
        self.votes = {}

    def cast_vote(self, voter, action):
        if action not in self.votes:
            self.votes[action] = []
        self.votes[action].append(voter)

    def decide(self):
        if not self.votes:
            return "idle"

        winner = max(self.votes.items(), key=lambda item: len(item[1]))
        self.votes = {}
        return winner[0]

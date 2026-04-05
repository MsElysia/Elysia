# trust_matrix.py

class TrustMatrix:
    def __init__(self):
        self.trust = {}

    def update_trust(self, name, delta):
        if name not in self.trust:
            self.trust[name] = 0.5
        self.trust[name] = max(0.0, min(1.0, self.trust[name] + delta))

    def get_trust(self, name):
        return self.trust.get(name, 0.5)

    def decay_all(self, amount=0.01):
        for k in self.trust:
            self.trust[k] = max(0.0, self.trust[k] - amount)

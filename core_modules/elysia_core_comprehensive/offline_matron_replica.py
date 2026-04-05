# offline_matron_replica.py

class OfflineMatronReplica:
    def __init__(self, identity_core):
        self.identity = identity_core

    def guide(self, question):
        summary = self.identity.describe()
        return f"{summary['name']} reflects: '{question}' aligns with my oath: {summary['oath']}'"

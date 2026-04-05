# digital_safehouse.py

class DigitalSafehouse:
    def __init__(self):
        self.secure_vault = {}

    def store(self, key, value):
        self.secure_vault[key] = value
        print(f"[Safehouse] Stored secret: {key}")

    def retrieve(self, key):
        return self.secure_vault.get(key, "[Not Found]")

    def list_keys(self):
        return list(self.secure_vault.keys())

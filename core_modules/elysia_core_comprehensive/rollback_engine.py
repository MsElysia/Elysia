# rollback_engine.py

import os

class RollbackEngine:
    def __init__(self, backup_folder="backups"):
        self.backup_folder = backup_folder

    def list_backups(self, filename_prefix):
        files = os.listdir(self.backup_folder)
        return sorted([f for f in files if f.startswith(filename_prefix)], reverse=True)

    def restore_backup(self, filename_prefix, backup_name):
        target = filename_prefix
        backup_path = os.path.join(self.backup_folder, backup_name)
        if not os.path.exists(backup_path):
            return f"[Rollback] Backup not found: {backup_name}"

        with open(backup_path, "r", encoding="utf-8") as f:
            restored = f.read()
        with open(target, "w", encoding="utf-8") as f:
            f.write(restored)
        return f"[Rollback] Restored {backup_name} to {target}"

"""
Monitor Elysia 8-Hour Learning Session
Check progress and statistics
"""

import os
import time
from pathlib import Path
from datetime import datetime

def monitor_session():
    """Monitor the learning session"""
    log_file = Path("elysia_learning_session.log")
    
    if not log_file.exists():
        print("⚠️  Learning session log not found yet.")
        print("   The session may still be starting...")
        return
    
    print("="*70)
    print("ELYSIA LEARNING SESSION MONITOR")
    print("="*70)
    print(f"Log file: {log_file}")
    print(f"Last updated: {datetime.fromtimestamp(log_file.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Read last 50 lines of log
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            recent_lines = lines[-50:] if len(lines) > 50 else lines
            
            print("Recent activity:")
            print("-"*70)
            for line in recent_lines:
                print(line.rstrip())
    except Exception as e:
        print(f"Error reading log: {e}")
    
    print()
    print("="*70)
    print("To see live updates, run: tail -f elysia_learning_session.log")
    print("Or on Windows: Get-Content elysia_learning_session.log -Wait -Tail 20")
    print("="*70)

if __name__ == "__main__":
    monitor_session()


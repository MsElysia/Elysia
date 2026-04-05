# interactive_elysia.py
# Interactive command-line interface for Elysia system

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from project_guardian.core import GuardianCore

class ElysiaInteractive:
    """Interactive interface for Elysia system."""
    
    def __init__(self):
        print("\n" + "="*70)
        print("ELYSIA INTERACTIVE INTERFACE")
        print("="*70)
        print("\nInitializing system...")
        
        self.core = GuardianCore({
            "enable_resource_monitoring": False,
            "enable_runtime_health_monitoring": False,
        })
        
        print("[OK] System initialized!\n")
        self.show_status()
    
    def show_status(self):
        """Show system status."""
        status = self.core.get_system_status()
        print("\n" + "-"*70)
        print("SYSTEM STATUS")
        print("-"*70)
        print(f"  Memories: {status.get('memory', {}).get('total_memories', 'N/A')}")
        print(f"  Categories: {len(status.get('memory', {}).get('categories', {}))}")
        print(f"  Uptime: {status.get('uptime', 'N/A')}")
        print("-"*70 + "\n")
    
    def show_menu(self):
        """Show main menu."""
        print("="*70)
        print("MAIN MENU")
        print("="*70)
        print("  1. Store Memory")
        print("  2. Recall Memories")
        print("  3. Show System Status")
        print("  4. Show Startup Verification")
        print("  5. Search Memories")
        print("  6. Exit")
        print("="*70)
    
    def store_memory(self):
        """Store a memory."""
        print("\n[Store Memory]")
        thought = input("Enter memory: ").strip()
        if not thought:
            print("  [ERROR] Memory cannot be empty")
            return
        
        category = input("Category (optional, press Enter for 'general'): ").strip() or "general"
        
        try:
            self.core.memory.remember(thought, category=category)
            print(f"  [OK] Memory stored in category '{category}'")
        except Exception as e:
            print(f"  [ERROR] Failed to store memory: {e}")
    
    def recall_memories(self):
        """Recall recent memories."""
        print("\n[Recall Memories]")
        try:
            count = input("How many memories? (default: 5): ").strip()
            count = int(count) if count else 5
            
            memories = self.core.memory.recall_last(count=count)
            
            if not memories:
                print("  [INFO] No memories found")
                return
            
            print(f"\n  Found {len(memories)} memories:\n")
            for i, mem in enumerate(memories, 1):
                thought = mem.get('thought', mem.get('content', 'N/A'))
                category = mem.get('category', 'N/A')
                timestamp = mem.get('timestamp', 'N/A')
                print(f"  {i}. [{category}] {thought}")
                print(f"     Time: {timestamp}\n")
        except ValueError:
            print("  [ERROR] Invalid number")
        except Exception as e:
            print(f"  [ERROR] Failed to recall memories: {e}")
    
    def show_startup_verification(self):
        """Show startup verification."""
        print("\n[Startup Verification]")
        try:
            verification = self.core.get_startup_verification()
            if verification:
                checks = verification.get("checks", [])
                successes = sum(1 for c in checks if c.get("status") == "success")
                warnings = sum(1 for c in checks if c.get("status") == "warning")
                failures = sum(1 for c in checks if c.get("status") == "failure")
                
                print(f"\n  Total Checks: {len(checks)}")
                print(f"  [OK] Successes: {successes}")
                if warnings > 0:
                    print(f"  [WARN] Warnings: {warnings}")
                if failures > 0:
                    print(f"  [FAIL] Failures: {failures}")
                
                print("\n  Component Status:")
                for check in checks[:10]:  # Show first 10
                    component = check.get("component", "Unknown")
                    status = check.get("status", "unknown")
                    status_icon = {
                        "success": "[OK]",
                        "warning": "[WARN]",
                        "failure": "[FAIL]"
                    }.get(status, "[?]")
                    print(f"    {status_icon} {component}")
        except Exception as e:
            print(f"  [ERROR] Failed to get verification: {e}")
    
    def search_memories(self):
        """Search memories by category."""
        print("\n[Search Memories]")
        category = input("Enter category to search (or press Enter for all): ").strip()
        
        try:
            memories = self.core.memory.recall_last(count=100)  # Get more to search
            
            if category:
                filtered = [m for m in memories if m.get('category', '').lower() == category.lower()]
            else:
                filtered = memories
            
            if not filtered:
                print(f"  [INFO] No memories found" + (f" in category '{category}'" if category else ""))
                return
            
            print(f"\n  Found {len(filtered)} memories" + (f" in category '{category}'" if category else "") + ":\n")
            for i, mem in enumerate(filtered[:10], 1):  # Show first 10
                thought = mem.get('thought', mem.get('content', 'N/A'))
                cat = mem.get('category', 'N/A')
                print(f"  {i}. [{cat}] {thought[:60]}...")
        except Exception as e:
            print(f"  [ERROR] Failed to search memories: {e}")
    
    def run(self):
        """Run interactive loop."""
        while True:
            self.show_menu()
            choice = input("\nEnter choice (1-6): ").strip()
            
            if choice == "1":
                self.store_memory()
            elif choice == "2":
                self.recall_memories()
            elif choice == "3":
                self.show_status()
            elif choice == "4":
                self.show_startup_verification()
            elif choice == "5":
                self.search_memories()
            elif choice == "6":
                print("\n[Shutting down...]")
                self.core.shutdown()
                print("[OK] System shut down. Goodbye!\n")
                break
            else:
                print("\n[ERROR] Invalid choice. Please enter 1-6.")
            
            input("\nPress Enter to continue...")
            print()

def main():
    """Main entry point."""
    try:
        interface = ElysiaInteractive()
        interface.run()
    except KeyboardInterrupt:
        print("\n\n[Shutting down...]")
        try:
            interface.core.shutdown()
        except:
            pass
        print("[OK] System shut down. Goodbye!\n")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()


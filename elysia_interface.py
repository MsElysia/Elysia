#!/usr/bin/env python3
"""
Elysia Unified Interface
Single, easy-to-use interface for all Elysia functions and information
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime
import webbrowser
import threading
import time

# Add paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "project_guardian"))

# Attach mode: connect to running elysia.py via status API
try:
    from elysia_config import get_status_url
    STATUS_URL = get_status_url()
except Exception:
    STATUS_URL = "http://127.0.0.1:8888"

class ElysiaInterface:
    """Unified interface for all Elysia functions."""

    def __init__(self, attach_only: bool = False):
        self.core = None
        self.ui_panel = None
        self.running = False
        self.autonomous_system = None
        self.autonomous_thread = None
        self.attach_only = attach_only  # Connect to running backend via status API
        
    def show_main_menu(self):
        """Display main menu."""
        print("\n" + "="*70)
        print(" " * 20 + "ELYSIA UNIFIED INTERFACE")
        print("="*70)
        print()
        print("  [1] View System Status")
        print("  [2] Chat with Elysia")
        print("  [3] View Memories & Learning")
        print("  [4] Control System")
        print("  [5] View Logs")
        print("  [6] Introspection & Analysis")
        print("  [7] Open Web Dashboard")
        print("  [8] System Settings")
        print("  [9] Exit")
        print()
        if self.attach_only:
            print("  [ATTACHED] Connected to backend at", STATUS_URL)
        elif self.autonomous_system and self.autonomous_system.running:
            print("  [AUTONOMOUS] System is running in background")
            print("              - Learning: Active")
            print("              - Internet scanning: Active")
            print("              - All modules: Engaged")
        print()
        print("="*70)
        
    def _fetch_status_from_api(self):
        """Fetch status from running backend (attach mode)."""
        try:
            import urllib.request
            req = urllib.request.Request(f"{STATUS_URL}/status")
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            return {"error": str(e), "hint": "Is elysia.py running?"}

    def _fetch_health_from_api(self):
        """Fetch /health JSON from backend (attach mode)."""
        try:
            import urllib.request
            req = urllib.request.Request(f"{STATUS_URL}/health")
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            return {"error": str(e)}

    def view_status(self):
        """View comprehensive system status."""
        print("\n" + "="*70)
        print("SYSTEM STATUS")
        print("="*70)

        # Attach mode: fetch from status API
        if self.attach_only:
            status = self._fetch_status_from_api()
            if "error" in status:
                print(f"\n[WARN] Could not reach backend: {status.get('error')}")
                print(f"       {status.get('hint', '')}")
            else:
                print(f"\nUptime: {status.get('uptime', 'N/A')}")
                print("Components:")
                for comp, available in status.get("components", {}).items():
                    icon = "[OK]" if available else "[OFF]"
                    print(f"   {icon} {comp}: {'Active' if available else 'Inactive'}")
                print(f"Integrated Modules: {status.get('components', {}).get('integrated_modules', 0)}")
                print("\n(Status from backend via API)")
            input("\nPress Enter to continue...")
            return

        # Check autonomous system status
        if self.autonomous_system:
            try:
                auto_status = self.autonomous_system.get_status()
                print(f"\nAutonomous System:")
                print(f"   Status: {'Running' if self.autonomous_system.running else 'Stopped'}")
                print(f"   Uptime: {auto_status.get('uptime', 'N/A')}")
                print(f"\n   Components:")
                for comp, available in auto_status.get('components', {}).items():
                    icon = "[OK]" if available else "[OFF]"
                    print(f"      {icon} {comp}: {'Active' if available else 'Inactive'}")
            except Exception as e:
                print(f"   Error getting autonomous status: {e}")
        
        if not self.core:
            self._init_core()
        
        if self.core:
            try:
                status = self.core.get_system_status()
                print(f"\nInterface System:")
                print(f"   Memory System:")
                print(f"      Total Memories: {status.get('memory', {}).get('total_memories', 'N/A')}")
                print(f"      Categories: {len(status.get('memory', {}).get('categories', {}))}")
                
                print(f"\n   Components:")
                components = status.get('components', {})
                for comp, active in components.items():
                    icon = "[OK]" if active else "[OFF]"
                    print(f"      {icon} {comp}: {'Active' if active else 'Inactive'}")
                
                print(f"\n   System Info:")
                print(f"      Uptime: {status.get('uptime', 'N/A')}")
                print(f"      Active Tasks: {status.get('active_tasks', 0)}")
                
                # Display capabilities
                try:
                    from project_guardian.capabilities import get_capabilities, format_capabilities_text
                    capabilities = get_capabilities()
                    capabilities_text = format_capabilities_text(capabilities)
                    print(f"\n{capabilities_text}")
                except Exception as e:
                    print(f"\n   [WARN] Could not load capabilities: {e}")
                
            except Exception as e:
                print(f"Error getting status: {e}")
        else:
            print("Interface system not initialized")
        
        input("\nPress Enter to continue...")
    
    def chat_with_elysia(self):
        """Chat interface."""
        print("\n" + "="*70)
        print("CHAT WITH ELYSIA")
        print("="*70)
        print("\nType 'back' to return to main menu, 'help' for commands")
        print("-"*70)
        
        if not self.attach_only:
            if not self.core:
                self._init_core()
        
        # Reduce log noise during chat (heartbeat embedding warnings)
        _log = __import__("logging").getLogger("project_guardian.memory_vector")
        _old_level = _log.level
        _log.setLevel(__import__("logging").ERROR)
        try:
            if self.core or self.attach_only:
                print("\nElysia: Hello! How can I help you today?\n")
                
                while True:
                    try:
                        user_input = input("You: ").strip()
                        
                        if user_input.lower() in ['back', 'exit', 'quit']:
                            break
                        elif user_input.lower() == 'help':
                            print("\nCommands:")
                            print("  'status' - Show system status")
                            print("  'memories' - View recent memories")
                            print("  'what are you thinking' - See what Elysia is focusing on")
                            print("  'back' - Return to main menu")
                            continue
                        elif user_input.lower() == 'status':
                            self.view_status()
                            continue
                        elif user_input.lower() == 'memories':
                            self.view_memories()
                            continue
                        elif 'thinking' in user_input.lower() or 'focus' in user_input.lower():
                            self.view_introspection()
                            continue
                        
                        # "What have you learned" / "what do you know" -> show recent memories
                        lower = user_input.lower()
                        if any(x in lower for x in ("learned", "learn", "what you know", "what do you know", "tell me what", "memories", "remember")):
                            self._chat_show_learned()
                            continue
                        
                        # Attach mode: use backend /chat so AI (API keys) is used
                        if self.attach_only:
                            reply, err = self._chat_via_backend(user_input)
                            if reply:
                                print(f"\nElysia: {reply}\n")
                            elif err:
                                print(f"\nElysia: [Could not connect to AI] {err}")
                                print("         (Make sure elysia.py is running and API keys are in the API keys folder.)\n")
                            else:
                                print("\nElysia: No response from backend.\n")
                        else:
                            # Simple response when not attached
                            print(f"\nElysia: I understand you said '{user_input}'. ")
                            print("         (AI responses available when OpenAI API key is configured)")
                        
                    except KeyboardInterrupt:
                        break
                    except Exception as e:
                        print(f"Error: {e}")
            else:
                print("System not initialized")
                input("\nPress Enter to continue...")
        finally:
            _log.setLevel(_old_level)
    
    def _chat_show_learned(self):
        """Show a short 'what I've learned' summary from recent memories."""
        if self.attach_only:
            print(
                "\nElysia: In attach mode, memories live on the backend process. "
                "Open the Web Control Panel (menu 7) or check /status for guardian_status.\n"
            )
            return
        if not self.core or not hasattr(self.core, "memory"):
            print("\nElysia: I don't have memory access right now.\n")
            return
        try:
            mem = self.core.memory
            if hasattr(mem, "recall_last"):
                recent = mem.recall_last(count=10)
            elif hasattr(mem, "memory_log"):
                recent = (mem.memory_log or [])[-10:]
            else:
                recent = []
            if not recent:
                print("\nElysia: I don't have recent memories to share yet. Keep interacting!\n")
                return
            print("\nElysia: Here's some of what I've learned recently:\n")
            for i, m in enumerate(recent[-8:], 1):
                thought = (m.get("thought") or m.get("summary") or str(m))[:200]
                when = m.get("time") or m.get("timestamp") or ""
                if when and len(str(when)) > 20:
                    when = str(when)[:19]
                print(f"   {i}. [{when}] {thought}")
            print()
        except Exception as e:
            print(f"\nElysia: I had trouble recalling memories: {e}\n")
    
    def _chat_via_backend(self, message: str):
        """POST message to backend /chat. Returns (reply_text, error_string)."""
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{STATUS_URL}/chat",
                data=json.dumps({"message": message}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
                reply = (data.get("reply") or "").strip()
                err = (data.get("error") or "").strip()
                return reply, err
        except Exception as e:
            return "", str(e)
    
    def view_memories(self):
        """View memories and learning."""
        print("\n" + "="*70)
        print("MEMORIES & LEARNING")
        print("="*70)

        if self.attach_only:
            st = self._fetch_status_from_api()
            if "error" in st:
                print(f"\n[WARN] Could not reach backend: {st.get('error')}")
            else:
                gs = st.get("guardian_status") or {}
                mem = gs.get("memory") or {}
                if mem:
                    print(f"\n(Memory summary from backend /status)")
                    print(f"   Total memories: {mem.get('total_memories', 'N/A')}")
                    cats = mem.get("categories")
                    if isinstance(cats, dict):
                        print(f"   Categories: {len(cats)}")
                else:
                    print("\n(No memory block in backend status yet — backend may still be initializing.)")
                du = st.get("dashboard_url")
                if du:
                    print(f"\n   Full detail: Web Control Panel — {du}")
            input("\nPress Enter to continue...")
            return
        
        if not self.core:
            self._init_core()
        
        if self.core:
            try:
                status = self.core.get_system_status()
                memory_info = status.get('memory', {})
                
                print(f"\nMemory Statistics:")
                print(f"   Total Memories: {memory_info.get('total_memories', 0)}")
                print(f"   Categories: {len(memory_info.get('categories', {}))}")
                
                # Try to get recent memories
                if hasattr(self.core, 'memory') and hasattr(self.core.memory, 'memory_log'):
                    memories = self.core.memory.memory_log
                    if memories:
                        print(f"\nRecent Memories (last 5):")
                        print("-"*70)
                        for mem in memories[-5:]:
                            thought = mem.get('thought', 'N/A')[:100]
                            time = mem.get('time', 'N/A')
                            print(f"   [{time}] {thought}...")
                    else:
                        print("\nNo memories stored yet.")
                
                print("\nSearch Memories:")
                search = input("   Enter search term (or press Enter to skip): ").strip()
                if search:
                    # Simple search (can be enhanced)
                    print(f"\nSearching for: {search}")
                    print("(Full search available in Web UI)")
                
            except Exception as e:
                print(f"Error: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("System not initialized")
        
        input("\nPress Enter to continue...")
    
    def control_system(self):
        """System control functions."""
        print("\n" + "="*70)
        print("SYSTEM CONTROL")
        print("="*70)

        if self.attach_only:
            print(
                "\n[Attach mode] Pause/resume and deep control run on the backend elysia.py process.\n"
                "Use the Web Control Panel or backend console; local Guardian is not loaded.\n"
            )
            input("\nPress Enter to continue...")
            return
        
        if not self.core:
            self._init_core()
        
        print("\nControl Options:")
        print("  [1] Pause System")
        print("  [2] Resume System")
        print("  [3] Create Memory Snapshot")
        print("  [4] Trigger Introspection Cycle")
        print("  [5] Back to Main Menu")
        
        choice = input("\nChoice: ").strip()
        
        if choice == "1":
            print("\nPausing system...")
            # Implementation needed
            print("(Feature available in Web UI)")
        elif choice == "2":
            print("\nResuming system...")
            # Implementation needed
            print("(Feature available in Web UI)")
        elif choice == "3":
            print("\nCreating memory snapshot...")
            if self.core and hasattr(self.core, 'create_snapshot'):
                try:
                    self.core.create_snapshot()
                    print("[OK] Snapshot created")
                except Exception as e:
                    print(f"Error: {e}")
        elif choice == "4":
            print("\nTriggering introspection cycle...")
            print("(Feature available in Web UI)")
        
        input("\nPress Enter to continue...")
    
    def view_logs(self):
        """View system logs."""
        print("\n" + "="*70)
        print("VIEW LOGS")
        print("="*70)
        
        print("\nLog Files:")
        print("  [1] Main log (elysia_unified.log)")
        print("  [2] Unified log (unified_autonomous_system.log)")
        print("  [3] View last 50 lines of main log")
        print("  [4] Back to Main Menu")
        
        choice = input("\nChoice: ").strip()
        
        if choice == "1":
            log_file = project_root / "elysia_unified.log"
            if log_file.exists():
                print(f"\nOpening {log_file}...")
                os.startfile(str(log_file))
            else:
                print("Log file not found. System may not have been started.")
        elif choice == "2":
            log_file = project_root / "organized_project" / "data" / "logs" / "unified_autonomous_system.log"
            if log_file.exists():
                print(f"\nOpening {log_file}...")
                print("(This file is very large - may take time to open)")
                os.startfile(str(log_file))
            else:
                print("Log file not found.")
        elif choice == "3":
            log_file = project_root / "elysia_unified.log"
            if log_file.exists():
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                        print("\n" + "="*70)
                        print("LAST 50 LINES")
                        print("="*70)
                        for line in lines[-50:]:
                            print(line.rstrip())
                except Exception as e:
                    print(f"Error reading log: {e}")
            else:
                print("Log file not found.")
        
        input("\nPress Enter to continue...")
    
    def view_introspection(self):
        """View introspection and analysis."""
        print("\n" + "="*70)
        print("INTROSPECTION & ANALYSIS")
        print("="*70)

        if self.attach_only:
            print(
                "\n[Attach mode] Introspection data is on the backend. "
                "Open the Web Control Panel (menu 7) or inspect backend logs.\n"
            )
            input("\nPress Enter to continue...")
            return
        
        if not self.core:
            self._init_core()
        
        print("\nAnalysis Options:")
        print("  [1] What is Elysia thinking about?")
        print("  [2] Behavior Patterns")
        print("  [3] Memory Health")
        print("  [4] Focus Analysis (last 24h)")
        print("  [5] Back to Main Menu")
        
        choice = input("\nChoice: ").strip()
        
        if choice == "1":
            print("\nWhat Elysia is Thinking About:")
            print("-"*70)
            print("(Full introspection available in Web UI)")
            print("Open Web Dashboard for detailed analysis.")
        elif choice == "2":
            print("\nBehavior Patterns:")
            print("(Available in Web UI - Introspection tab)")
        elif choice == "3":
            print("\nMemory Health:")
            print("(Available in Web UI - Introspection tab)")
        elif choice == "4":
            print("\nFocus Analysis:")
            print("(Available in Web UI - Introspection tab)")
        
        input("\nPress Enter to continue...")
    
    def open_web_dashboard(self):
        """Open web dashboard."""
        print("\n" + "="*70)
        print("OPENING WEB DASHBOARD")
        print("="*70)

        if self.attach_only:
            print("\n[Attach mode] Opening dashboard served by the backend (no local GuardianCore).")
            st = self._fetch_status_from_api()
            h = self._fetch_health_from_api()
            url = None
            if isinstance(st, dict) and st.get("dashboard_url"):
                url = st["dashboard_url"]
            elif isinstance(h, dict) and h.get("dashboard_url"):
                url = h["dashboard_url"]
            if not url:
                url = "http://127.0.0.1:5000"
            print(f"   URL: {url}")
            try:
                webbrowser.open(url)
                print("[OK] Browser open requested.")
            except Exception as e:
                print(f"[INFO] Open manually: {url} ({e})")
            input("\nPress Enter to continue...")
            return
        
        print("\nStarting Web UI...")
        
        # Try multiple sources for GuardianCore instance
        guardian = None
        guardian_source = None
        
        # Source 1: Use self.core if available (preferred - already initialized)
        if self.core:
            guardian = self.core
            guardian_source = "self.core"
            import inspect
            module_path = inspect.getfile(type(guardian))
            print(f"[DEBUG] Using GuardianCore from: {guardian_source}")
            print(f"[DEBUG] GuardianCore module path: {module_path}")
            print(f"[DEBUG] GuardianCore instance exists: {guardian is not None}")
            print(f"[DEBUG] UI panel exists: {hasattr(guardian, 'ui_panel') and guardian.ui_panel is not None}")
        
        # Source 2: Use autonomous_system.guardian if available
        if not guardian and self.autonomous_system and hasattr(self.autonomous_system, 'guardian'):
            guardian = self.autonomous_system.guardian
            guardian_source = "autonomous_system.guardian"
            import inspect
            module_path = inspect.getfile(type(guardian))
            print(f"[DEBUG] Using GuardianCore from: {guardian_source}")
            print(f"[DEBUG] GuardianCore module path: {module_path}")
            print(f"[DEBUG] GuardianCore instance exists: {guardian is not None}")
            print(f"[DEBUG] UI panel exists: {hasattr(guardian, 'ui_panel') and guardian.ui_panel is not None}")
        
        # Source 3: Fall back to singleton
        if not guardian:
            try:
                from project_guardian.guardian_singleton import get_guardian_core
                import inspect
                singleton_module = inspect.getfile(get_guardian_core)
                print(f"[DEBUG] Attempting to get GuardianCore from singleton")
                print(f"[DEBUG] Singleton module path: {singleton_module}")
                
                # Use config with UI enabled
                config = {
                    "ui_config": {
                        "enabled": True,
                        "auto_start": True,
                        "host": "127.0.0.1",
                        "port": 5000
                    }
                }
                guardian = get_guardian_core(config=config)
                guardian_source = "singleton"
                print(f"[DEBUG] GuardianCore from singleton: {guardian is not None}")
                if guardian:
                    import inspect
                    module_path = inspect.getfile(type(guardian))
                    print(f"[DEBUG] GuardianCore module path: {module_path}")
                    print(f"[DEBUG] UI panel exists: {hasattr(guardian, 'ui_panel') and guardian.ui_panel is not None}")
            except Exception as e:
                print(f"[ERROR] Failed to get GuardianCore from singleton: {e}")
                import traceback
                traceback.print_exc()
                guardian = None
        
        # Verify guardian and UI panel
        if not guardian:
            print("\n[ERROR] Could not get GuardianCore instance from any source")
            print("  Tried: self.core, autonomous_system.guardian, singleton")
            return
        
        if not hasattr(guardian, 'ui_panel') or guardian.ui_panel is None:
            print(f"\n[WARN] GuardianCore found but UI panel not initialized")
            print(f"  GuardianCore source: {guardian_source}")
            print(f"  Attempting to initialize UI panel...")
            
            # Try to initialize UI panel
            try:
                # Use start_ui_panel method if available (preferred)
                if hasattr(guardian, 'start_ui_panel'):
                    print(f"[DEBUG] Using start_ui_panel() method...")
                    guardian.start_ui_panel(host="127.0.0.1", port=5000, debug=False)
                    print(f"[OK] UI panel initialized via start_ui_panel()")
                # Fallback: create UI panel directly
                else:
                    print(f"[DEBUG] Creating UI panel directly...")
                    from project_guardian.ui_control_panel import UIControlPanel
                    guardian.ui_panel = UIControlPanel(
                        orchestrator=guardian,
                        host="127.0.0.1",
                        port=5000
                    )
                    print(f"[DEBUG] UI panel created, starting server...")
                    guardian.ui_panel.start(debug=False, source="elysia_interface.open_web_dashboard")
                    print(f"[OK] UI panel initialized and started")
                
                if not hasattr(guardian, 'ui_panel') or guardian.ui_panel is None:
                    print(f"[ERROR] UI panel initialization failed - ui_panel is still None")
                    return
            except Exception as e:
                print(f"[ERROR] Failed to initialize UI panel: {e}")
                import traceback
                traceback.print_exc()
                return
        
        # Verify server is started (start() is idempotent, safe to call if already started)
        if not guardian.ui_panel.running:
            print(f"[DEBUG] Server not running, starting...")
            try:
                guardian.ui_panel.start(debug=False, source="elysia_interface.open_web_dashboard")
                print(f"[OK] Server start() called")
            except Exception as e:
                print(f"[ERROR] Failed to start server: {e}")
                if hasattr(guardian.ui_panel, '_server_error') and guardian.ui_panel._server_error:
                    print(f"  Server error: {guardian.ui_panel._server_error}")
                import traceback
                traceback.print_exc()
                return
        else:
            print(f"[DEBUG] Server already running (idempotent check passed)")
        
        # Wait for UI to initialize and get actual port
        time.sleep(2)
        try:
            # Use the same guardian instance we found earlier
            if guardian and guardian.ui_panel:
                actual_port = guardian.ui_panel._actual_port or guardian.ui_panel.port
                actual_host = guardian.ui_panel.host
                url = f"http://{actual_host}:{actual_port}"
                
                # Wait for server to be ready before opening browser
                if hasattr(guardian.ui_panel, '_wait_for_server_ready'):
                    max_wait = 10
                    waited = 0
                    while waited < max_wait:
                        if guardian.ui_panel._wait_for_server_ready(timeout=1.0):
                            break
                        waited += 1
                        time.sleep(0.5)
                
                print("\nOpening browser...")
                try:
                    webbrowser.open(url)
                    print(f"\n[OK] Browser opened!")
                except Exception:
                    print(f"\n[INFO] Please open browser manually: {url}")
                
                print(f"  Web Dashboard: {url}")
            else:
                print(f"\n[WARN] UI panel not available, cannot determine URL")
                print(f"  GuardianCore source: {guardian_source if 'guardian_source' in locals() else 'unknown'}")
                print(f"  GuardianCore exists: {guardian is not None}")
                print(f"  UI panel attribute exists: {hasattr(guardian, 'ui_panel') if guardian else False}")
                if guardian and hasattr(guardian, 'ui_panel'):
                    print(f"  UI panel value: {guardian.ui_panel}")
                print("  Try: http://127.0.0.1:5000")
        except Exception as e:
            print(f"\n[WARN] Could not determine server URL: {e}")
            import traceback
            traceback.print_exc()
            print("  Try: http://127.0.0.1:5000")
        print("\nNote: Keep this window open to keep the server running")
        print("Press Enter to return to menu (server will continue running)...")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
    
    def system_settings(self):
        """System settings."""
        print("\n" + "="*70)
        print("SYSTEM SETTINGS")
        print("="*70)
        
        print("\nSettings:")
        print("  [1] View Configuration")
        print("  [2] Check Dependencies")
        print("  [3] Test Components")
        print("  [4] Back to Main Menu")
        
        choice = input("\nChoice: ").strip()
        
        if choice == "1":
                print("\nConfiguration:")
                print("  Config files: config/")
                print("  Memory: guardian_memory.json")
                print("  Logs: organized_project/data/logs/")
        elif choice == "2":
            print("\nChecking Dependencies...")
            deps = {
                "Flask": False,
                "Flask-SocketIO": False,
                "Python": True
            }
            try:
                import flask
                deps["Flask"] = True
            except ImportError:
                pass
            try:
                import flask_socketio
                deps["Flask-SocketIO"] = True
            except ImportError:
                pass
            
            for dep, status in deps.items():
                icon = "[OK]" if status else "[MISSING]"
                print(f"   {icon} {dep}")
        elif choice == "3":
            print("\nTesting Components...")
            # Run quick test
            try:
                from project_guardian.runtime_loop_core import RuntimeLoop
                print("   [OK] RuntimeLoop: OK")
            except Exception as e:
                print(f"   [ERROR] RuntimeLoop: {e}")
        
        input("\nPress Enter to continue...")
    
    def _init_core(self):
        """Initialize GuardianCore (uses singleton to prevent double initialization)."""
        if self.attach_only:
            return
        if not self.core:
            try:
                from project_guardian.guardian_singleton import get_guardian_core
                # Use singleton to get existing instance or create new one
                config = {
                    "enable_resource_monitoring": False,
                    "enable_runtime_health_monitoring": False,
                }
                self.core = get_guardian_core(config=config)
                if self.core:
                    print("[OK] System initialized (using singleton)")
                else:
                    print("[WARN] Could not get GuardianCore instance")
            except Exception as e:
                print(f"Error initializing: {e}")
                import traceback
                traceback.print_exc()
                self.core = None
    
    def _start_autonomous_system(self):
        """Start the full autonomous system in background."""
        print("\nStarting autonomous system...")
        try:
            from elysia import UnifiedElysiaSystem
            
            try:
                from elysia_config import get_elysia_config
                config = get_elysia_config()
            except Exception:
                config = {
                    "memory_file": "guardian_memory.json",
                    "trust_file": "enhanced_trust.json",
                    "tasks_file": "enhanced_tasks.json",
                }
            self.autonomous_system = UnifiedElysiaSystem(config=config)
            self.autonomous_system.start()
            
            print("[OK] Autonomous system started")
            print("   - Internet scanning: Active")
            print("   - Learning systems: Active")
            print("   - All modules: Engaged")
            
            return True
        except Exception as e:
            print(f"[WARN] Could not start autonomous system: {e}")
            print("   Continuing with interface only...")
            return False
    
    def run(self):
        """Main interface loop."""
        print("\n" + "="*70)
        print(" " * 15 + "WELCOME TO ELYSIA")
        print("="*70)
        if self.attach_only:
            print("\n[Attach mode] Connecting to running backend at", STATUS_URL)
            max_wait = float(os.environ.get("ELYSIA_STARTUP_WAIT_SEC", "300"))
            interval = float(os.environ.get("ELYSIA_STARTUP_POLL_SEC", "3"))
            t_start = time.time()
            deadline = t_start + max_wait
            attempt = 0
            status = self._fetch_status_from_api()
            while "error" in status and time.time() < deadline:
                attempt += 1
                elapsed = time.time() - t_start
                err = str(status.get("error", ""))
                print(
                    f"       Backend still booting… {elapsed:.0f}s elapsed, "
                    f"retry {attempt} (max {max_wait:.0f}s) — {err[:140]}"
                )
                time.sleep(interval)
                status = self._fetch_status_from_api()
            if "error" in status:
                print(f"\n[WARN] Backend not reachable after {max_wait:.0f}s: {status.get('error')}")
                print(
                    "       Timeout — the backend may still be initializing (memory, vectors, Guardian). "
                    "This is not necessarily 'start elysia.py first'."
                )
                print("       Check the backend console or elysia_unified.log, or increase ELYSIA_STARTUP_WAIT_SEC.")
                input("Press Enter to exit...")
                return
            print("[OK] Backend connected")
            if isinstance(status, dict) and status.get("startup_phase"):
                print(f"     startup_phase: {status.get('startup_phase')}")
            print("[Attach mode] Using remote backend only; local Guardian init skipped")
        else:
            print("\nInitializing...")
            self._start_autonomous_system()
            self._init_core()
        
        # Enable embeddings after menu is shown (startup complete)
        if self.core and hasattr(self.core, 'memory') and hasattr(self.core.memory, 'enable_embeddings'):
            self.core.memory.enable_embeddings()
        
        while True:
            try:
                self.show_main_menu()
                choice = input("Choice: ").strip()
                
                if choice == "1":
                    self.view_status()
                elif choice == "2":
                    self.chat_with_elysia()
                elif choice == "3":
                    self.view_memories()
                elif choice == "4":
                    self.control_system()
                elif choice == "5":
                    self.view_logs()
                elif choice == "6":
                    self.view_introspection()
                elif choice == "7":
                    self.open_web_dashboard()
                elif choice == "8":
                    self.system_settings()
                elif choice == "9" or choice.lower() in ['exit', 'quit']:
                    print("\nShutting down...")
                    if not self.attach_only and self.autonomous_system:
                        try:
                            self.autonomous_system.shutdown()
                            print("[OK] Autonomous system stopped")
                        except Exception:
                            pass
                    if self.core:
                        try:
                            self.core.shutdown()
                            print("[OK] Interface system stopped")
                        except Exception:
                            pass
                    print("\nGoodbye!")
                    break
                else:
                    print("\nInvalid choice. Please try again.")
                    time.sleep(1)
                    
            except KeyboardInterrupt:
                print("\n\nShutting down...")
                if not self.attach_only and self.autonomous_system:
                    try:
                        self.autonomous_system.shutdown()
                        print("[OK] Autonomous system stopped")
                    except Exception:
                        pass
                # Shutdown core
                if self.core:
                    try:
                        self.core.shutdown()
                        print("[OK] Interface system stopped")
                    except Exception:
                        pass
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"\nError: {e}")
                import traceback
                traceback.print_exc()
                input("\nPress Enter to continue...")


if __name__ == "__main__":
    attach = "--attach-only" in sys.argv or "-a" in sys.argv
    if not attach:
        try:
            from elysia_config import probe_backend_alive

            if probe_backend_alive():
                print(
                    "Backend already running — attaching new interface "
                    "(no local GuardianCore / memory / vector startup).\n"
                )
                attach = True
        except Exception:
            pass
    interface = ElysiaInterface(attach_only=attach)
    interface.run()


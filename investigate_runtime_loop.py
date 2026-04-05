#!/usr/bin/env python3
"""
Investigate Runtime Loop Import Issue
Tests why ElysiaRuntimeLoop import is failing
"""

import sys
from pathlib import Path

# Add paths like run_elysia_unified.py does
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "core_modules" / "elysia_core_comprehensive"))
sys.path.insert(0, str(project_root / "project_guardian"))

print("="*70)
print("INVESTIGATING RUNTIME LOOP IMPORT ISSUE")
print("="*70)

# Test 1: Try importing the module
print("\n[1] Testing import of elysia_runtime_loop...")
try:
    import elysia_runtime_loop
    print("✅ Module imported successfully")
    print(f"   Module location: {elysia_runtime_loop.__file__}")
except ImportError as e:
    print(f"❌ ImportError: {e}")
    import traceback
    traceback.print_exc()
except Exception as e:
    print(f"❌ Error importing module: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

# Test 2: Try importing the class
print("\n[2] Testing import of ElysiaRuntimeLoop class...")
try:
    from elysia_runtime_loop import ElysiaRuntimeLoop
    print("✅ ElysiaRuntimeLoop class imported successfully")
except ImportError as e:
    print(f"❌ ImportError: {e}")
    import traceback
    traceback.print_exc()
except Exception as e:
    print(f"❌ Error importing class: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Try instantiating the class
print("\n[3] Testing instantiation of ElysiaRuntimeLoop...")
try:
    from elysia_runtime_loop import ElysiaRuntimeLoop
    loop = ElysiaRuntimeLoop()
    print("✅ ElysiaRuntimeLoop instantiated successfully")
    print(f"   Type: {type(loop)}")
except Exception as e:
    print(f"❌ Error instantiating: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

# Test 4: Check if project_guardian RuntimeLoop is available as alternative
print("\n[4] Testing project_guardian RuntimeLoop as alternative...")
try:
    from project_guardian.runtime_loop_core import RuntimeLoop
    print("✅ project_guardian.RuntimeLoop imported successfully")
    
    # Try instantiating
    try:
        pg_loop = RuntimeLoop()
        print("✅ project_guardian.RuntimeLoop instantiated successfully")
        print(f"   Type: {type(pg_loop)}")
        print(f"   Has start() method: {hasattr(pg_loop, 'start')}")
    except Exception as e:
        print(f"❌ Error instantiating project_guardian.RuntimeLoop: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
except ImportError as e:
    print(f"❌ ImportError: {e}")
except Exception as e:
    print(f"❌ Error: {type(e).__name__}: {e}")

# Test 5: Check dependencies
print("\n[5] Checking dependencies...")
dependencies = [
    "enhanced_memory_core",
    "enhanced_trust_matrix", 
    "enhanced_task_engine",
    "voicethread",
    "mutation_engine"
]

for dep in dependencies:
    try:
        __import__(dep)
        print(f"✅ {dep} available")
    except ImportError:
        print(f"❌ {dep} NOT available (might cause import failure)")

print("\n" + "="*70)
print("INVESTIGATION COMPLETE")
print("="*70)


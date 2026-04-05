# usage_examples.py
# Comprehensive examples of how to use the Elysia system

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from project_guardian.core import GuardianCore

print("="*70)
print("ELYSIA SYSTEM - USAGE EXAMPLES")
print("="*70)

# Initialize the system
print("\n[1] Initializing System...")
core = GuardianCore({
    "enable_resource_monitoring": False,
    "enable_runtime_health_monitoring": False,
})
print("  [OK] System initialized\n")

# ============================================================================
# EXAMPLE 1: Memory Operations
# ============================================================================
print("="*70)
print("EXAMPLE 1: Memory Operations")
print("="*70)

# Store memories
core.memory.remember("I learned about Python decorators today", category="learning")
core.memory.remember("Important meeting scheduled for tomorrow", category="tasks")
core.memory.remember("User requested system documentation", category="interactions")

# Recall recent memories
recent = core.memory.recall_last(count=5)
print(f"\nStored 3 memories, retrieved {len(recent)} recent memories:")
for i, mem in enumerate(recent[:3], 1):
    thought = mem.get('thought', mem.get('content', 'N/A'))
    print(f"  {i}. [{mem.get('category', 'N/A')}] {thought[:50]}...")

# ============================================================================
# EXAMPLE 2: System Status
# ============================================================================
print("\n" + "="*70)
print("EXAMPLE 2: System Status")
print("="*70)

status = core.get_system_status()
print("\nSystem Status:")
print(f"  - Total Memories: {status.get('memory', {}).get('total_memories', 'N/A')}")
print(f"  - Memory Categories: {len(status.get('memory', {}).get('categories', {}))}")
print(f"  - Uptime: {status.get('uptime', 'N/A')}")

# ============================================================================
# EXAMPLE 3: Startup Verification
# ============================================================================
print("\n" + "="*70)
print("EXAMPLE 3: Startup Verification")
print("="*70)

verification = core.get_startup_verification()
if verification:
    checks = verification.get("checks", [])
    successes = sum(1 for c in checks if c.get("status") == "success")
    print(f"\nStartup Verification: {successes}/{len(checks)} checks passed")
    print("\nComponent Status:")
    for check in checks[:5]:  # Show first 5
        name = check.get("component", "Unknown")
        status_icon = "[OK]" if check.get("status") == "success" else "[FAIL]"
        print(f"  {status_icon} {name}")

# ============================================================================
# EXAMPLE 4: Mutation Engine (Code Changes)
# ============================================================================
print("\n" + "="*70)
print("EXAMPLE 4: Mutation Engine")
print("="*70)

try:
    # Propose a code mutation
    mutation_id = core.mutation.propose_mutation(
        target_module="example_module.py",
        mutation_type="code_modification",
        description="Add error handling to function",
        proposed_code="def example():\n    try:\n        # code\n    except:\n        pass",
        original_code="def example():\n    # code"
    )
    print(f"\n[OK] Mutation proposed: {mutation_id}")
    
    # Get mutation status
    mutation = core.mutation.get_mutation(mutation_id)
    if mutation:
        print(f"  Status: {mutation.status.value}")
        print(f"  Target: {mutation.target_module}")
except Exception as e:
    print(f"\nNote: Mutation operations available (error: {e})")

# ============================================================================
# EXAMPLE 5: Task Management
# ============================================================================
print("\n" + "="*70)
print("EXAMPLE 5: Task Management")
print("="*70)

try:
    # Create a task
    task_id = core.tasks.create_task(
        description="Review system performance",
        priority="high",
        category="monitoring"
    )
    print(f"\n[OK] Task created: {task_id}")
    
    # Get task status
    task = core.tasks.get_task(task_id)
    if task:
        print(f"  Description: {task.description}")
        print(f"  Status: {task.status.value}")
except Exception as e:
    print(f"\nNote: Task operations available (error: {e})")

# ============================================================================
# EXAMPLE 6: Trust Management
# ============================================================================
print("\n" + "="*70)
print("EXAMPLE 6: Trust Management")
print("="*70)

try:
    # Get trust information
    trust_info = core.trust.get_trust_matrix()
    if trust_info:
        print(f"\n[OK] Trust matrix retrieved")
        print(f"  Total nodes: {len(trust_info.get('nodes', {}))}")
except Exception as e:
    print(f"\nNote: Trust operations available (error: {e})")

# ============================================================================
# EXAMPLE 7: Consensus Engine
# ============================================================================
print("\n" + "="*70)
print("EXAMPLE 7: Consensus Engine")
print("="*70)

try:
    # Get consensus status
    consensus_info = core.consensus.get_consensus_status()
    if consensus_info:
        agents = consensus_info.get('agents', {})
        print(f"\n[OK] Consensus engine active")
        print(f"  Registered agents: {len(agents)}")
        for agent_id, agent_info in list(agents.items())[:3]:
            print(f"    - {agent_id}: {agent_info.get('role', 'N/A')}")
except Exception as e:
    print(f"\nNote: Consensus operations available (error: {e})")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "="*70)
print("SUMMARY")
print("="*70)
print("\nYou can use the Elysia system for:")
print("  [OK] Memory storage and retrieval")
print("  [OK] System monitoring and status")
print("  [OK] Code mutation proposals")
print("  [OK] Task management")
print("  [OK] Trust tracking")
print("  [OK] Multi-agent consensus")
print("\nAll components are accessible via the 'core' object:")
print("  - core.memory")
print("  - core.mutation")
print("  - core.tasks")
print("  - core.trust")
print("  - core.consensus")
print("  - core.get_system_status()")
print("  - core.get_startup_verification()")

# Shutdown
print("\n" + "="*70)
print("Shutting down...")
core.shutdown()
print("System shutdown complete.")
print("="*70)


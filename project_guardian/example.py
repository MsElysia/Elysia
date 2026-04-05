# project_guardian/example.py
# Example usage of Project Guardian

from .core import GuardianCore
import time

def main():
    """
    Example demonstration of Project Guardian capabilities.
    """
    print("=== Project Guardian Demo ===\n")
    
    # Initialize Guardian Core
    guardian = GuardianCore()
    print("✅ Guardian Core initialized")
    
    # Show initial system status
    print("\n📊 Initial System Status:")
    print(guardian.get_system_summary())
    
    # Create some tasks
    print("\n📝 Creating tasks...")
    task1 = guardian.create_task(
        "demo_task_1",
        "Demonstrate task creation",
        priority=0.7,
        category="demo"
    )
    
    task2 = guardian.create_task(
        "demo_task_2", 
        "Show task management",
        priority=0.5,
        category="demo"
    )
    
    print(f"✅ Created task: {task1['name']}")
    print(f"✅ Created task: {task2['name']}")
    
    # Show task status
    active_tasks = guardian.tasks.get_active_tasks()
    print(f"\n📋 Active tasks: {len(active_tasks)}")
    for task in active_tasks:
        print(f"  - {task['name']}: {task['status']}")
    
    # Demonstrate memory system
    print("\n🧠 Testing memory system...")
    guardian.memory.remember("This is a test memory entry", category="demo", priority=0.6)
    guardian.memory.remember("Another test entry", category="demo", priority=0.8)
    
    recent_memories = guardian.memory.recall_last(3)
    print(f"✅ Recent memories: {len(recent_memories)}")
    
    # Demonstrate trust system
    print("\n🤝 Testing trust system...")
    guardian.trust.update_trust("demo_component", 0.8, "Demo component")
    trust_level = guardian.trust.get_trust("demo_component")
    print(f"✅ Trust level for demo_component: {trust_level:.2f}")
    
    # Demonstrate consensus system
    print("\n🗳️ Testing consensus system...")
    guardian.consensus.cast_vote("memory_core", "demo_action", 0.9, "Demo vote")
    guardian.consensus.cast_vote("safety_engine", "demo_action", 0.7, "Safety approval")
    
    consensus_status = guardian.consensus.get_consensus_status("demo_action")
    print(f"✅ Consensus status: {consensus_status['votes']} votes, level: {consensus_status['consensus_level']:.2f}")
    
    # Demonstrate safety system
    print("\n🛡️ Testing safety system...")
    safety_report = guardian.safety.get_safety_report()
    print(f"✅ Safety level: {safety_report['safety_level']}")
    
    # Run safety check
    print("\n🔍 Running safety check...")
    safety_results = guardian.run_safety_check()
    print(f"✅ Safety check completed: {len(safety_results['checks'])} warnings")
    
    # Show final system status
    print("\n📊 Final System Status:")
    print(guardian.get_system_summary())
    
    # Demonstrate shutdown
    print("\n🔄 Shutting down...")
    guardian.shutdown()
    print("✅ Guardian Core shutdown complete")
    
    print("\n=== Demo Complete ===")

if __name__ == "__main__":
    main() 
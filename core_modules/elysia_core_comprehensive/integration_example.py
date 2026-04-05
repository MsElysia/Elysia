#!/usr/bin/env python3
"""
Integration Example: Enhanced Elysia Core with Project Guardian Features
Demonstrates how to integrate the enhanced components with your existing system.
"""

from enhanced_memory_core import EnhancedMemoryCore
from enhanced_trust_matrix import EnhancedTrustMatrix
from enhanced_task_engine import EnhancedTaskEngine
import datetime

def main():
    """Demonstrate enhanced Elysia Core integration"""
    
    print("🛡️ Enhanced Elysia Core Integration Demo")
    print("=" * 50)
    
    # Initialize enhanced components
    print("\n1. 🧠 Enhanced Memory Core")
    print("-" * 30)
    memory = EnhancedMemoryCore("enhanced_memory.json")
    
    # Store memories with categories and priorities
    memory.remember("System initialization complete", category="system", priority=0.8)
    memory.remember("User requested task analysis", category="user", priority=0.6)
    memory.remember("Critical error detected", category="error", priority=0.9)
    memory.remember("Routine maintenance completed", category="maintenance", priority=0.4)
    
    # Demonstrate enhanced memory features
    print(f"   Total memories: {memory.get_memory_stats()['total_memories']}")
    print(f"   Categories: {memory.get_memory_stats()['categories']}")
    
    # Search memories
    error_memories = memory.search_memories("error", category="error")
    print(f"   Error memories found: {len(error_memories)}")
    
    # Get high priority memories
    high_priority = memory.get_high_priority_memories(threshold=0.7)
    print(f"   High priority memories: {len(high_priority)}")
    
    print("\n2. 🤝 Enhanced Trust Matrix")
    print("-" * 30)
    trust = EnhancedTrustMatrix("enhanced_trust.json")
    
    # Update trust with reasons
    trust.update_trust("memory_core", 0.1, "Successfully stored categorized memories", "memory_operation")
    trust.update_trust("task_engine", 0.2, "Created complex task with deadline", "task_creation")
    trust.update_trust("safety_system", -0.1, "Failed to validate critical operation", "safety_check")
    
    # Demonstrate trust features
    trust_stats = trust.get_trust_stats()
    print(f"   Average trust: {trust_stats['average_trust']:.2f}")
    print(f"   High trust components: {trust_stats['high_trust_components']}")
    print(f"   Low trust components: {trust_stats['low_trust_components']}")
    
    # Validate trust for actions
    can_mutate = trust.validate_trust_for_action("memory_core", "mutation", required_trust=0.6)
    print(f"   Memory core can mutate: {can_mutate}")
    
    # Get low trust warnings
    warnings = trust.get_low_trust_warnings(threshold=0.4)
    if warnings:
        print(f"   Low trust warnings: {warnings}")
    
    print("\n3. 📋 Enhanced Task Engine")
    print("-" * 30)
    task_engine = EnhancedTaskEngine(memory, "enhanced_tasks.json")
    
    # Create tasks with enhanced features
    task1 = task_engine.create_task(
        "Security Audit",
        "Perform comprehensive security analysis",
        priority=0.8,
        category="security",
        deadline=(datetime.datetime.now() + datetime.timedelta(hours=2)).isoformat(),
        tags=["critical", "safety"]
    )
    
    task2 = task_engine.create_task(
        "Memory Optimization",
        "Clean up old memory entries",
        priority=0.5,
        category="maintenance",
        tags=["routine"]
    )
    
    task3 = task_engine.create_task(
        "User Interface Update",
        "Update UI components",
        priority=0.6,
        category="development",
        tags=["feature"]
    )
    
    # Update task status
    task_engine.update_task_status(task1["id"], "in_progress", "Started security analysis")
    task_engine.update_task_status(task2["id"], "completed", "Memory cleanup successful")
    
    # Demonstrate task features
    task_stats = task_engine.get_task_stats()
    print(f"   Total tasks: {task_stats['total_tasks']}")
    print(f"   Active tasks: {task_stats['active_tasks']}")
    print(f"   Completed tasks: {task_stats['completed_tasks']}")
    
    # Get high priority tasks
    high_priority_tasks = task_engine.get_high_priority_tasks(threshold=0.7)
    print(f"   High priority tasks: {len(high_priority_tasks)}")
    
    # Search tasks
    security_tasks = task_engine.search_tasks("security", category="security")
    print(f"   Security tasks found: {len(security_tasks)}")
    
    print("\n4. 🔄 System Integration")
    print("-" * 30)
    
    # Demonstrate cross-component integration
    print("   Memory-Task Integration:")
    recent_memories = memory.recall_last(3, category="task")
    print(f"   Recent task memories: {len(recent_memories)}")
    
    print("   Trust-Memory Integration:")
    memory_trust = trust.get_trust("memory_core")
    print(f"   Memory core trust: {memory_trust:.2f}")
    
    print("   Task-Trust Integration:")
    if memory_trust >= 0.6:
        print("   Memory core trusted for task operations")
    else:
        print("   Memory core trust too low for task operations")
    
    print("\n5. 📊 System Statistics")
    print("-" * 30)
    
    # Comprehensive system overview
    memory_stats = memory.get_memory_stats()
    trust_stats = trust.get_trust_stats()
    task_stats = task_engine.get_task_stats()
    
    print(f"   Memory: {memory_stats['total_memories']} entries, {memory_stats['categories']} categories")
    print(f"   Trust: {trust_stats['total_components']} components, avg {trust_stats['average_trust']:.2f}")
    print(f"   Tasks: {task_stats['total_tasks']} total, {task_stats['active_tasks']} active")
    
    # System health indicators
    if memory_stats['recent_activity'] > 5:
        print("   ✅ High memory activity")
    else:
        print("   ⚠️  Low memory activity")
    
    if trust_stats['low_trust_components'] == 0:
        print("   ✅ All components trusted")
    else:
        print(f"   ⚠️  {trust_stats['low_trust_components']} low-trust components")
    
    if task_stats['overdue_tasks'] == 0:
        print("   ✅ No overdue tasks")
    else:
        print(f"   ⚠️  {task_stats['overdue_tasks']} overdue tasks")
    
    print("\n6. 🛡️ Safety Features")
    print("-" * 30)
    
    # Demonstrate safety validation
    print("   Trust-based action validation:")
    
    actions = [
        ("memory_core", "mutation", 0.6),
        ("task_engine", "deletion", 0.8),
        ("safety_system", "override", 0.9)
    ]
    
    for component, action, required_trust in actions:
        can_perform = trust.validate_trust_for_action(component, action, required_trust)
        status = "✅" if can_perform else "❌"
        print(f"   {status} {component} can {action} (requires {required_trust:.1f})")
    
    print("\n7. 🔍 Advanced Analytics")
    print("-" * 30)
    
    # Memory analytics
    print("   Memory Analytics:")
    for category, count in memory_stats['category_breakdown'].items():
        print(f"   - {category}: {count} memories")
    
    # Trust analytics
    print("   Trust Analytics:")
    high_trust = trust.get_components_by_trust_level(min_trust=0.7)
    low_trust = trust.get_components_by_trust_level(max_trust=0.3)
    print(f"   - High trust components: {high_trust}")
    print(f"   - Low trust components: {low_trust}")
    
    # Task analytics
    print("   Task Analytics:")
    for category, stats in task_stats['categories'].items():
        print(f"   - {category}: {stats['active']} active, {stats['completed']} completed")
    
    print("\n✅ Enhanced Elysia Core Integration Complete!")
    print("=" * 50)
    print("\nKey Benefits:")
    print("  • Enhanced memory with categories and priorities")
    print("  • Advanced trust management with history tracking")
    print("  • Comprehensive task management with deadlines")
    print("  • Cross-component integration and validation")
    print("  • Safety features with trust-based authorization")
    print("  • Detailed analytics and system health monitoring")

if __name__ == "__main__":
    main() 
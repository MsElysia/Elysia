#!/usr/bin/env python3
"""
Advanced Project Guardian Example
Demonstrates all integrated capabilities including creativity, external interactions, and mission management.
"""

import time
from project_guardian import GuardianCore

def main():
    """Demonstrate advanced Project Guardian capabilities."""
    
    print("🛡️ Project Guardian - Advanced Demo")
    print("=" * 50)
    
    # Initialize Guardian Core
    guardian = GuardianCore()
    
    print("\n1. 🧠 Creative Dream Cycle")
    print("-" * 30)
    dreams = guardian.begin_dream_cycle(3)
    for i, dream in enumerate(dreams, 1):
        print(f"   Dream {i}: {dream}")
    
    print("\n2. 🌐 Web Content Fetching")
    print("-" * 30)
    # Note: This would require internet access
    print("   Web reader initialized and ready")
    print("   Use guardian.fetch_web_content('https://example.com') to fetch content")
    
    print("\n3. 🗣️ Voice Synthesis")
    print("-" * 30)
    guardian.speak_message("Guardian system is online and ready to protect", "guardian")
    print("   Voice message sent (check your speakers)")
    
    print("\n4. 🤖 AI Interaction")
    print("-" * 30)
    # Note: Requires OpenAI API key
    print("   AI interaction system ready")
    print("   Use guardian.ask_ai('your question') to interact with AI")
    
    print("\n5. 🎯 Mission Management")
    print("-" * 30)
    
    # Create missions
    mission1 = guardian.create_mission(
        "System Security Audit",
        "Perform comprehensive security analysis of all components",
        priority="high"
    )
    
    mission2 = guardian.create_mission(
        "Memory Optimization",
        "Optimize memory usage and clean up old entries",
        priority="medium"
    )
    
    print(f"   Created mission: {mission1['name']}")
    print(f"   Created mission: {mission2['name']}")
    
    # Add subtasks
    guardian.missions.add_subtask("System Security Audit", "Check trust matrix integrity")
    guardian.missions.add_subtask("System Security Audit", "Validate safety protocols")
    guardian.missions.add_subtask("Memory Optimization", "Remove old error logs")
    
    # Log progress
    guardian.missions.log_progress("System Security Audit", "Trust matrix analysis complete", 0.5)
    guardian.missions.log_progress("Memory Optimization", "Started cleanup process", 0.3)
    
    print("\n6. 🔍 Context Building")
    print("-" * 30)
    
    # Get context by keyword
    context = guardian.get_context(keyword="safety")
    print(f"   Safety context: {context[:100]}...")
    
    # Get recent context
    recent_context = guardian.get_context(minutes=60)
    print(f"   Recent context: {recent_context[:100]}...")
    
    print("\n7. 📊 System Status")
    print("-" * 30)
    
    # Get comprehensive status
    status = guardian.get_system_status()
    print(f"   Uptime: {status['uptime']:.0f} seconds")
    print(f"   Memory: {status['memory']['total_memories']} entries")
    print(f"   Tasks: {status['tasks']['active_tasks']} active")
    print(f"   Trust Level: {status['trust']['average_trust']:.2f}")
    
    # Get mission stats
    mission_stats = guardian.missions.get_mission_stats()
    print(f"   Missions: {mission_stats['active_missions']} active")
    print(f"   Completion Rate: {mission_stats['completion_rate']:.1%}")
    
    # Get dream stats
    dream_stats = guardian.dreams.get_dream_stats()
    print(f"   Dreams: {dream_stats['total_dreams']} generated")
    print(f"   Dream Density: {dream_stats['dream_density']:.2f}")
    
    print("\n8. 🛡️ Safety Validation")
    print("-" * 30)
    
    # Run safety check
    safety_results = guardian.run_safety_check()
    print(f"   Safety checks: {len(safety_results['checks'])} warnings")
    
    for check in safety_results['checks']:
        print(f"   - {check['type']}: {check['message']} ({check['severity']})")
    
    print("\n9. 🔄 Task Management")
    print("-" * 30)
    
    # Create tasks
    task1 = guardian.create_task(
        "Monitor Dream Patterns",
        "Analyze creative patterns in dream cycles",
        priority=0.7,
        category="analysis"
    )
    
    task2 = guardian.create_task(
        "Update Trust Matrix",
        "Recalculate trust levels based on recent activity",
        priority=0.8,
        category="safety"
    )
    
    print(f"   Created task: {task1['name']}")
    print(f"   Created task: {task2['name']}")
    
    # Complete a task
    guardian.tasks.complete_task(task1['id'])
    
    print("\n10. 🎭 Voice Mode Switching")
    print("-" * 30)
    
    # Switch voice modes
    guardian.voice.set_mode("warm_guide")
    guardian.speak_message("I'm here to help you", "warm_guide")
    
    guardian.voice.set_mode("sharp_analyst")
    guardian.speak_message("Analysis shows optimal performance", "sharp_analyst")
    
    guardian.voice.set_mode("poetic_oracle")
    guardian.speak_message("The patterns reveal wisdom", "poetic_oracle")
    
    print("   Voice modes demonstrated")
    
    print("\n11. 📈 Advanced Analytics")
    print("-" * 30)
    
    # Get pattern analysis
    patterns = guardian.memory_search.find_patterns("safety", hours=24)
    print(f"   Safety patterns: {patterns['total_matches']} matches")
    print(f"   Average priority: {patterns['average_priority']:.2f}")
    
    # Get web reader stats
    web_stats = guardian.web_reader.get_web_stats()
    print(f"   Web fetches: {web_stats['total_fetches']}")
    print(f"   Success rate: {web_stats['fetch_success_rate']:.1%}")
    
    # Get voice stats
    voice_stats = guardian.voice.get_voice_stats()
    print(f"   Speech count: {voice_stats['speech_count']}")
    print(f"   Current mode: {voice_stats['current_mode']}")
    
    print("\n12. 🎯 Mission Completion")
    print("-" * 30)
    
    # Complete a subtask
    guardian.missions.complete_subtask("System Security Audit", "Check trust matrix integrity")
    
    # Complete a mission
    guardian.missions.complete_mission("Memory Optimization", "Cleanup completed successfully")
    
    print("   Subtask completed: Check trust matrix integrity")
    print("   Mission completed: Memory Optimization")
    
    print("\n13. 🔍 Deadline Monitoring")
    print("-" * 30)
    
    # Check for deadline issues
    deadline_issues = guardian.missions.check_deadlines()
    if deadline_issues:
        for issue in deadline_issues:
            print(f"   ⚠️  {issue['mission']}: {issue['issue']}")
    else:
        print("   ✅ No deadline issues found")
    
    print("\n14. 📋 Final Summary")
    print("-" * 30)
    
    summary = guardian.get_system_summary()
    print(summary)
    
    print("\n15. 🛡️ System Shutdown")
    print("-" * 30)
    
    # Safely shutdown
    guardian.shutdown()
    print("   System shutdown complete")
    
    print("\n✅ Advanced Project Guardian Demo Complete!")
    print("=" * 50)
    print("\nKey Features Demonstrated:")
    print("  • Creative dream cycles and inspiration")
    print("  • Web content fetching and analysis")
    print("  • Voice synthesis with personality modes")
    print("  • AI interaction capabilities")
    print("  • Mission management and tracking")
    print("  • Context building and memory search")
    print("  • Advanced safety validation")
    print("  • Comprehensive system monitoring")
    print("  • Pattern recognition and analytics")
    print("  • Deadline monitoring and alerts")

if __name__ == "__main__":
    main() 
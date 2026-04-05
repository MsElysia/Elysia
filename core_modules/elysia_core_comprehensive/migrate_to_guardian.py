#!/usr/bin/env python3
"""
Migration Script: Elysia Core to Project Guardian Integration
Automates the integration of Project Guardian's advanced features into Elysia Core.
"""

import os
import shutil
import json
import datetime
from pathlib import Path

def migrate_to_guardian():
    """Migrate existing Elysia Core to Project Guardian enhanced system"""
    
    print("🛡️ Starting Project Guardian Migration...")
    print("=" * 50)
    
    # Create backup
    create_backup()
    
    # Update components
    update_mutation_engine()
    update_api_endpoints()
    create_integration_test()
    
    print("✅ Migration completed successfully!")
    print("\n📋 Next Steps:")
    print("1. Test the enhanced system: python test_integration.py")
    print("2. Run the updated runtime: python elysia_runtime_loop.py")
    print("3. Check enhanced memory: enhanced_memory.json")
    print("4. Monitor trust levels: enhanced_trust.json")
    print("5. Review tasks: enhanced_tasks.json")

def create_backup():
    """Create backup of existing files"""
    backup_dir = "backups/pre_guardian"
    os.makedirs(backup_dir, exist_ok=True)
    
    files_to_backup = [
        "elysia_runtime_loop.py",
        "mutation_engine.py", 
        "memory_core.py",
        "trust_matrix.py",
        "task_engine.py",
        "elysia_api.py"
    ]
    
    print("📦 Creating backup...")
    for file in files_to_backup:
        if os.path.exists(file):
            backup_path = f"{backup_dir}/{file}"
            shutil.copy2(file, backup_path)
            print(f"   ✅ Backed up {file}")
        else:
            print(f"   ⚠️  {file} not found, skipping")
    
    # Create backup manifest
    manifest = {
        "backup_date": datetime.datetime.now().isoformat(),
        "backup_files": [f for f in files_to_backup if os.path.exists(f)],
        "migration_version": "1.0.0"
    }
    
    with open(f"{backup_dir}/backup_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    
    print(f"   📄 Backup manifest created: {backup_dir}/backup_manifest.json")

def update_mutation_engine():
    """Update mutation_engine.py with Project Guardian safety features"""
    print("\n🔧 Updating mutation engine with safety features...")
    
    # Read current mutation engine
    if os.path.exists("mutation_engine.py"):
        with open("mutation_engine.py", "r") as f:
            content = f.read()
        
        # Add Project Guardian safety imports
        if "from project_guardian.safety import DevilsAdvocate" not in content:
            safety_imports = """
# Project Guardian Safety Integration
try:
    from project_guardian.safety import DevilsAdvocate as GuardianDevilsAdvocate
    from project_guardian.trust import TrustMatrix as GuardianTrustMatrix
    GUARDIAN_SAFETY_AVAILABLE = True
except ImportError:
    GUARDIAN_SAFETY_AVAILABLE = False
    print("[Warning] Project Guardian safety components not available.")
"""
            # Insert after existing imports
            lines = content.split('\n')
            import_end = 0
            for i, line in enumerate(lines):
                if line.startswith('import ') or line.startswith('from '):
                    import_end = i + 1
            
            lines.insert(import_end, safety_imports)
            content = '\n'.join(lines)
        
        # Add safety validation to propose_mutation method
        if "def propose_mutation" in content and "safety_result = self.safety.review_mutation" not in content:
            safety_code = """
        # Project Guardian Safety Review
        if GUARDIAN_SAFETY_AVAILABLE:
            if not hasattr(self, 'guardian_safety'):
                self.guardian_safety = GuardianDevilsAdvocate(self.memory)
                self.guardian_trust = GuardianTrustMatrix(self.memory)
            
            # Safety review
            safety_result = self.guardian_safety.review_mutation([new_code])
            if "suspicious" in safety_result.lower():
                return f"[Mutation Blocked] Safety review failed: {safety_result}"
            
            # Trust validation
            if not self.guardian_trust.validate_trust_for_action("mutation_engine", "mutation"):
                return "[Mutation Blocked] Insufficient trust for mutation operation"
"""
            # Find the propose_mutation method and add safety code
            if "def propose_mutation" in content:
                # Simple replacement - in practice, you'd want more sophisticated parsing
                content = content.replace(
                    "def propose_mutation(self, filename, new_code):",
                    "def propose_mutation(self, filename, new_code):" + safety_code
                )
        
        # Write updated content
        with open("mutation_engine.py", "w", encoding="utf-8") as f:
            f.write(content)
        
        print("   ✅ Mutation engine updated with safety features")
    else:
        print("   ⚠️  mutation_engine.py not found, skipping")

def update_api_endpoints():
    """Update elysia_api.py with Project Guardian endpoints"""
    print("\n🌐 Updating API with Guardian endpoints...")
    
    if os.path.exists("elysia_api.py"):
        with open("elysia_api.py", "r") as f:
            content = f.read()
        
        # Add Guardian API imports
        guardian_imports = """
# Project Guardian API Integration
try:
    from project_guardian import GuardianCore
    GUARDIAN_API_AVAILABLE = True
except ImportError:
    GUARDIAN_API_AVAILABLE = False
    print("[Warning] Project Guardian API not available.")
"""
        
        # Add Guardian endpoints
        guardian_endpoints = """

# Project Guardian API Endpoints
if GUARDIAN_API_AVAILABLE:
    @app.route("/guardian/status")
    def guardian_status():
        try:
            guardian = GuardianCore()
            return jsonify(guardian.get_system_status())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/guardian/memory/search")
    def guardian_memory_search():
        keyword = request.args.get("keyword", "")
        category = request.args.get("category", "")
        try:
            guardian = GuardianCore()
            results = guardian.memory.search_memories(keyword, category)
            return jsonify(results)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/guardian/tasks/create", methods=["POST"])
    def guardian_create_task():
        try:
            data = request.json
            guardian = GuardianCore()
            task = guardian.create_task(
                data["name"],
                data["description"],
                priority=data.get("priority", 0.5),
                category=data.get("category", "general")
            )
            return jsonify(task)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/guardian/trust/update", methods=["POST"])
    def guardian_update_trust():
        try:
            data = request.json
            guardian = GuardianCore()
            new_trust = guardian.trust.update_trust(
                data["component"],
                data["delta"],
                data.get("reason", "API update")
            )
            return jsonify({"component": data["component"], "trust": new_trust})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
"""
        
        # Insert imports after existing imports
        lines = content.split('\n')
        import_end = 0
        for i, line in enumerate(lines):
            if line.startswith('import ') or line.startswith('from '):
                import_end = i + 1
        
        lines.insert(import_end, guardian_imports)
        content = '\n'.join(lines)
        
        # Add endpoints before the main block
        if "if __name__ == '__main__':" in content:
            content = content.replace(
                "if __name__ == '__main__':",
                guardian_endpoints + "\nif __name__ == '__main__':"
            )
        
        # Write updated content
        with open("elysia_api.py", "w", encoding="utf-8") as f:
            f.write(content)
        
        print("   ✅ API updated with Guardian endpoints")
    else:
        print("   ⚠️  elysia_api.py not found, skipping")

def create_integration_test():
    """Create integration test for the merged system"""
    print("\n🧪 Creating integration test...")
    
    test_content = '''#!/usr/bin/env python3
"""
Integration Test: Project Guardian + Elysia Core
Tests the merged system functionality.
"""

import sys
import os
import time

def test_enhanced_memory():
    """Test enhanced memory functionality"""
    print("🧠 Testing Enhanced Memory...")
    
    try:
        from enhanced_memory_core import EnhancedMemoryCore
        
        memory = EnhancedMemoryCore("test_memory.json")
        
        # Test basic functionality
        memory.remember("Test memory", category="test", priority=0.8)
        memory.remember("Another test", category="test", priority=0.6)
        memory.remember("System event", category="system", priority=0.9)
        
        # Test enhanced features
        stats = memory.get_memory_stats()
        assert stats["total_memories"] == 3
        assert stats["categories"] == 2
        
        # Test search
        results = memory.search_memories("test", category="test")
        assert len(results) == 2
        
        # Test high priority
        high_priority = memory.get_high_priority_memories(threshold=0.7)
        assert len(high_priority) == 2
        
        print("   ✅ Enhanced memory test passed")
        return True
        
    except Exception as e:
        print(f"   ❌ Enhanced memory test failed: {e}")
        return False

def test_enhanced_trust():
    """Test enhanced trust functionality"""
    print("🤝 Testing Enhanced Trust...")
    
    try:
        from enhanced_trust_matrix import EnhancedTrustMatrix
        
        trust = EnhancedTrustMatrix("test_trust.json")
        
        # Test basic functionality
        trust.update_trust("test_component", 0.1, "Test operation", "test")
        trust.update_trust("another_component", -0.2, "Failed operation", "test")
        
        # Test enhanced features
        stats = trust.get_trust_stats()
        assert stats["total_components"] == 2
        
        # Test validation
        can_mutate = trust.validate_trust_for_action("test_component", "mutation", 0.6)
        assert can_mutate == False  # Trust too low
        
        # Test warnings
        warnings = trust.get_low_trust_warnings(threshold=0.3)
        assert len(warnings) == 1
        
        print("   ✅ Enhanced trust test passed")
        return True
        
    except Exception as e:
        print(f"   ❌ Enhanced trust test failed: {e}")
        return False

def test_enhanced_tasks():
    """Test enhanced task functionality"""
    print("📋 Testing Enhanced Tasks...")
    
    try:
        from enhanced_task_engine import EnhancedTaskEngine
        from enhanced_memory_core import EnhancedMemoryCore
        
        memory = EnhancedMemoryCore("test_memory.json")
        task_engine = EnhancedTaskEngine(memory, "test_tasks.json")
        
        # Test basic functionality
        task1 = task_engine.create_task(
            "Test Task",
            "Test description",
            priority=0.7,
            category="test"
        )
        
        task2 = task_engine.create_task(
            "Another Task",
            "Another description",
            priority=0.5,
            category="test"
        )
        
        # Test enhanced features
        stats = task_engine.get_task_stats()
        assert stats["total_tasks"] == 2
        assert stats["active_tasks"] == 2
        
        # Test status update
        task_engine.update_task_status(task1["id"], "in_progress", "Started")
        task_engine.complete_task(task1["id"])
        
        # Test search
        test_tasks = task_engine.search_tasks("Test", category="test")
        assert len(test_tasks) == 1
        
        print("   ✅ Enhanced tasks test passed")
        return True
        
    except Exception as e:
        print(f"   ❌ Enhanced tasks test failed: {e}")
        return False

def test_runtime_integration():
    """Test runtime loop integration"""
    print("🔄 Testing Runtime Integration...")
    
    try:
        from elysia_runtime_loop import ElysiaRuntimeLoop
        
        # Initialize runtime (should use enhanced components)
        runtime = ElysiaRuntimeLoop()
        
        # Test that enhanced components are loaded
        assert hasattr(runtime, 'memory')
        assert hasattr(runtime, 'trust')
        assert hasattr(runtime, 'tasks')
        
        # Test Guardian integration if available
        if hasattr(runtime, 'guardian'):
            print("   ✅ Project Guardian integration detected")
        else:
            print("   ⚠️  Project Guardian not available, using basic components")
        
        print("   ✅ Runtime integration test passed")
        return True
        
    except Exception as e:
        print(f"   ❌ Runtime integration test failed: {e}")
        return False

def cleanup_test_files():
    """Clean up test files"""
    test_files = [
        "test_memory.json",
        "test_trust.json", 
        "test_tasks.json"
    ]
    
    for file in test_files:
        if os.path.exists(file):
            os.remove(file)
            print(f"   🧹 Cleaned up {file}")

def main():
    """Run integration tests"""
    print("🛡️ Project Guardian Integration Test")
    print("=" * 50)
    
    tests = [
        test_enhanced_memory,
        test_enhanced_trust,
        test_enhanced_tasks,
        test_runtime_integration
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    # Cleanup
    cleanup_test_files()
    
    # Results
    print("📊 Test Results:")
    print(f"   Passed: {passed}/{total}")
    print(f"   Success Rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("🎉 All tests passed! Integration successful.")
        return True
    else:
        print("⚠️  Some tests failed. Check the output above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
'''
    
    with open("test_integration.py", "w", encoding="utf-8") as f:
        f.write(test_content)
    
    print("   ✅ Integration test created: test_integration.py")

def create_requirements_update():
    """Update requirements.txt with Project Guardian dependencies"""
    print("\n📦 Updating requirements...")
    
    guardian_requirements = """
# Project Guardian Dependencies
openai>=1.0.0
flask>=2.0.0
typing-extensions>=4.0.0
requests>=2.25.0
beautifulsoup4>=4.9.0
pyttsx3>=2.90
pyyaml>=5.4.0
psutil>=5.8.0
"""
    
    if os.path.exists("requirements.txt"):
        with open("requirements.txt", "r") as f:
            content = f.read()
        
        if "Project Guardian Dependencies" not in content:
            content += guardian_requirements
        
        with open("requirements.txt", "w") as f:
            f.write(content)
        
        print("   ✅ Requirements updated")
    else:
        with open("requirements.txt", "w", encoding="utf-8") as f:
            f.write(guardian_requirements)
        print("   ✅ Requirements file created")

if __name__ == "__main__":
    migrate_to_guardian()
    create_requirements_update() 
# project_guardian/tests/test_integration.py
# Integration Tests for Elysia System
# Validates critical system integrations work together

import pytest
import asyncio
import os
import tempfile
import shutil
from pathlib import Path

# Import system components
from ..core import GuardianCore
from ..elysia_loop_core import ElysiaLoopCore, Task, TaskStatus
from ..trust_eval_action import TrustEvalAction
from ..trust_eval_content import TrustEvalContent
from ..feedback_loop import FeedbackLoopCore
from ..memory_vector import VectorMemory
from ..memory_snapshot import MemorySnapshot


class TestEventLoopIntegration:
    """Test ElysiaLoop-Core integration with modules."""
    
    def test_task_submission_and_execution(self):
        """Test that tasks can be submitted and executed."""
        loop = ElysiaLoopCore()
        results = []
        
        async def test_task(message):
            await asyncio.sleep(0.1)
            results.append(message)
            return f"Completed: {message}"
            
        # Submit task
        task_id = loop.submit_task(
            func=test_task,
            args=("test message",),
            priority=10,
            module="test"
        )
        
        assert task_id is not None
        
        # Start loop and wait
        loop.start()
        asyncio.run(asyncio.sleep(0.5))
        loop.stop()
        
        # Check result
        assert len(results) > 0
        assert "test message" in results[0]
        
    def test_module_adapter_execution(self):
        """Test module adapters execute through registry."""
        from ..adapters import MemoryAdapter
        from ..memory import MemoryCore
        
        loop = ElysiaLoopCore()
        memory = MemoryCore()
        adapter = MemoryAdapter(memory)
        
        loop.registry.register("memory", adapter)
        
        # Submit task via adapter
        async def memory_task():
            result = adapter.execute("remember", {
                "thought": "Test memory",
                "category": "test",
                "priority": 0.5
            })
            return result
            
        task_id = loop.submit_task(
            func=memory_task,
            priority=10,
            module="memory"
        )
        
        loop.start()
        asyncio.run(asyncio.sleep(0.5))
        loop.stop()
        
        # Verify memory was stored
        memories = memory.recall_last(1)
        assert len(memories) > 0
        assert "Test memory" in memories[0]["thought"]


class TestSecurityIntegration:
    """Test security systems integration."""
    
    def test_trust_eval_action_blocks_dangerous_action(self):
        """Test TrustEval-Action blocks dangerous file operations."""
        trust_eval = TrustEvalAction()
        
        # Test dangerous file write to system directory
        action = {
            "type": "file_write",
            "target": "/etc/passwd",
            "parameters": {"operation": "write", "content": "test"}
        }
        
        result = trust_eval.authorize_action(
            request_context={"user_id": "system"},
            action=action,
            dry_run=True
        )
        
        assert result["allowed"] == False
        assert result["severity_score"] >= 70
        
    def test_trust_eval_content_filters_pii(self):
        """Test TrustEvalContent redacts PII."""
        trust_eval = TrustEvalContent()
        
        content = "Contact me at user@example.com or call 555-1234"
        
        result = trust_eval.evaluate(content, user_id="test")
        
        assert result["verdict"] == "MODIFY"
        # Check for PII flag (case-insensitive)
        flags_lower = [f.lower() for f in result["flags"]]
        assert "pii" in flags_lower
        assert "[EMAIL_REDACTED]" in result["modified_content"] or "[PHONE_REDACTED]" in result["modified_content"]
        
    def test_security_system_integration(self):
        """Test security systems work together."""
        core = GuardianCore({"enable_vector_memory": False})
        
        # Test action authorization
        action = {
            "type": "admin",
            "target": "rm -rf /",
            "parameters": {}
        }
        
        result = core.authorize_action(action, user_id="test_user")
        
        # Should be blocked
        assert result["allowed"] == False
        
        # Test content filtering
        content_result = core.evaluate_content("Contact: user@example.com")
        assert content_result["was_modified"] == True


class TestMemoryIntegration:
    """Test memory system integration."""
    
    def test_enhanced_memory_with_vector(self):
        """Test EnhancedMemoryCore with vector search."""
        try:
            from ..memory_vector import EnhancedMemoryCore
            
            # Skip if FAISS not available
            import faiss
        except ImportError:
            pytest.skip("FAISS not available")
            
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = EnhancedMemoryCore(
                json_filepath=os.path.join(tmpdir, "test_memory.json"),
                enable_vector=True,
                vector_config={
                    "index_path": os.path.join(tmpdir, "index.faiss"),
                    "metadata_path": os.path.join(tmpdir, "metadata.json")
                }
            )
            
            # Store memory
            memory.remember("Python is a programming language", category="tech")
            memory.remember("Dogs are loyal pets", category="general")
            
            # Test semantic search (if OpenAI API key available)
            if os.getenv("OPENAI_API_KEY"):
                results = memory.semantic_search("programming", limit=5)
                # Should find Python-related memory
                assert len(results) > 0
                
    def test_memory_snapshot_creation_and_restore(self):
        """Test memory snapshot creation and restoration."""
        from ..memory import MemoryCore
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = MemoryCore(os.path.join(tmpdir, "test_memory.json"))
            snapshot = MemorySnapshot(snapshot_dir=os.path.join(tmpdir, "snapshots"))
            
            # Add some memories
            memory.remember("Memory 1", category="test")
            memory.remember("Memory 2", category="test")
            
            # Create snapshot
            snapshot_path = snapshot.create_snapshot(memory.dump_all())
            assert os.path.exists(snapshot_path)
            
            # Clear memory
            memory.forget()
            assert len(memory.memory_log) == 0
            
            # Restore from snapshot
            success = snapshot.restore_from_snapshot(snapshot_path, memory)
            assert success == True
            assert len(memory.memory_log) == 2


class TestFeedbackLoopIntegration:
    """Test FeedbackLoop integration."""
    
    def test_feedback_evaluation_cycle(self):
        """Test complete feedback evaluation."""
        feedback_loop = FeedbackLoopCore()
        
        output = "This is a test output with some content."
        
        result = feedback_loop.evaluate_output(
            output,
            context={"user_id": "test"}
        )
        
        assert "average_score" in result
        assert "detailed_results" in result
        assert len(result["detailed_results"]) == 4  # 4 evaluators
        assert result["average_score"] >= 1.0 and result["average_score"] <= 5.0
        
    def test_user_preference_logging(self):
        """Test user preference logging and matching."""
        feedback_loop = FeedbackLoopCore()
        
        # Log preferences
        feedback_loop.log_user_preference("user123", "tone", "casual")
        feedback_loop.log_user_preference("user123", "length", "concise")
        
        # Evaluate output that doesn't match
        result = feedback_loop.evaluate_output(
            "This is a very formal and lengthy output that does not match user preferences.",
            context={"user_id": "user123"}
        )
        
        # Should have preference evaluator in results
        pref_result = [r for r in result["detailed_results"] if "preference" in r["module"]]
        assert len(pref_result) > 0


class TestEndToEndWorkflow:
    """Test complete end-to-end workflows."""
    
    def test_task_lifecycle(self):
        """Test complete task lifecycle through system."""
        core = GuardianCore({"enable_vector_memory": False})
        
        # Submit task to loop
        async def test_workflow():
            # Simulate a task that uses memory
            core.memory.remember("Workflow test memory", category="test")
            return "Workflow completed"
            
        task_id = core.submit_task_to_loop(
            func=test_workflow,
            priority=10,
            module="unknown"
        )
        
        assert task_id is not None
        
        # Check loop status
        status = core.get_loop_status()
        assert status["queue_size"] >= 0
        
        # Give it time to execute
        import time
        time.sleep(1)
        
        # Verify memory was updated
        memories = core.memory.recall_last(1, category="test")
        assert len(memories) > 0
        
    def test_security_integration_with_tasks(self):
        """Test security systems integrated with task execution."""
        core = GuardianCore({"enable_vector_memory": False})
        
        # Try to submit a task that requires security check
        async def secure_task():
            # Task that tries to access restricted file
            action = {
                "type": "file_write",
                "target": "/etc/passwd",
                "parameters": {"operation": "write"}
            }
            
            result = core.authorize_action(action, user_id="test")
            
            if not result["allowed"]:
                return "Action properly blocked"
            else:
                return "Security failed"
                
        task_id = core.submit_task_to_loop(
            func=secure_task,
            priority=10
        )
        
        # Should complete and show action was blocked
        import time
        time.sleep(1)


class TestSystemHealth:
    """Test overall system health and status."""
    
    def test_system_status_reporting(self):
        """Test comprehensive system status."""
        core = GuardianCore({"enable_vector_memory": False})
        
        status = core.get_system_status()
        
        assert "uptime" in status
        assert "memory" in status
        assert "tasks" in status
        assert "trust" in status
        assert "safety_level" in status
        
    def test_security_status_reporting(self):
        """Test security system status."""
        core = GuardianCore({"enable_vector_memory": False})
        
        security_status = core.get_security_status()
        
        assert "recent_violations" in security_status
        assert "pending_reviews" in security_status
        assert "policy_loaded" in security_status
        
    def test_loop_status_reporting(self):
        """Test event loop status."""
        core = GuardianCore({"enable_vector_memory": False})
        
        loop_status = core.get_loop_status()
        
        assert "running" in loop_status
        assert "queue_size" in loop_status
        assert "registered_modules" in loop_status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


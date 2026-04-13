# project_guardian/tests/test_basic_functionality.py
# Basic Functionality Tests
# Validates core components work independently

import pytest
import os
import tempfile
from ..memory import MemoryCore
from ..trust import TrustMatrix
from ..feedback_loop import FeedbackLoopCore, AccuracyEvaluator, CreativityEvaluator


class TestMemoryCore:
    """Test basic MemoryCore functionality."""
    
    def test_memory_storage_and_recall(self):
        """Test storing and recalling memories."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name
        
        try:
            memory = MemoryCore(temp_path)
            
            memory.remember("Test memory", category="test", priority=0.8)
            memories = memory.recall_last(1)
            
            assert len(memories) == 1
            assert memories[0]["thought"] == "Test memory"
        finally:
            # Close memory before deleting file (Windows requirement)
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except PermissionError:
                    # File might still be locked, skip deletion on Windows
                    pass
            
    def test_memory_search(self):
        """Test memory keyword search."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name
        
        try:
            memory = MemoryCore(temp_path)
            
            memory.remember("Python programming", category="tech")
            memory.remember("Dog training", category="pets")
            
            results = memory.search_memories("Python")
            assert len(results) > 0
            assert "Python" in results[0]["thought"]
        finally:
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except PermissionError:
                    pass


class TestTrustMatrix:
    """Test TrustMatrix functionality."""
    
    def test_trust_updates(self):
        """Test trust level updates."""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        # Update trust (delta is added to current, default is 0.5)
        trust.update_trust("component1", 0.3, "Good performance")
        # 0.5 (default) + 0.3 = 0.8 (clamped to 1.0)
        assert trust.get_trust("component1") >= 0.7  # Should be around 0.8
        
        initial_trust = trust.get_trust("component1")
        trust.update_trust("component1", 0.2, "Great performance")
        # Should add to existing trust
        assert trust.get_trust("component1") > initial_trust
        
    def test_trust_decay(self):
        """Test trust decay mechanism."""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        # Set high trust
        trust.update_trust("component1", 0.5, "Initial trust")  # 0.5 + 0.5 = 1.0
        initial_trust = trust.get_trust("component1")
        assert initial_trust >= 0.9  # Should be near 1.0
        
        trust.decay_all(0.1)
        # Decay should reduce trust
        decayed_trust = trust.get_trust("component1")
        assert decayed_trust < initial_trust


class TestFeedbackEvaluators:
    """Test individual feedback evaluators."""
    
    def test_accuracy_evaluator(self):
        """Test AccuracyEvaluator."""
        evaluator = AccuracyEvaluator()
        
        # Test vague output
        vague_output = "Some people say that things are generally good."
        score, advice = evaluator.evaluate(vague_output)
        
        assert 1 <= score <= 5
        assert isinstance(advice, str)
        
    def test_creativity_evaluator(self):
        """Test CreativityEvaluator."""
        evaluator = CreativityEvaluator()
        
        # Test generic output
        generic_output = "It is important to note that this is a test."
        score, advice = evaluator.evaluate(generic_output)
        
        assert 1 <= score <= 5
        assert isinstance(advice, str)
        
    def test_feedback_loop_evaluation(self):
        """Test complete feedback loop evaluation."""
        feedback_loop = FeedbackLoopCore()
        
        output = "This is a well-written, creative piece of content."
        result = feedback_loop.evaluate_output(output)
        
        assert "average_score" in result
        assert "detailed_results" in result
        assert len(result["detailed_results"]) == 4


class TestTrustEvalAction:
    """Test TrustEval-Action basic functionality."""
    
    def test_policy_loading(self):
        """Test policy loading."""
        from ..trust_policy_manager import TrustPolicyManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            policy = TrustPolicyManager(
                config_path=os.path.join(tmpdir, "test_policy.yaml")
            )
            
            assert policy.current_policy is not None
            assert "network" in policy.current_policy
            
    def test_action_authorization(self):
        """Test basic action authorization."""
        from ..trust_eval_action import TrustEvalAction
        trust_eval = TrustEvalAction()
        
        # Test safe action
        safe_action = {
            "type": "file_read",
            "target": "/tmp/test.txt",
            "parameters": {"operation": "read"}
        }
        
        result = trust_eval.authorize_action(
            request_context={"user_id": "system"},
            action=safe_action,
            dry_run=True
        )
        
        assert "verdict" in result
        assert "allowed" in result
        assert "severity_score" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


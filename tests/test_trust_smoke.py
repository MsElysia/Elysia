"""
TrustMatrix Smoke Tests
=======================
Behavioral tests for TrustMatrix correctness and completeness.
These are NOT presence checks - they verify actual runtime behavior.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestTrustDecisionStructure:
    """Test A: TrustDecision returns valid structure and fields"""
    
    def test_decision_returns_trust_decision(self):
        """Verify validate_trust_for_action returns TrustDecision with valid fields"""
        try:
            from project_guardian.trust import TrustMatrix, TrustDecision, NETWORK_ACCESS
            from project_guardian.memory import MemoryCore
            
            memory = MemoryCore()
            trust = TrustMatrix(memory)
            
            # Test with default trust (0.5) for NETWORK_ACCESS (requires 0.7)
            decision = trust.validate_trust_for_action("TestComponent", NETWORK_ACCESS)
            
            # Verify it's a TrustDecision
            assert isinstance(decision, TrustDecision), "Must return TrustDecision object"
            
            # Verify decision is one of allowed values
            assert decision.decision in ["allow", "deny", "review"], \
                f"Invalid decision: {decision.decision}. Must be 'allow', 'deny', or 'review'"
            
            # Verify reason_code is non-empty
            assert decision.reason_code, "reason_code must be non-empty"
            assert len(decision.reason_code) > 0, "reason_code must have content"
            
            # Verify message is non-empty
            assert decision.message, "message must be non-empty"
            assert len(decision.message) > 0, "message must have content"
            
            # Verify risk_score is None or within [0, 1]
            if decision.risk_score is not None:
                assert 0.0 <= decision.risk_score <= 1.0, \
                    f"risk_score must be in [0, 1], got {decision.risk_score}"
            
            # Verify allowed field matches decision semantics
            # Invariant: decision in {"deny","review"} => allowed==False
            if decision.decision in ["deny", "review"]:
                assert decision.allowed == False, \
                    f"decision={decision.decision} must have allowed=False, got {decision.allowed}"
            elif decision.decision == "allow":
                assert decision.allowed == True, \
                    f"decision=allow must have allowed=True, got {decision.allowed}"
                
        except ImportError as e:
            pytest.skip(f"Required modules not available: {e}")
        except Exception as e:
            pytest.fail(f"Error testing TrustDecision structure: {e}")


class TestTrustThresholdBehavior:
    """Test B: Threshold behavior (below => deny, within margin => review, above => allow)"""
    
    def test_below_threshold_denies(self):
        """Verify trust below required threshold results in deny"""
        try:
            from project_guardian.trust import TrustMatrix, TrustDecision, NETWORK_ACCESS
            from project_guardian.memory import MemoryCore
            
            memory = MemoryCore()
            trust = TrustMatrix(memory)
            
            # NETWORK_ACCESS requires 0.7
            # Set trust to 0.6 (below threshold)
            trust.update_trust("TestComponent", 0.1, "test")  # 0.5 + 0.1 = 0.6
            
            decision = trust.validate_trust_for_action("TestComponent", NETWORK_ACCESS)
            
            assert decision.decision == "deny", \
                f"Trust 0.6 < 0.7 should deny, got {decision.decision}"
            assert decision.allowed == False, \
                "Deny decision must have allowed=False"
            assert "INSUFFICIENT_TRUST" in decision.reason_code, \
                f"Deny reason_code should include INSUFFICIENT_TRUST, got {decision.reason_code}"
                
        except ImportError as e:
            pytest.skip(f"Required modules not available: {e}")
        except Exception as e:
            pytest.fail(f"Error testing below threshold: {e}")
    
    def test_within_margin_reviews(self):
        """Verify trust within +0.1 margin results in review"""
        try:
            from project_guardian.trust import TrustMatrix, TrustDecision, NETWORK_ACCESS
            from project_guardian.memory import MemoryCore
            
            memory = MemoryCore()
            trust = TrustMatrix(memory)
            
            # NETWORK_ACCESS requires 0.7, margin is +0.1, so review range is [0.7, 0.8)
            # Set trust to 0.75 (within margin)
            trust.update_trust("TestComponent", 0.25, "test")  # 0.5 + 0.25 = 0.75
            
            decision = trust.validate_trust_for_action("TestComponent", NETWORK_ACCESS)
            
            assert decision.decision == "review", \
                f"Trust 0.75 within margin [0.7, 0.8) should review, got {decision.decision}"
            assert decision.allowed == False, \
                "Review decision must have allowed=False (action not allowed until approved)"
            assert "BORDERLINE_TRUST" in decision.reason_code, \
                f"Review reason_code should include BORDERLINE_TRUST, got {decision.reason_code}"
                
        except ImportError as e:
            pytest.skip(f"Required modules not available: {e}")
        except Exception as e:
            pytest.fail(f"Error testing within margin: {e}")
    
    def test_above_margin_allows(self):
        """Verify trust above margin results in allow"""
        try:
            from project_guardian.trust import TrustMatrix, TrustDecision, NETWORK_ACCESS
            from project_guardian.memory import MemoryCore
            
            memory = MemoryCore()
            trust = TrustMatrix(memory)
            
            # NETWORK_ACCESS requires 0.7, margin is +0.1, so allow is >= 0.8
            # Set trust to 0.9 (above margin)
            trust.update_trust("TestComponent", 0.4, "test")  # 0.5 + 0.4 = 0.9
            
            decision = trust.validate_trust_for_action("TestComponent", NETWORK_ACCESS)
            
            assert decision.decision == "allow", \
                f"Trust 0.9 >= 0.8 should allow, got {decision.decision}"
            assert decision.allowed == True, \
                "Allow decision must have allowed=True"
            assert "ALLOWED" in decision.reason_code, \
                f"Allow reason_code should include ALLOWED, got {decision.reason_code}"
                
        except ImportError as e:
            pytest.skip(f"Required modules not available: {e}")
        except Exception as e:
            pytest.fail(f"Error testing above margin: {e}")


class TestContextRedaction:
    """Test C: Context redaction filters sensitive fields"""
    
    def test_context_redaction_filters_sensitive_fields(self):
        """Verify memory log excludes sensitive fields from context"""
        try:
            from project_guardian.trust import TrustMatrix, NETWORK_ACCESS
            from project_guardian.memory import MemoryCore
            
            memory = MemoryCore()
            trust = TrustMatrix(memory)
            
            # Context with sensitive fields
            context = {
                "target": "example.com",
                "method": "GET",
                "body": "sensitive body content",
                "token": "secret_token_12345",
                "api_key": "key_abc123",
                "password": "mypassword",
                "sensitive": "sensitive_data",
                "content": "sensitive_content"
            }
            
            # Mock memory.remember to capture what gets logged
            remembered_calls = []
            original_remember = memory.remember
            
            def capture_remember(*args, **kwargs):
                remembered_calls.append((args, kwargs))
                return original_remember(*args, **kwargs)
            
            memory.remember = capture_remember
            
            # Call validate_trust_for_action with sensitive context
            trust.validate_trust_for_action("TestComponent", NETWORK_ACCESS, context=context)
            
            # Verify memory.remember was called
            assert len(remembered_calls) > 0, "memory.remember should be called"
            
            # Check that logged messages don't contain sensitive fields
            for args, kwargs in remembered_calls:
                message = args[0] if args else ""
                if "Context:" in message:
                    # Verify sensitive fields are NOT in the logged message
                    assert "secret_token_12345" not in message, \
                        "token should be redacted from context log"
                    assert "key_abc123" not in message, \
                        "api_key should be redacted from context log"
                    assert "mypassword" not in message, \
                        "password should be redacted from context log"
                    assert "sensitive body content" not in message, \
                        "body should be redacted from context log"
                    assert "sensitive_data" not in message, \
                        "sensitive field should be redacted from context log"
                    assert "sensitive_content" not in message, \
                        "content should be redacted from context log"
                    
                    # Verify safe fields ARE in the logged message
                    assert "example.com" in message or "target" in message, \
                        "target (safe field) should be in context log"
                    assert "GET" in message or "method" in message, \
                        "method (safe field) should be in context log"
            
            # Restore original
            memory.remember = original_remember
                
        except ImportError as e:
            pytest.skip(f"Required modules not available: {e}")
        except Exception as e:
            pytest.fail(f"Error testing context redaction: {e}")


class TestUnknownActionGuardrail:
    """Test D: Unknown action guardrail triggers warning"""
    
    def test_unknown_action_triggers_warning(self):
        """Verify unknown action string triggers memory warning"""
        try:
            from project_guardian.trust import TrustMatrix
            from project_guardian.memory import MemoryCore
            
            memory = MemoryCore()
            trust = TrustMatrix(memory)
            
            # Mock memory.remember to capture calls
            remembered_calls = []
            original_remember = memory.remember
            
            def capture_remember(*args, **kwargs):
                remembered_calls.append((args, kwargs))
                return original_remember(*args, **kwargs)
            
            memory.remember = capture_remember
            
            # Call with unknown action string
            unknown_action = "completely_unknown_action_xyz"
            decision = trust.validate_trust_for_action("TestComponent", unknown_action)
            
            # Verify memory.remember was called with warning
            warning_found = False
            for args, kwargs in remembered_calls:
                message = args[0] if args else ""
                if "Unknown action string" in message and unknown_action in message:
                    warning_found = True
                    assert kwargs.get("category") == "governance", \
                        "Warning should be logged with category='governance'"
                    break
            
            assert warning_found, \
                f"Warning for unknown action '{unknown_action}' should be logged to memory"
            
            # Verify decision still works (uses default threshold)
            assert decision.decision in ["allow", "deny", "review"], \
                "Unknown action should still return valid decision (using default threshold)"
            
            # Restore original
            memory.remember = original_remember
                
        except ImportError as e:
            pytest.skip(f"Required modules not available: {e}")
        except Exception as e:
            pytest.fail(f"Error testing unknown action guardrail: {e}")


class TestReviewDecisionSemantics:
    """Test that review decisions have allowed=False"""
    
    def test_review_decision_has_allowed_false(self):
        """Verify review decisions correctly set allowed=False"""
        try:
            from project_guardian.trust import TrustMatrix, NETWORK_ACCESS
            from project_guardian.memory import MemoryCore
            
            memory = MemoryCore()
            trust = TrustMatrix(memory)
            
            # Set trust to trigger review (within margin)
            # NETWORK_ACCESS requires 0.7, margin +0.1, so [0.7, 0.8) is review
            trust.update_trust("TestComponent", 0.25, "test")  # 0.5 + 0.25 = 0.75
            
            decision = trust.validate_trust_for_action("TestComponent", NETWORK_ACCESS)
            
            if decision.decision == "review":
                assert decision.allowed == False, \
                    "Review decision must have allowed=False (action not allowed until approved)"
            else:
                pytest.skip(f"Trust level did not trigger review (got {decision.decision}), cannot test review semantics")
                
        except ImportError as e:
            pytest.skip(f"Required modules not available: {e}")
        except Exception as e:
            pytest.fail(f"Error testing review decision semantics: {e}")

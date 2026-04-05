"""
Trust & Consultation System
============================
Extracted from: MN Adversarial AI Self-Improvement conversation

Core components:
- Mediator as trust anchor (stabilized at 81.78% post-tuning)
- Dynamic trust weighting (adapts to past accuracy)
- DA & Skepticism balance (capped at 30% critique rate, -5 max penalty)
- Consultation scaling (+10/+4 if mediator-aligned)
- Trust buffer (past 5-round average preserves context)
- Emergency override (crisis mode scales with past accuracy)
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
import statistics


@dataclass
class TrustMetrics:
    """Trust metrics for a single round"""
    round_number: int
    trust_level: float
    mediator_aligned: bool
    confidence: float
    da_critique_rate: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ConsultationDecision:
    """Represents a consultation decision"""
    action: str  # "act", "consult", "delay"
    confidence: float
    trust_level: float
    mediator_alignment: bool
    reasoning: str
    timestamp: datetime = field(default_factory=datetime.now)


class TrustBuffer:
    """Maintains a rolling buffer of past trust metrics"""
    
    def __init__(self, buffer_size: int = 5):
        self.buffer_size = buffer_size
        self.metrics: deque = deque(maxlen=buffer_size)
    
    def add_metric(self, metric: TrustMetrics):
        """Add a new trust metric to the buffer"""
        self.metrics.append(metric)
    
    def get_average_trust(self) -> float:
        """Get average trust from buffer"""
        if not self.metrics:
            return 0.75  # Default trust
        return statistics.mean([m.trust_level for m in self.metrics])
    
    def get_recent_trend(self) -> str:
        """Get trend: 'increasing', 'decreasing', 'stable'"""
        if len(self.metrics) < 2:
            return "stable"
        
        recent = [m.trust_level for m in self.metrics]
        if recent[-1] > recent[0]:
            return "increasing"
        elif recent[-1] < recent[0]:
            return "decreasing"
        return "stable"


class TrustConsultationSystem:
    """
    Trust & Consultation System for Elysia
    
    Features:
    - Mediator as trust anchor (81.78% post-tuning)
    - Dynamic trust weighting based on past accuracy
    - DA & Skepticism balance (30% critique rate, -5 max penalty)
    - Consultation scaling (+10/+4 if mediator-aligned)
    - Trust buffer (past 5-round average)
    - Emergency override (crisis mode)
    """
    
    def __init__(
        self,
        initial_trust: float = 0.8178,  # 81.78% post-tuning
        mediator_trust_anchor: float = 0.8178,
        max_da_critique_rate: float = 0.30,  # 30% max
        max_da_penalty: float = -5.0,
        consultation_scaling_aligned: Tuple[float, float] = (10.0, 4.0),
        buffer_size: int = 5
    ):
        self.current_trust = initial_trust
        self.mediator_trust_anchor = mediator_trust_anchor
        self.max_da_critique_rate = max_da_critique_rate
        self.max_da_penalty = max_da_penalty
        self.consultation_scaling_aligned = consultation_scaling_aligned
        self.trust_buffer = TrustBuffer(buffer_size)
        self.past_accuracy_history: List[float] = []
        self.consultation_history: List[ConsultationDecision] = []
    
    def calculate_dynamic_trust_weighting(self) -> float:
        """
        Calculate dynamic trust weighting based on past accuracy
        
        Returns a multiplier for trust adjustments
        """
        if not self.past_accuracy_history:
            return 1.0
        
        # Use recent accuracy (last 10 decisions)
        recent_accuracy = self.past_accuracy_history[-10:] if len(self.past_accuracy_history) >= 10 else self.past_accuracy_history
        avg_accuracy = statistics.mean(recent_accuracy) if recent_accuracy else 0.75
        
        # Higher accuracy = higher trust weighting
        # Scale between 0.8 and 1.2 based on accuracy
        weighting = 0.8 + (avg_accuracy - 0.5) * 0.8
        return max(0.8, min(1.2, weighting))
    
    def apply_da_skepticism_balance(self, da_critique_rate: float) -> float:
        """
        Apply DA & Skepticism balance
        
        Args:
            da_critique_rate: Current DA critique rate (0.0 to 1.0)
        
        Returns:
            Adjusted trust penalty
        """
        # Cap critique rate at 30%
        capped_rate = min(da_critique_rate, self.max_da_critique_rate)
        
        # Calculate penalty (max -5)
        penalty = -capped_rate * (self.max_da_penalty / self.max_da_critique_rate)
        
        return penalty
    
    def calculate_consultation_scaling(self, mediator_aligned: bool) -> Tuple[float, float]:
        """
        Calculate consultation scaling based on mediator alignment
        
        Returns:
            Tuple of (positive_scaling, negative_scaling)
        """
        if mediator_aligned:
            return self.consultation_scaling_aligned
        else:
            # Default scaling when not aligned
            return (5.0, 2.0)
    
    def make_consultation_decision(
        self,
        confidence: float,
        context: Dict,
        mediator_input: Optional[Dict] = None
    ) -> ConsultationDecision:
        """
        Make a consultation decision based on confidence and trust
        
        Decision thresholds:
        - ≥80% confidence: act
        - 40-79% confidence: consult
        - <40% confidence: delay and verify
        
        Args:
            confidence: Confidence level (0.0 to 1.0)
            context: Context information
            mediator_input: Optional mediator input
        
        Returns:
            ConsultationDecision
        """
        # Get dynamic trust weighting
        trust_weighting = self.calculate_dynamic_trust_weighting()
        weighted_trust = self.current_trust * trust_weighting
        
        # Determine mediator alignment
        mediator_aligned = False
        if mediator_input:
            # Check if mediator input aligns with current decision
            mediator_aligned = self._check_mediator_alignment(mediator_input, context)
        
        # Apply consultation scaling if mediator aligned
        pos_scale, neg_scale = self.calculate_consultation_scaling(mediator_aligned)
        
        # Decision logic
        if confidence >= 0.80:
            action = "act"
            reasoning = f"High confidence ({confidence:.1%}) - proceeding with action"
        elif confidence >= 0.40:
            action = "consult"
            reasoning = f"Medium confidence ({confidence:.1%}) - consulting mediator"
        else:
            action = "delay"
            reasoning = f"Low confidence ({confidence:.1%}) - delaying and verifying"
        
        # Create decision
        decision = ConsultationDecision(
            action=action,
            confidence=confidence,
            trust_level=weighted_trust,
            mediator_alignment=mediator_aligned,
            reasoning=reasoning
        )
        
        # Record in history
        self.consultation_history.append(decision)
        
        # Update trust buffer
        metric = TrustMetrics(
            round_number=len(self.consultation_history),
            trust_level=self.current_trust,
            mediator_aligned=mediator_aligned,
            confidence=confidence,
            da_critique_rate=0.0  # Would be calculated from actual DA interactions
        )
        self.trust_buffer.add_metric(metric)
        
        return decision
    
    def _check_mediator_alignment(self, mediator_input: Dict, context: Dict) -> bool:
        """Check if mediator input aligns with current context"""
        # Simplified alignment check
        # In practice, this would compare mediator recommendations with current decision
        return mediator_input.get("aligned", False)
    
    def apply_trust_adjustment(
        self,
        outcome: str,  # "success", "failure", "partial"
        mediator_aligned: bool
    ):
        """
        Apply trust adjustment based on outcome
        
        Args:
            outcome: Outcome of the action
            mediator_aligned: Whether mediator was aligned
        """
        # Get scaling factors
        pos_scale, neg_scale = self.calculate_consultation_scaling(mediator_aligned)
        
        # Calculate adjustment
        if outcome == "success":
            adjustment = pos_scale / 100.0  # Convert to percentage
            self.past_accuracy_history.append(1.0)
        elif outcome == "failure":
            adjustment = -neg_scale / 100.0
            self.past_accuracy_history.append(0.0)
        else:  # partial
            adjustment = (pos_scale - neg_scale) / 200.0
            self.past_accuracy_history.append(0.5)
        
        # Apply dynamic weighting
        trust_weighting = self.calculate_dynamic_trust_weighting()
        adjustment *= trust_weighting
        
        # Update trust (bound between 0.3 and 0.95)
        self.current_trust = max(0.30, min(0.95, self.current_trust + adjustment))
    
    def emergency_override(self, crisis_level: float) -> bool:
        """
        Emergency override for crisis mode
        
        Args:
            crisis_level: Crisis level (0.0 to 1.0)
        
        Returns:
            Whether override should be activated
        """
        # Scale with past accuracy
        avg_accuracy = statistics.mean(self.past_accuracy_history[-10:]) if self.past_accuracy_history else 0.75
        accuracy_factor = avg_accuracy
        
        # Higher accuracy = lower threshold for override
        threshold = 0.7 - (accuracy_factor * 0.2)
        
        return crisis_level >= threshold
    
    def get_trust_status(self) -> Dict:
        """Get current trust status"""
        return {
            "current_trust": self.current_trust,
            "mediator_anchor": self.mediator_trust_anchor,
            "buffer_average": self.trust_buffer.get_average_trust(),
            "buffer_trend": self.trust_buffer.get_recent_trend(),
            "dynamic_weighting": self.calculate_dynamic_trust_weighting(),
            "past_accuracy": statistics.mean(self.past_accuracy_history[-10:]) if self.past_accuracy_history else None,
            "total_consultations": len(self.consultation_history)
        }


if __name__ == "__main__":
    # Example usage
    print("Testing Trust & Consultation System...")
    
    system = TrustConsultationSystem()
    
    # Simulate some decisions
    for i in range(10):
        confidence = 0.5 + (i * 0.05)
        decision = system.make_consultation_decision(
            confidence=confidence,
            context={"task": f"task_{i}"},
            mediator_input={"aligned": i % 2 == 0}
        )
        
        print(f"Decision {i+1}: {decision.action} (confidence: {confidence:.1%}, trust: {decision.trust_level:.2%})")
        
        # Simulate outcome
        outcome = "success" if i % 3 != 0 else "failure"
        system.apply_trust_adjustment(outcome, decision.mediator_alignment)
    
    # Get status
    status = system.get_trust_status()
    print(f"\nTrust Status:")
    print(f"  Current Trust: {status['current_trust']:.2%}")
    print(f"  Buffer Average: {status['buffer_average']:.2%}")
    print(f"  Trend: {status['buffer_trend']}")
    print(f"  Dynamic Weighting: {status['dynamic_weighting']:.2f}")

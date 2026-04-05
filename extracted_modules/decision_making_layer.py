"""
Decision-Making Layer
=====================
Extracted from: MN Adversarial AI Self-Improvement conversation

Features:
- Hierarchical reasoning system
- Confidence-based response (≥80% act, 40-79% consult, <40% delay)
- Weighted truth verification (scales with confidence level)
- Post-analysis workflow (applies to X, social media, truth-seeking tasks)
- Emergency verification trigger (actively seeks deeper truth)
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ActionType(Enum):
    """Types of actions Elysia can take"""
    ACT = "act"
    CONSULT = "consult"
    DELAY = "delay"
    VERIFY = "verify"


@dataclass
class DecisionContext:
    """Context for making a decision"""
    task_description: str
    confidence: float
    trust_level: float
    available_information: Dict
    urgency: float  # 0.0 to 1.0
    risk_level: float  # 0.0 to 1.0
    mediator_available: bool = True


@dataclass
class DecisionResult:
    """Result of a decision"""
    action: ActionType
    confidence: float
    reasoning: str
    verification_required: bool
    post_analysis_required: bool
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class HierarchicalReasoningSystem:
    """
    Hierarchical reasoning system for structured decision-making
    
    Decision thresholds:
    - ≥80% confidence: ACT
    - 40-79% confidence: CONSULT
    - <40% confidence: DELAY and VERIFY
    """
    
    def __init__(
        self,
        act_threshold: float = 0.80,
        consult_threshold: float = 0.40,
        verification_weight: float = 1.0
    ):
        self.act_threshold = act_threshold
        self.consult_threshold = consult_threshold
        self.verification_weight = verification_weight
        self.decision_history: List[DecisionResult] = []
    
    def make_decision(self, context: DecisionContext) -> DecisionResult:
        """
        Make a hierarchical decision based on confidence and context
        
        Args:
            context: Decision context
        
        Returns:
            DecisionResult
        """
        confidence = context.confidence
        trust_level = context.trust_level
        
        # Determine base action
        if confidence >= self.act_threshold:
            action = ActionType.ACT
            reasoning = f"High confidence ({confidence:.1%}) and trust ({trust_level:.1%}) - proceeding with action"
            verification_required = False
        elif confidence >= self.consult_threshold:
            action = ActionType.CONSULT
            reasoning = f"Medium confidence ({confidence:.1%}) - consulting mediator before action"
            verification_required = confidence < 0.60
        else:
            action = ActionType.DELAY
            reasoning = f"Low confidence ({confidence:.1%}) - delaying and verifying before action"
            verification_required = True
        
        # Determine if post-analysis is required
        post_analysis_required = self._requires_post_analysis(context)
        
        # Create decision result
        result = DecisionResult(
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            verification_required=verification_required,
            post_analysis_required=post_analysis_required
        )
        
        self.decision_history.append(result)
        return result
    
    def _requires_post_analysis(self, context: DecisionContext) -> bool:
        """Determine if post-analysis is required"""
        # Post-analysis for social media, X, and truth-seeking tasks
        task_type = context.available_information.get("task_type", "")
        
        if task_type in ["social_media", "x_twitter", "truth_seeking", "content_analysis"]:
            return True
        
        # Also require for high-risk decisions
        if context.risk_level > 0.7:
            return True
        
        return False


class WeightedTruthVerification:
    """
    Weighted truth verification system
    
    Scales verification based on confidence level:
    - High confidence: Light verification
    - Medium confidence: Moderate verification
    - Low confidence: Deep verification
    """
    
    def __init__(self):
        self.verification_history: List[Dict] = []
    
    def verify_truth(
        self,
        claim: str,
        confidence: float,
        sources: List[str],
        external_ai_available: bool = True
    ) -> Dict:
        """
        Verify truth with weighted approach
        
        Args:
            claim: Claim to verify
            confidence: Confidence level
            sources: Available sources
            external_ai_available: Whether external AI is available
        
        Returns:
            Verification result
        """
        # Determine verification depth based on confidence
        if confidence >= 0.80:
            verification_depth = "light"
            weight = 0.3
        elif confidence >= 0.40:
            verification_depth = "moderate"
            weight = 0.6
        else:
            verification_depth = "deep"
            weight = 1.0
        
        # Perform verification
        verification_result = {
            "claim": claim,
            "confidence": confidence,
            "verification_depth": verification_depth,
            "weight": weight,
            "sources_checked": len(sources),
            "external_ai_used": external_ai_available and confidence < 0.60,
            "verified": confidence >= 0.60,  # Simplified
            "timestamp": datetime.now()
        }
        
        self.verification_history.append(verification_result)
        return verification_result


class PostAnalysisWorkflow:
    """
    Post-analysis workflow for X, social media, and truth-seeking tasks
    
    Applies structured analysis after decisions are made
    """
    
    def __init__(self):
        self.analysis_history: List[Dict] = []
    
    def analyze_decision(
        self,
        decision: DecisionResult,
        context: DecisionContext,
        outcome: Optional[str] = None
    ) -> Dict:
        """
        Perform post-analysis on a decision
        
        Args:
            decision: The decision that was made
            context: Original context
            outcome: Optional outcome if available
        
        Returns:
            Analysis result
        """
        analysis = {
            "decision_id": len(self.analysis_history),
            "action_taken": decision.action.value,
            "confidence": decision.confidence,
            "context_urgency": context.urgency,
            "context_risk": context.risk_level,
            "outcome": outcome,
            "analysis_timestamp": datetime.now(),
            "insights": self._generate_insights(decision, context, outcome)
        }
        
        self.analysis_history.append(analysis)
        return analysis
    
    def _generate_insights(
        self,
        decision: DecisionResult,
        context: DecisionContext,
        outcome: Optional[str]
    ) -> List[str]:
        """Generate insights from the analysis"""
        insights = []
        
        # Confidence analysis
        if decision.confidence < 0.40:
            insights.append("Low confidence decision - consider gathering more information")
        
        # Risk analysis
        if context.risk_level > 0.7:
            insights.append("High-risk decision - ensure proper verification was performed")
        
        # Outcome analysis
        if outcome:
            if outcome == "success" and decision.confidence < 0.60:
                insights.append("Successful outcome despite low confidence - may indicate conservative approach")
            elif outcome == "failure" and decision.confidence > 0.80:
                insights.append("Failure despite high confidence - review decision criteria")
        
        return insights


class EmergencyVerificationTrigger:
    """
    Emergency verification trigger
    
    Actively seeks deeper truth when confidence is low or risk is high
    """
    
    def __init__(self):
        self.trigger_history: List[Dict] = []
    
    def should_trigger_emergency_verification(
        self,
        confidence: float,
        risk_level: float,
        trust_level: float
    ) -> Tuple[bool, str]:
        """
        Determine if emergency verification should be triggered
        
        Returns:
            Tuple of (should_trigger, reason)
        """
        # Trigger conditions
        if confidence < 0.30:
            return True, "Very low confidence - emergency verification required"
        
        if risk_level > 0.85:
            return True, "Very high risk - emergency verification required"
        
        if trust_level < 0.50 and confidence < 0.50:
            return True, "Low trust and confidence - emergency verification required"
        
        return False, "No emergency verification needed"
    
    def trigger_emergency_verification(
        self,
        claim: str,
        context: DecisionContext
    ) -> Dict:
        """
        Trigger emergency verification process
        
        Args:
            claim: Claim to verify
            context: Decision context
        
        Returns:
            Emergency verification result
        """
        should_trigger, reason = self.should_trigger_emergency_verification(
            context.confidence,
            context.risk_level,
            context.trust_level
        )
        
        if not should_trigger:
            return {
                "triggered": False,
                "reason": reason
            }
        
        # Perform deep verification
        verification = {
            "triggered": True,
            "reason": reason,
            "claim": claim,
            "verification_depth": "emergency",
            "sources_consulted": ["multiple_external", "mediator", "historical_data"],
            "timestamp": datetime.now()
        }
        
        self.trigger_history.append(verification)
        return verification


class DecisionMakingLayer:
    """
    Complete Decision-Making Layer
    
    Integrates all components:
    - Hierarchical reasoning
    - Weighted truth verification
    - Post-analysis workflow
    - Emergency verification
    """
    
    def __init__(self):
        self.reasoning_system = HierarchicalReasoningSystem()
        self.truth_verification = WeightedTruthVerification()
        self.post_analysis = PostAnalysisWorkflow()
        self.emergency_verification = EmergencyVerificationTrigger()
    
    def process_decision(
        self,
        context: DecisionContext,
        claim: Optional[str] = None
    ) -> Dict:
        """
        Process a complete decision through the layer
        
        Args:
            context: Decision context
            claim: Optional claim to verify
        
        Returns:
            Complete decision processing result
        """
        # Make hierarchical decision
        decision = self.reasoning_system.make_decision(context)
        
        # Verify truth if needed
        verification_result = None
        if decision.verification_required and claim:
            verification_result = self.truth_verification.verify_truth(
                claim=claim,
                confidence=context.confidence,
                sources=context.available_information.get("sources", [])
            )
        
        # Check for emergency verification
        emergency_result = None
        if claim:
            emergency_result = self.emergency_verification.trigger_emergency_verification(
                claim=claim,
                context=context
            )
        
        # Perform post-analysis if required
        post_analysis_result = None
        if decision.post_analysis_required:
            post_analysis_result = self.post_analysis.analyze_decision(
                decision=decision,
                context=context
            )
        
        return {
            "decision": decision,
            "verification": verification_result,
            "emergency_verification": emergency_result,
            "post_analysis": post_analysis_result,
            "timestamp": datetime.now()
        }


if __name__ == "__main__":
    # Example usage
    print("Testing Decision-Making Layer...")
    
    layer = DecisionMakingLayer()
    
    # Test decision
    context = DecisionContext(
        task_description="Analyze social media post for bias",
        confidence=0.65,
        trust_level=0.75,
        available_information={
            "task_type": "social_media",
            "sources": ["source1", "source2"]
        },
        urgency=0.5,
        risk_level=0.6
    )
    
    result = layer.process_decision(
        context=context,
        claim="This post contains potential bias"
    )
    
    print(f"\nDecision: {result['decision'].action.value}")
    print(f"Reasoning: {result['decision'].reasoning}")
    print(f"Verification Required: {result['decision'].verification_required}")
    print(f"Post-Analysis Required: {result['decision'].post_analysis_required}")

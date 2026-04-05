# project_guardian/feedback_loop_core.py
# FeedbackLoopCore: Performance Evaluation and Learning
# Based on Conversation 4 (Feedback Loop Evaluation) design specifications

import logging
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from collections import defaultdict

try:
    from .ask_ai import AskAI, AIProvider
except ImportError:
    try:
        from ask_ai import AskAI, AIProvider
    except ImportError:
        AskAI = None
        AIProvider = None

logger = logging.getLogger(__name__)


class EvaluationType(Enum):
    """Types of evaluations."""
    ACCURACY = "accuracy"
    CREATIVITY = "creativity"
    STYLE = "style"
    USER_PREFERENCE = "user_preference"
    OVERALL = "overall"


@dataclass
class FeedbackEntry:
    """A single feedback entry."""
    entry_id: str
    prompt: str
    response: str
    evaluator_type: EvaluationType
    score: float  # 0.0-1.0
    feedback_text: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entry_id": self.entry_id,
            "prompt": self.prompt[:100],  # Truncate for storage
            "response": self.response[:100],
            "evaluator_type": self.evaluator_type.value,
            "score": self.score,
            "feedback_text": self.feedback_text,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


class AccuracyEvaluator:
    """Evaluates factual correctness of responses."""
    
    def __init__(self, ask_ai: Optional[AskAI] = None):
        self.ask_ai = ask_ai
    
    def evaluate(self, prompt: str, response: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Evaluate accuracy of a response.
        Enhanced with AI-based fact-checking when available.
        
        Args:
            prompt: Original prompt
            response: Generated response
            context: Optional context for validation
            
        Returns:
            Evaluation result with score and feedback
        """
        # Try AI-based accuracy evaluation first (sync wrapper for async)
        if self.ask_ai:
            try:
                import asyncio
                loop = None
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                if loop.is_running():
                    # If loop is running, schedule for later (non-blocking)
                    logger.debug("Event loop running, skipping AI accuracy check for now")
                else:
                    ai_result = loop.run_until_complete(self._ai_accuracy_check(prompt, response))
                    if ai_result:
                        return ai_result
            except Exception as e:
                logger.debug(f"AI accuracy check failed: {e}")
        
        # Fallback to heuristic-based evaluation
        score = 0.7  # Default/placeholder score
        feedback = "Accuracy evaluation - heuristic-based"
        
        # Simple heuristics
        if "I don't know" in response or "I'm not sure" in response:
            # Honest uncertainty is better than false confidence
            score = 0.8
        elif len(response) < 10:
            # Very short responses might be incomplete
            score = 0.5
        
        return {
            "score": score,
            "feedback": feedback,
            "confidence": 0.5
        }
    
    async def _ai_accuracy_check(self, prompt: str, response: str) -> Optional[Dict[str, Any]]:
        """Use AI to fact-check and evaluate accuracy."""
        if not self.ask_ai:
            return None
        
        check_prompt = f"""Evaluate the factual accuracy of this response on a scale of 0.0 to 1.0:

Prompt: {prompt}
Response: {response}

Provide:
1. A score (0.0-1.0) for factual accuracy
2. Brief feedback on any inaccuracies or uncertainties
3. Confidence level (0.0-1.0)

Return as JSON: {{"score": 0.0-1.0, "feedback": "text", "confidence": 0.0-1.0}}"""

        try:
            ai_response = await self.ask_ai.ask(
                prompt=check_prompt,
                provider=AIProvider.OPENAI,
                temperature=0.3,
                max_tokens=300
            )
            
            if ai_response.success:
                import json
                import re
                
                # Extract JSON
                content = ai_response.content.strip()
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(0))
                    return {
                        "score": float(result.get("score", 0.7)),
                        "feedback": result.get("feedback", "AI accuracy evaluation"),
                        "confidence": float(result.get("confidence", 0.7))
                    }
        except Exception as e:
            logger.debug(f"AI accuracy check error: {e}")
        
        return None


class CreativityEvaluator:
    """Evaluates creativity and originality of responses."""
    
    def evaluate(self, prompt: str, response: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Evaluate creativity of a response.
        
        Args:
            prompt: Original prompt
            response: Generated response
            context: Optional context
            
        Returns:
            Evaluation result
        """
        score = 0.6  # Default
        feedback = "Creativity evaluation placeholder"
        
        # Simple heuristics
        unique_words = len(set(response.lower().split()))
        total_words = len(response.split())
        diversity = unique_words / total_words if total_words > 0 else 0
        
        # More diverse vocabulary = more creative
        if diversity > 0.7:
            score = 0.8
        elif diversity < 0.3:
            score = 0.4
        
        return {
            "score": score,
            "feedback": feedback,
            "diversity_score": diversity
        }


class StyleEvaluator:
    """Evaluates style and tone appropriateness."""
    
    def evaluate(
        self,
        prompt: str,
        response: str,
        target_style: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate style match.
        
        Args:
            prompt: Original prompt
            response: Generated response
            target_style: Desired style (formal, casual, technical, etc.)
            context: Optional context
            
        Returns:
            Evaluation result
        """
        score = 0.7  # Default
        feedback = "Style evaluation placeholder"
        
        # Simple style detection
        formal_indicators = ["therefore", "furthermore", "consequently"]
        casual_indicators = ["yeah", "okay", "gonna", "wanna"]
        
        formal_count = sum(1 for word in formal_indicators if word in response.lower())
        casual_count = sum(1 for word in casual_indicators if word in response.lower())
        
        detected_style = "formal" if formal_count > casual_count else "casual"
        
        if target_style and detected_style == target_style:
            score = 0.9
        elif target_style:
            score = 0.5
        
        return {
            "score": score,
            "feedback": feedback,
            "detected_style": detected_style
        }


class UserPreferenceMatcher:
    """Matches responses to user preferences."""
    
    def __init__(self):
        self.preference_history: List[Dict[str, Any]] = []
    
    def record_preference(
        self,
        prompt: str,
        response: str,
        user_rating: float,
        user_feedback: Optional[str] = None
    ):
        """Record a user preference."""
        self.preference_history.append({
            "prompt": prompt[:100],
            "response": response[:100],
            "rating": user_rating,
            "feedback": user_feedback,
            "timestamp": datetime.now().isoformat()
        })
    
    def evaluate(self, prompt: str, response: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Evaluate how well response matches user preferences.
        
        Args:
            prompt: Original prompt
            response: Generated response
            context: Optional context
            
        Returns:
            Evaluation result
        """
        if not self.preference_history:
            return {
                "score": 0.5,
                "feedback": "No preference history available"
            }
        
        # Find similar prompts in history
        # In production, would use semantic similarity
        # For now, simple keyword matching
        prompt_words = set(prompt.lower().split())
        avg_score = 0.5
        
        matching_entries = 0
        total_rating = 0.0
        
        for entry in self.preference_history[-10:]:  # Last 10 preferences
            entry_words = set(entry["prompt"].lower().split())
            overlap = len(prompt_words & entry_words)
            
            if overlap > 0:
                matching_entries += 1
                total_rating += entry["rating"]
        
        if matching_entries > 0:
            avg_score = total_rating / matching_entries
        
        return {
            "score": avg_score,
            "feedback": f"Based on {matching_entries} similar preferences",
            "matching_entries": matching_entries
        }


class FeedbackSynthesizer:
    """Synthesizes feedback from multiple evaluators."""
    
    def synthesize(
        self,
        evaluations: Dict[EvaluationType, Dict[str, Any]],
        weights: Optional[Dict[EvaluationType, float]] = None
    ) -> Dict[str, Any]:
        """
        Combine multiple evaluations into overall feedback.
        
        Args:
            evaluations: Dictionary of evaluator_type -> evaluation result
            weights: Optional weights for each evaluator (defaults to equal)
            
        Returns:
            Synthesized feedback
        """
        if not evaluations:
            return {
                "overall_score": 0.5,
                "feedback": "No evaluations provided",
                "breakdown": {}
            }
        
        weights = weights or {
            EvaluationType.ACCURACY: 0.3,
            EvaluationType.CREATIVITY: 0.2,
            EvaluationType.STYLE: 0.2,
            EvaluationType.USER_PREFERENCE: 0.3
        }
        
        weighted_sum = 0.0
        total_weight = 0.0
        breakdown = {}
        
        for eval_type, result in evaluations.items():
            score = result.get("score", 0.5)
            weight = weights.get(eval_type, 0.25)
            
            weighted_sum += score * weight
            total_weight += weight
            breakdown[eval_type.value] = {
                "score": score,
                "weight": weight,
                "feedback": result.get("feedback", "")
            }
        
        overall_score = weighted_sum / total_weight if total_weight > 0 else 0.5
        
        # Generate overall feedback
        if overall_score >= 0.8:
            overall_feedback = "Excellent response"
        elif overall_score >= 0.6:
            overall_feedback = "Good response"
        elif overall_score >= 0.4:
            overall_feedback = "Adequate response"
        else:
            overall_feedback = "Needs improvement"
        
        return {
            "overall_score": overall_score,
            "feedback": overall_feedback,
            "breakdown": breakdown
        }


class FeedbackLoopCore:
    """
    Evaluates outputs and incorporates feedback to continuously improve.
    Uses multiple evaluators and learns from user preferences.
    """
    
    def __init__(
        self,
        storage_path: str = "data/feedback_loop.json",
        ask_ai: Optional[AskAI] = None
    ):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.ask_ai = ask_ai
        
        # Evaluators (with AI integration)
        self.accuracy_evaluator = AccuracyEvaluator(ask_ai=ask_ai)
        self.creativity_evaluator = CreativityEvaluator()
        self.style_evaluator = StyleEvaluator()
        self.user_preference_matcher = UserPreferenceMatcher()
        self.synthesizer = FeedbackSynthesizer()
        
        # Feedback storage
        self.feedback_entries: List[FeedbackEntry] = []
        
        # Learning data
        self.pattern_learned: Dict[str, Any] = {}
        
        self.load()
    
    def evaluate_output(
        self,
        prompt: str,
        response: str,
        evaluation_types: Optional[List[EvaluationType]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate an output using multiple evaluators.
        
        Args:
            prompt: Original prompt
            response: Generated response
            evaluation_types: Types of evaluation to perform (defaults to all)
            context: Optional context
            
        Returns:
            Complete evaluation result
        """
        evaluation_types = evaluation_types or [
            EvaluationType.ACCURACY,
            EvaluationType.CREATIVITY,
            EvaluationType.STYLE
        ]
        
        evaluations = {}
        
        # Run each evaluator
        if EvaluationType.ACCURACY in evaluation_types:
            evaluations[EvaluationType.ACCURACY] = self.accuracy_evaluator.evaluate(
                prompt, response, context
            )
        
        if EvaluationType.CREATIVITY in evaluation_types:
            evaluations[EvaluationType.CREATIVITY] = self.creativity_evaluator.evaluate(
                prompt, response, context
            )
        
        if EvaluationType.STYLE in evaluation_types:
            target_style = context.get("target_style") if context else None
            evaluations[EvaluationType.STYLE] = self.style_evaluator.evaluate(
                prompt, response, target_style, context
            )
        
        if EvaluationType.USER_PREFERENCE in evaluation_types:
            evaluations[EvaluationType.USER_PREFERENCE] = self.user_preference_matcher.evaluate(
                prompt, response, context
            )
        
        # Synthesize results
        synthesized = self.synthesizer.synthesize(evaluations)
        
        # Store feedback
        for eval_type, result in evaluations.items():
            entry = FeedbackEntry(
                entry_id=f"{datetime.now().timestamp()}_{eval_type.value}",
                prompt=prompt,
                response=response,
                evaluator_type=eval_type,
                score=result.get("score", 0.5),
                feedback_text=result.get("feedback"),
                metadata=result
            )
            self.feedback_entries.append(entry)
        
        self.save()
        
        return synthesized
    
    def record_user_feedback(
        self,
        prompt: str,
        response: str,
        user_rating: float,
        user_feedback: Optional[str] = None
    ):
        """Record explicit user feedback."""
        self.user_preference_matcher.record_preference(
            prompt=prompt,
            response=response,
            user_rating=user_rating,
            user_feedback=user_feedback
        )
        
        # Also store as feedback entry
        entry = FeedbackEntry(
            entry_id=f"user_{datetime.now().timestamp()}",
            prompt=prompt,
            response=response,
            evaluator_type=EvaluationType.USER_PREFERENCE,
            score=user_rating,
            feedback_text=user_feedback,
            metadata={"source": "user"}
        )
        self.feedback_entries.append(entry)
        self.save()
    
    def identify_biases(self, recent_count: int = 100) -> Dict[str, Any]:
        """
        Identify biases or errors in recent outputs.
        
        Args:
            recent_count: Number of recent entries to analyze
            
        Returns:
            Bias analysis results
        """
        recent = self.feedback_entries[-recent_count:]
        
        if not recent:
            return {
                "biases_found": [],
                "analysis": "No recent feedback to analyze"
            }
        
        # Analyze scores by category
        scores_by_type = defaultdict(list)
        for entry in recent:
            scores_by_type[entry.evaluator_type].append(entry.score)
        
        biases = []
        
        # Check for consistently low scores
        for eval_type, scores in scores_by_type.items():
            avg_score = sum(scores) / len(scores) if scores else 0.5
            if avg_score < 0.4:
                biases.append({
                    "type": eval_type.value,
                    "issue": f"Consistently low {eval_type.value} scores (avg: {avg_score:.2f})",
                    "severity": "high"
                })
        
        return {
            "biases_found": biases,
            "total_entries_analyzed": len(recent),
            "average_scores": {
                k.value: sum(v) / len(v) if v else 0.5
                for k, v in scores_by_type.items()
            }
        }
    
    def get_learning_insights(self) -> Dict[str, Any]:
        """Get insights learned from feedback."""
        if not self.feedback_entries:
            return {"insights": "No feedback collected yet"}
        
        # Analyze patterns
        recent = self.feedback_entries[-50:]  # Last 50 entries
        
        # Average scores over time
        early_scores = [e.score for e in recent[:25]]
        late_scores = [e.score for e in recent[25:]]
        
        early_avg = sum(early_scores) / len(early_scores) if early_scores else 0.5
        late_avg = sum(late_scores) / len(late_scores) if late_scores else 0.5
        
        improvement = late_avg - early_avg
        
        return {
            "total_feedback_entries": len(self.feedback_entries),
            "early_period_avg": early_avg,
            "recent_period_avg": late_avg,
            "improvement": improvement,
            "trend": "improving" if improvement > 0.05 else "declining" if improvement < -0.05 else "stable"
        }
    
    def save(self):
        """Save feedback loop data."""
        data = {
            "entries": [entry.to_dict() for entry in self.feedback_entries[-1000:]],  # Keep last 1000
            "preferences": self.user_preference_matcher.preference_history,
            "updated_at": datetime.now().isoformat()
        }
        
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load(self):
        """Load feedback loop data."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            for entry_data in data.get("entries", []):
                entry = FeedbackEntry(
                    entry_id=entry_data["entry_id"],
                    prompt=entry_data["prompt"],
                    response=entry_data["response"],
                    evaluator_type=EvaluationType(entry_data["evaluator_type"]),
                    score=entry_data["score"],
                    feedback_text=entry_data.get("feedback_text"),
                    timestamp=datetime.fromisoformat(entry_data["timestamp"]),
                    metadata=entry_data.get("metadata", {})
                )
                self.feedback_entries.append(entry)
            
            self.user_preference_matcher.preference_history = data.get("preferences", [])
            
            logger.info(f"Loaded {len(self.feedback_entries)} feedback entries")
        except Exception as e:
            logger.error(f"Error loading feedback loop: {e}")


# Example usage
if __name__ == "__main__":
    loop = FeedbackLoopCore()
    
    # Evaluate an output
    result = loop.evaluate_output(
        prompt="What is machine learning?",
        response="Machine learning is a subset of artificial intelligence that enables systems to learn from data.",
        evaluation_types=[EvaluationType.ACCURACY, EvaluationType.STYLE]
    )
    
    print(f"Overall score: {result['overall_score']:.2f}")
    print(f"Feedback: {result['feedback']}")
    
    # Record user feedback
    loop.record_user_feedback(
        prompt="What is machine learning?",
        response="Machine learning is a subset of artificial intelligence...",
        user_rating=0.9,
        user_feedback="Clear and accurate explanation"
    )
    
    # Get insights
    insights = loop.get_learning_insights()
    print(f"Learning insights: {insights}")


# project_guardian/feedback_loop.py
# FeedbackLoop-Core: Multi-Dimensional Output Evaluation System
# Based on Conversation 4 design specifications

import logging
from typing import Any, Dict, List, Optional, Tuple
from abc import ABC, abstractmethod
from datetime import datetime

logger = logging.getLogger(__name__)


class BaseEvaluator(ABC):
    """Abstract base class for all evaluators."""
    
    @abstractmethod
    def evaluate(self, output: str, context: Optional[Dict[str, Any]] = None) -> Tuple[int, str]:
        """
        Evaluate output and return score and advice.
        
        Args:
            output: The output to evaluate
            context: Optional context about the output
            
        Returns:
            Tuple of (score: int, advice: str)
            Score is 1-5, where 5 is best
        """
        pass


class AccuracyEvaluator(BaseEvaluator):
    """
    Assesses factual reliability and internal consistency.
    Flags hallucinations, unverifiable claims, misleading information.
    """
    
    def evaluate(self, output: str, context: Optional[Dict[str, Any]] = None) -> Tuple[int, str]:
        """
        Evaluate factual accuracy.
        
        Returns:
            (score 1-5, advice string)
        """
        score = 5  # Start with perfect score
        advice_parts = []
        
        # Check for vague generalizations
        vague_phrases = [
            "some people say",
            "it is believed that",
            "many experts",
            "studies show",
            "research indicates"
        ]
        
        vague_count = sum(1 for phrase in vague_phrases if phrase.lower() in output.lower())
        if vague_count > 2:
            score -= 1
            advice_parts.append("Reduce vague generalizations; cite specific examples")
            
        # Check for absolute claims without support
        absolute_phrases = [
            "always",
            "never",
            "all",
            "none",
            "every"
        ]
        
        absolute_count = sum(1 for phrase in absolute_phrases if phrase.lower() in output.lower())
        if absolute_count > 3:
            score -= 1
            advice_parts.append("Avoid absolute claims without citations or qualifiers")
            
        # Check for conflicting statements (simplified)
        if output.lower().count("however") > 2:
            score -= 1
            advice_parts.append("Review for internal consistency")
            
        # Check for numbers/statistics without context
        import re
        numbers = re.findall(r'\d+', output)
        if len(numbers) > 5 and not any("source" in output.lower() or "according" in output.lower()):
            score -= 1
            advice_parts.append("Cite sources for statistical claims")
            
        # Ensure score stays in range
        score = max(1, min(5, score))
        
        if not advice_parts:
            advice = "Output is factually sound and well-supported"
        else:
            advice = "; ".join(advice_parts)
            
        return (score, advice)


class CreativityEvaluator(BaseEvaluator):
    """
    Assesses novelty, imagination, and risk-taking.
    Determines if output was too generic or safe.
    """
    
    def evaluate(self, output: str, context: Optional[Dict[str, Any]] = None) -> Tuple[int, str]:
        """
        Evaluate creativity and originality.
        
        Returns:
            (score 1-5, advice string)
        """
        score = 3  # Start with neutral
        advice_parts = []
        
        # Check for generic phrases
        generic_phrases = [
            "it is important",
            "in conclusion",
            "as we can see",
            "it should be noted",
            "generally speaking"
        ]
        
        generic_count = sum(1 for phrase in generic_phrases if phrase.lower() in output.lower())
        if generic_count > 2:
            score -= 1
            advice_parts.append("Output is too generic; add unique perspective or metaphor")
            
        # Check for creative elements
        creative_indicators = [
            "metaphor",
            "analogy",
            "imagine",
            "suppose",
            "what if"
        ]
        
        has_creative = any(indicator in output.lower() for indicator in creative_indicators)
        if has_creative:
            score += 1
        else:
            if len(output) > 500:  # Longer outputs should have some creativity
                advice_parts.append("Add narrative twist, metaphor, or creative angle")
                score -= 1
                
        # Check for risk-taking (uncommon words/ideas)
        words = output.split()
        if len(words) > 50:
            # Check vocabulary diversity
            unique_words = len(set(word.lower() for word in words))
            diversity = unique_words / len(words)
            if diversity > 0.7:
                score += 1
            elif diversity < 0.5:
                score -= 1
                advice_parts.append("Increase vocabulary diversity")
                
        # Check engagement level
        questions = output.count("?")
        if questions == 0 and len(output) > 300:
            score -= 1
            advice_parts.append("Consider adding questions to engage reader")
            
        # Ensure score stays in range
        score = max(1, min(5, score))
        
        if score >= 4 and not advice_parts:
            advice = "Output is creative and engaging"
        elif not advice_parts:
            advice = "Consider increasing temperature or adding narrative elements"
        else:
            advice = "; ".join(advice_parts)
            
        return (score, advice)


class StyleEvaluator(BaseEvaluator):
    """
    Evaluates tone, voice, and formatting style.
    Flags awkward phrasing, mismatched voice, excessive verbosity.
    """
    
    def evaluate(self, output: str, context: Optional[Dict[str, Any]] = None) -> Tuple[int, str]:
        """
        Evaluate style, tone, and clarity.
        
        Returns:
            (score 1-5, advice string)
        """
        score = 5  # Start with perfect
        advice_parts = []
        
        # Check for excessive verbosity
        avg_word_length = sum(len(word) for word in output.split()) / max(len(output.split()), 1)
        if avg_word_length > 6:
            score -= 1
            advice_parts.append("More concise; use shorter, clearer words")
            
        # Check sentence length
        sentences = output.split('.')
        long_sentences = [s for s in sentences if len(s.split()) > 25]
        if len(long_sentences) > len(sentences) * 0.3:
            score -= 1
            advice_parts.append("Break up long sentences")
            
        # Check for passive voice (simplified)
        passive_indicators = ["was", "were", "been", "being"]
        passive_count = sum(1 for word in output.split() if word.lower() in passive_indicators)
        if passive_count > len(output.split()) * 0.15:
            score -= 1
            advice_parts.append("Switch to active voice where possible")
            
        # Check for contractions (affects tone)
        contractions = ["don't", "can't", "won't", "it's", "you're"]
        has_contractions = any(cont in output.lower() for cont in contractions)
        if not has_contractions and len(output) > 200:
            # Might be too formal
            if "cannot" in output.lower() or "do not" in output.lower():
                advice_parts.append("Consider using contractions for more natural tone")
                
        # Check for repetitive words
        words = output.lower().split()
        if len(words) > 10:
            word_counts = {}
            for word in words:
                if len(word) > 3:  # Ignore short words
                    word_counts[word] = word_counts.get(word, 0) + 1
                    
            repeated = [word for word, count in word_counts.items() if count > 5]
            if repeated:
                score -= 1
                advice_parts.append(f"Avoid repeating: {', '.join(repeated[:3])}")
                
        # Check structure/clarity
        paragraphs = output.split('\n\n')
        if len(paragraphs) == 1 and len(output) > 500:
            score -= 1
            advice_parts.append("Break into paragraphs for better structure")
            
        # Ensure score stays in range
        score = max(1, min(5, score))
        
        if not advice_parts:
            advice = "Style is clear and well-structured"
        else:
            advice = "; ".join(advice_parts)
            
        return (score, advice)


class UserPreferenceMatcher(BaseEvaluator):
    """
    Checks alignment with known user preferences and recent feedback.
    Cross-checks style, format, tone against logged preferences.
    """
    
    def __init__(self):
        self.preference_log: List[Dict[str, Any]] = []
        
    def log_preference(self, user_id: str, preference_type: str, value: Any):
        """Log a user preference."""
        self.preference_log.append({
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "type": preference_type,
            "value": value
        })
        
    def evaluate(self, output: str, context: Optional[Dict[str, Any]] = None) -> Tuple[int, str]:
        """
        Evaluate against user preferences.
        
        Returns:
            (score 1-5, advice string)
        """
        score = 4  # Default to good
        advice_parts = []
        
        if not context:
            context = {}
            
        user_id = context.get("user_id", "default")
        
        # Get recent preferences for this user
        user_prefs = [
            pref for pref in self.preference_log
            if pref.get("user_id") == user_id
        ][-10:]  # Last 10 preferences
        
        if not user_prefs:
            # No preferences yet - neutral score
            return (3, "No user preferences logged yet")
            
        # Check against logged preferences
        for pref in user_prefs:
            pref_type = pref.get("type")
            pref_value = pref.get("value")
            
            if pref_type == "tone":
                if pref_value == "formal" and any(word in output.lower() for word in ["don't", "can't", "it's"]):
                    score -= 1
                    advice_parts.append("User prefers formal tone (avoid contractions)")
                elif pref_value == "casual" and "cannot" in output.lower():
                    score -= 1
                    advice_parts.append("User prefers casual tone (use contractions)")
                    
            elif pref_type == "length":
                if pref_value == "concise" and len(output) > 500:
                    score -= 1
                    advice_parts.append("User prefers concise output")
                elif pref_value == "detailed" and len(output) < 200:
                    score -= 1
                    advice_parts.append("User prefers detailed output")
                    
            elif pref_type == "style":
                if pref_value == "technical" and output.count("?") > 2:
                    score -= 1
                    advice_parts.append("User prefers technical style (fewer questions)")
                elif pref_value == "conversational" and output.count("?") == 0:
                    score -= 1
                    advice_parts.append("User prefers conversational style (add questions)")
                    
        # Ensure score stays in range
        score = max(1, min(5, score))
        
        if not advice_parts:
            advice = "Output aligns with user preferences"
        else:
            advice = "; ".join(advice_parts)
            
        return (score, advice)


class FeedbackSynthesizer:
    """
    Consolidates scores and advice from all evaluators.
    Generates unified Feedback Report.
    """
    
    def synthesize(
        self,
        evaluator_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Synthesize feedback from all evaluators.
        
        Args:
            evaluator_results: List of results from evaluators
                Each should have: module, score, advice
        
        Returns:
            Unified feedback report
        """
        if not evaluator_results:
            return {
                "feedback_summary": "No evaluators provided results",
                "average_score": 0,
                "adjustments": [],
                "detailed_results": []
            }
            
        # Calculate average score
        scores = [result.get("score", 3) for result in evaluator_results]
        average_score = sum(scores) / len(scores) if scores else 0
        
        # Collect all advice
        adjustments = []
        for result in evaluator_results:
            advice = result.get("advice", "")
            if advice and advice not in adjustments:
                adjustments.append(advice)
                
        # Generate summary
        if average_score >= 4.5:
            summary = "Output quality is excellent across all dimensions"
        elif average_score >= 3.5:
            summary = "Output quality is good with minor improvements possible"
        elif average_score >= 2.5:
            summary = "Output quality is moderate; several areas need improvement"
        else:
            summary = "Output quality needs significant improvement"
            
        return {
            "feedback_summary": summary,
            "average_score": round(average_score, 2),
            "adjustments": adjustments,
            "detailed_results": evaluator_results,
            "timestamp": datetime.now().isoformat()
        }


class FeedbackLoopCore:
    """
    Central coordinator for DreamCore's feedback and learning system.
    Routes evaluations to specialized submodules.
    Compiles Feedback Reports for MemoryBank, GenerationEngine, and DreamCore-Orchestrator.
    """
    
    def __init__(self, prompt_evolver: Optional[Any] = None):
        self.accuracy_evaluator = AccuracyEvaluator()
        self.prompt_evolver = prompt_evolver
        self.creativity_evaluator = CreativityEvaluator()
        self.style_evaluator = StyleEvaluator()
        self.preference_matcher = UserPreferenceMatcher()
        self.synthesizer = FeedbackSynthesizer()
        
        self.evaluation_history: List[Dict[str, Any]] = []
        
    def evaluate_output(
        self,
        output: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run full evaluation cycle on an output.
        
        Args:
            output: Output text to evaluate
            context: Optional context (user_id, task_type, etc.)
            
        Returns:
            Complete feedback report
        """
        if not context:
            context = {}
            
        # Run all evaluators
        evaluator_results = []
        
        # Accuracy evaluation
        accuracy_score, accuracy_advice = self.accuracy_evaluator.evaluate(output, context)
        evaluator_results.append({
            "module": "feedbackloop.accuracy_evaluator",
            "score": accuracy_score,
            "advice": accuracy_advice
        })
        
        # Creativity evaluation
        creativity_score, creativity_advice = self.creativity_evaluator.evaluate(output, context)
        evaluator_results.append({
            "module": "feedbackloop.creativity_evaluator",
            "score": creativity_score,
            "advice": creativity_advice
        })
        
        # Style evaluation
        style_score, style_advice = self.style_evaluator.evaluate(output, context)
        evaluator_results.append({
            "module": "feedbackloop.style_evaluator",
            "score": style_score,
            "advice": style_advice
        })
        
        # User preference matching
        pref_score, pref_advice = self.preference_matcher.evaluate(output, context)
        evaluator_results.append({
            "module": "feedbackloop.user_preference_matcher",
            "score": pref_score,
            "advice": pref_advice
        })
        
        # Synthesize feedback
        feedback_report = self.synthesizer.synthesize(evaluator_results)
        
        # Store in history
        evaluation_record = {
            "timestamp": datetime.now().isoformat(),
            "output_length": len(output),
            "context": context,
            "feedback_report": feedback_report
        }
        self.evaluation_history.append(evaluation_record)
        
        # Keep only last 100 evaluations
        if len(self.evaluation_history) > 100:
            self.evaluation_history = self.evaluation_history[-100:]
        
        # Log for prompt evolution when context has prompt (1-5 scale -> 0-1 for evolver)
        if self.prompt_evolver and context.get("prompt"):
            score_01 = feedback_report["average_score"] / 5.0
            self.prompt_evolver.log_interaction(
                task_type=context.get("task_type", "evaluation"),
                prompt=context["prompt"],
                response=output,
                score=score_01,
                feedback=feedback_report.get("feedback_summary"),
            )
            
        logger.info(f"Feedback evaluation completed: avg_score={feedback_report['average_score']:.2f}")
        
        return feedback_report
        
    def log_user_preference(
        self,
        user_id: str,
        preference_type: str,
        value: Any
    ):
        """Log a user preference for future matching."""
        self.preference_matcher.log_preference(user_id, preference_type, value)
        
    def get_evaluation_history(
        self,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get recent evaluation history."""
        return self.evaluation_history[-limit:]
        
    def get_performance_trends(self) -> Dict[str, Any]:
        """Analyze performance trends over time."""
        if not self.evaluation_history:
            return {"message": "No evaluation history"}
            
        # Calculate average scores over time
        recent = self.evaluation_history[-20:]
        older = self.evaluation_history[:-20] if len(self.evaluation_history) > 20 else []
        
        recent_avg = sum(
            eval_record["feedback_report"]["average_score"]
            for eval_record in recent
        ) / len(recent) if recent else 0
        
        older_avg = sum(
            eval_record["feedback_report"]["average_score"]
            for eval_record in older
        ) / len(older) if older else recent_avg
        
        trend = "improving" if recent_avg > older_avg else "declining" if recent_avg < older_avg else "stable"
        
        return {
            "recent_average": round(recent_avg, 2),
            "older_average": round(older_avg, 2),
            "trend": trend,
            "total_evaluations": len(self.evaluation_history)
        }


# Integration adapter for ElysiaLoop-Core
from .elysia_loop_core import BaseModuleAdapter


class FeedbackLoopAdapter(BaseModuleAdapter):
    """Adapter for FeedbackLoop-Core module."""
    
    def __init__(self, feedback_loop: FeedbackLoopCore):
        self.feedback_loop = feedback_loop
        
    def get_module_name(self) -> str:
        return "feedback_loop"
        
    def get_capabilities(self) -> List[str]:
        return ["evaluate_output", "log_user_preference", "get_evaluation_history", "get_performance_trends"]
        
    def execute(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if method == "evaluate_output":
                output = payload.get("output", "")
                context = payload.get("context", {})
                result = self.feedback_loop.evaluate_output(output, context)
                return {"success": True, "feedback_report": result}
                
            elif method == "log_user_preference":
                user_id = payload.get("user_id", "default")
                preference_type = payload.get("preference_type", "")
                value = payload.get("value")
                self.feedback_loop.log_user_preference(user_id, preference_type, value)
                return {"success": True, "message": "Preference logged"}
                
            elif method == "get_evaluation_history":
                limit = payload.get("limit", 20)
                history = self.feedback_loop.get_evaluation_history(limit)
                return {"success": True, "history": history}
                
            elif method == "get_performance_trends":
                trends = self.feedback_loop.get_performance_trends()
                return {"success": True, "trends": trends}
                
            else:
                return {"success": False, "error": f"Unknown method: {method}"}
                
        except Exception as e:
            logger.error(f"FeedbackLoop error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


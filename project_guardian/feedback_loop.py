# project_guardian/feedback_loop.py
# FeedbackLoop-Core: Multi-Dimensional Output Evaluation System
# Based on Conversation 4 design specifications

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from abc import ABC, abstractmethod
from datetime import datetime

logger = logging.getLogger(__name__)


def _word_tokens(output: str) -> List[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z0-9_'-]*", str(output or "").lower())


def _phrase_count(output: str, phrases: List[str]) -> int:
    text = f" {str(output or '').lower()} "
    count = 0
    for phrase in phrases:
        pattern = r"(?<![a-zA-Z0-9_])" + re.escape(phrase.lower()) + r"(?![a-zA-Z0-9_])"
        if re.search(pattern, text):
            count += 1
    return count


def _context_terms(context: Optional[Dict[str, Any]], key: str) -> List[str]:
    if not context:
        return []
    value = context.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _clamp_score(score: int) -> int:
    return max(1, min(5, int(score)))


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
        context = context or {}
        output = str(output or "")
        score = 5  # Start with perfect score
        advice_parts = []
        output_lower = output.lower()

        if not output.strip():
            return (1, "Output is empty; provide a substantive response")
        
        # Check for vague generalizations
        vague_phrases = [
            "some people say",
            "it is believed that",
            "many experts",
            "studies show",
            "research indicates",
            "everyone knows",
            "obviously"
        ]
        
        vague_count = _phrase_count(output, vague_phrases)
        if vague_count:
            score -= min(2, vague_count)
            advice_parts.append("Replace vague authority claims with specific evidence or qualifiers")
            
        # Check for absolute claims without support
        absolute_phrases = [
            "always",
            "never",
            "all",
            "none",
            "every"
        ]
        
        words = _word_tokens(output)
        absolute_count = sum(1 for word in words if word in absolute_phrases)
        if absolute_count > 3:
            score -= 1
            advice_parts.append("Avoid absolute claims without citations or qualifiers")
            
        # Check for conflicting statements (simplified)
        if output_lower.count("however") > 2:
            score -= 1
            advice_parts.append("Review for internal consistency")
            
        # Check for numbers/statistics without context
        numbers = re.findall(r'\d+', output)
        has_source_language = any(token in output_lower for token in ("source", "according", "cited", "reported by"))
        if len(numbers) > 2 and not has_source_language:
            score -= 1
            advice_parts.append("Cite sources for statistical claims")

        required_terms = _context_terms(context, "required_terms")
        missing_terms = [term for term in required_terms if term.lower() not in output_lower]
        if missing_terms:
            score -= min(2, len(missing_terms))
            advice_parts.append(f"Include required term(s): {', '.join(missing_terms[:4])}")

        forbidden_terms = _context_terms(context, "forbidden_terms")
        present_forbidden = [term for term in forbidden_terms if term.lower() in output_lower]
        if present_forbidden:
            score -= min(2, len(present_forbidden))
            advice_parts.append(f"Remove forbidden term(s): {', '.join(present_forbidden[:4])}")

        source_required = bool(context.get("source_required") or context.get("requires_citation"))
        if source_required and not has_source_language:
            score -= 1
            advice_parts.append("Add an explicit source reference for this task")
            
        # Ensure score stays in range
        score = _clamp_score(score)
        
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
        context = context or {}
        output = str(output or "")
        score = 3  # Start with neutral
        advice_parts = []

        if not output.strip():
            return (1, "Output is empty; add a concrete response before judging originality")
        
        # Check for generic phrases
        generic_phrases = [
            "it is important",
            "in conclusion",
            "as we can see",
            "it should be noted",
            "generally speaking",
            "this is a test",
            "some content",
            "at the end of the day"
        ]
        
        generic_count = _phrase_count(output, generic_phrases)
        if generic_count:
            score -= min(2, generic_count)
            advice_parts.append("Output is generic; add task-specific detail or a sharper point of view")
            
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
            if len(output) > 500 or context.get("task_type") in {"creative", "dream", "social_reply"}:
                advice_parts.append("Add a concrete image, comparison, or distinctive framing")
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

        if context.get("requires_actionable_detail") and not any(
            token in output.lower()
            for token in ("next", "step", "because", "therefore", "recommend", "plan", "test")
        ):
            score -= 1
            advice_parts.append("Add actionable detail tied to the task")
                
        # Check engagement level
        questions = output.count("?")
        if questions == 0 and len(output) > 300:
            score -= 1
            advice_parts.append("Consider adding questions to engage reader")
            
        # Ensure score stays in range
        score = _clamp_score(score)
        
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
        context = context or {}
        output = str(output or "")
        score = 5  # Start with perfect
        advice_parts = []

        if not output.strip():
            return (1, "Output is empty; provide readable content")
        
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

        max_words = context.get("max_words")
        if max_words:
            try:
                max_words_int = int(max_words)
                word_count = len(output.split())
                if max_words_int > 0 and word_count > max_words_int:
                    score -= 1
                    advice_parts.append(f"Shorten output to {max_words_int} words or fewer")
            except (TypeError, ValueError):
                pass

        required_format = str(context.get("required_format") or "").lower()
        if required_format == "bullets" and "- " not in output and "* " not in output:
            score -= 1
            advice_parts.append("Use bullet formatting as requested")
        elif required_format == "json":
            stripped = output.strip()
            if not (stripped.startswith("{") and stripped.endswith("}")):
                score -= 1
                advice_parts.append("Return valid JSON object formatting")
            
        # Ensure score stays in range
        score = _clamp_score(score)
        
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
        output = str(output or "")
        output_lower = output.lower()
            
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
                if pref_value == "formal" and any(word in output_lower for word in ["don't", "can't", "it's"]):
                    score -= 1
                    advice_parts.append("User prefers formal tone (avoid contractions)")
                elif pref_value == "casual" and "cannot" in output_lower:
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

            elif pref_type == "format":
                if pref_value == "bullets" and "- " not in output and "* " not in output:
                    score -= 1
                    advice_parts.append("User prefers bullet formatting")
                elif pref_value == "plain" and output.count("- ") > 3:
                    score -= 1
                    advice_parts.append("User prefers plain prose over long bullet lists")

            elif pref_type == "avoid":
                avoid_terms = _context_terms({"avoid": pref_value}, "avoid")
                found_terms = [term for term in avoid_terms if term.lower() in output_lower]
                if found_terms:
                    score -= min(2, len(found_terms))
                    advice_parts.append(f"User asked to avoid: {', '.join(found_terms[:4])}")

        desired_tone = context.get("target_tone")
        if desired_tone == "casual" and "cannot" in output_lower:
            score -= 1
            advice_parts.append("Context requests a more casual tone")
        elif desired_tone == "formal" and any(word in output_lower for word in ["don't", "can't", "it's"]):
            score -= 1
            advice_parts.append("Context requests a more formal tone")
                    
        # Ensure score stays in range
        score = _clamp_score(score)
        
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
        scores = [_clamp_score(result.get("score", 3)) for result in evaluator_results]
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

        lowest_score = min(scores) if scores else 0
        lowest_modules = [
            result.get("module", "unknown")
            for result in evaluator_results
            if _clamp_score(result.get("score", 3)) == lowest_score
        ]
        action_items = [
            result.get("advice", "")
            for result in evaluator_results
            if _clamp_score(result.get("score", 3)) < 4 and result.get("advice")
        ]
            
        return {
            "feedback_summary": summary,
            "average_score": round(average_score, 2),
            "needs_revision": average_score < 3.5 or any(score <= 2 for score in scores),
            "lowest_modules": lowest_modules,
            "adjustments": adjustments,
            "action_items": action_items,
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
        output = str(output or "")
        if not isinstance(context, dict):
            context = {}
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
            try:
                self.prompt_evolver.log_interaction(
                    task_type=context.get("task_type", "evaluation"),
                    prompt=context["prompt"],
                    response=output,
                    score=score_01,
                    feedback=feedback_report.get("feedback_summary"),
                )
            except Exception as exc:
                logger.debug("Prompt evolution logging skipped after feedback evaluation: %s", exc)
            
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
        try:
            limit = max(1, int(limit))
        except (TypeError, ValueError):
            limit = 20
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
            payload = payload if isinstance(payload, dict) else {}
            if method == "evaluate_output":
                output = payload.get("output", "")
                context = payload.get("context", {})
                if not isinstance(context, dict):
                    context = {}
                result = self.feedback_loop.evaluate_output(output, context)
                return {"success": True, "feedback_report": result}
                
            elif method == "log_user_preference":
                user_id = payload.get("user_id", "default")
                preference_type = payload.get("preference_type", "")
                value = payload.get("value")
                self.feedback_loop.log_user_preference(user_id, preference_type, value)
                return {"success": True, "message": "Preference logged"}
                
            elif method == "get_evaluation_history":
                try:
                    limit = max(1, int(payload.get("limit", 20)))
                except (TypeError, ValueError):
                    limit = 20
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


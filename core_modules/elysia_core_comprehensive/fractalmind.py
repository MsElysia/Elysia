"""
FractalMind - Task splitting engine for breaking complex tasks into subtasks
Integrated from old modules.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logging.warning("OpenAI not available. FractalMind will use fallback mode.")


DEFAULT_DEPTH = 3  # Baseline depth of reasoning
KEYWORDS_AMBIGUITY = [
    "not sure", "maybe", "unclear", "could be", "confusing", "unsure", "uncertain",
    "not certain", "perhaps", "might", "i don't know", "idk", "help me decide",
]

# Fallback templates when AI unavailable — domain hints for Elysia / Guardian
DOMAIN_FALLBACK_KEYWORDS = {
    "guardian": ["Review Guardian state", "Check memory pressure and cleanup", "Run next safe autonomy action"],
    "elysia": ["Sync with active objectives", "Verify module health", "Queue next exploratory step"],
    "autonomy": ["Pick next allowed action", "Avoid repeated blocked routes", "Log outcome for learning"],
    "objective": ["Refresh long-term objective status", "Advance one concrete step", "Record progress"],
    "research": ["Research", "Gather information", "Analyze findings"],
    "build": ["Design", "Implement", "Test"],
    "write": ["Outline", "Draft", "Edit", "Review"],
    "learn": ["Study", "Practice", "Apply"],
    "create": ["Plan", "Design", "Build", "Refine"],
}


class FractalMind:
    """
    Task splitting engine that breaks complex tasks into detailed subtasks.
    Uses AI to intelligently decompose tasks based on ambiguity detection.
    """
    
    def __init__(self, openai_client: Optional[Any] = None, api_key: Optional[str] = None, log_file: Optional[str] = None):
        """
        Initialize FractalMind.
        
        Args:
            openai_client: Optional OpenAI client instance
            api_key: Optional OpenAI API key (if client not provided); else OPENAI_API_KEY env
            log_file: Optional path for JSON log (default: <project>/data/fractalmind_log.json, or FRACTALMIND_LOG)
        """
        key = api_key or os.environ.get("OPENAI_API_KEY", "").strip()
        if openai_client:
            self.client = openai_client
        elif OPENAI_AVAILABLE and key:
            self.client = OpenAI(api_key=key)
        else:
            self.client = None
            logging.debug("FractalMind initialized without OpenAI client; using fallback mode")

        self.model = os.environ.get("FRACTALMIND_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
        if log_file:
            self.log_file = str(log_file).strip()
        elif os.environ.get("FRACTALMIND_LOG"):
            self.log_file = os.environ["FRACTALMIND_LOG"].strip()
        else:
            # Project root: .../core_modules/elysia_core_comprehensive/fractalmind.py -> parents[2]
            _root = Path(__file__).resolve().parents[2]
            self.log_file = str(_root / "data" / "fractalmind_log.json")
        self._last_gen_mode: str = "fallback"
    
    def is_ambiguous(self, prompt: str) -> bool:
        """Detect if a prompt contains ambiguity indicators"""
        prompt_lower = prompt.lower()
        return any(keyword in prompt_lower for keyword in KEYWORDS_AMBIGUITY)
    
    def generate_subtasks(self, prompt: str, depth: Optional[int] = None, model: Optional[str] = None) -> List[str]:
        """
        Generate subtasks from a prompt using AI or fallback logic.
        
        Args:
            prompt: The task prompt to break down
            depth: Number of subtasks to generate (default: auto-detect)
            model: OpenAI model to use
        
        Returns:
            List of subtask strings
        """
        if depth is None:
            depth = DEFAULT_DEPTH

        use_model = model or self.model
        self._last_gen_mode = "fallback"
        
        # Increase depth for ambiguous prompts
        if self.is_ambiguous(prompt):
            depth += 2
            logging.info(f"Ambiguous prompt detected. Increasing depth to {depth}")
        
        # Try AI-based generation
        if self.client:
            try:
                return self._generate_with_ai(prompt, depth, use_model)
            except Exception as e:
                logging.error(f"AI generation failed: {e}. Falling back to rule-based.")
        
        # Fallback to rule-based generation
        return self._generate_fallback(prompt, depth)
    
    def _generate_with_ai(self, prompt: str, depth: int, model: str) -> List[str]:
        """Generate subtasks using OpenAI"""
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": f"Break the following task into {depth} detailed, actionable subtasks. "
                              f"Each subtask should be specific and executable. "
                              f"Return only the subtasks, one per line, without numbering:\n\n{prompt}"
                }],
                max_tokens=500
            )
            content = response.choices[0].message.content.strip()
            
            # Parse subtasks from response
            subtasks = []
            for line in content.split("\n"):
                line = line.strip()
                if line:
                    # Remove common prefixes like "- ", "* ", "1. ", etc.
                    cleaned = line.lstrip("- *0123456789. ")
                    if cleaned:
                        subtasks.append(cleaned)
            
            if subtasks:
                self._last_gen_mode = "ai"
                return subtasks[:depth]
            return self._generate_fallback(prompt, depth)
        except Exception as e:
            logging.error(f"Error in AI generation: {e}")
            return self._generate_fallback(prompt, depth)
    
    def _generate_fallback(self, prompt: str, depth: int) -> List[str]:
        """Fallback rule-based subtask generation"""
        self._last_gen_mode = "fallback"
        prompt_lower = prompt.lower()
        subtasks: List[str] = []

        # Prefer domain-specific templates (first match wins; order matters for Elysia)
        for key, task_templates in DOMAIN_FALLBACK_KEYWORDS.items():
            if key in prompt_lower:
                subtasks = list(task_templates)[:depth]
                break

        if not subtasks:
            subtasks = [
                f"Analyze requirements for: {prompt[:50]}...",
                f"Plan approach for: {prompt[:50]}...",
                f"Execute: {prompt[:50]}...",
                f"Review and refine: {prompt[:50]}...",
            ]

        return subtasks[:depth]
    
    def save_log(
        self,
        prompt: str,
        subtasks: List[str],
        *,
        source: Optional[str] = None,
        requested_depth: Optional[int] = None,
    ) -> None:
        """Append one structured entry to the JSON log (creates data dir if needed)."""
        log_entry: Dict[str, Any] = {
            "timestamp": str(datetime.now()),
            "prompt": prompt,
            "subtasks": subtasks,
            "count": len(subtasks),
            "depth": len(subtasks),
            "requested_depth": requested_depth,
            "ambiguous": self.is_ambiguous(prompt),
            "mode": getattr(self, "_last_gen_mode", "fallback"),
            "model": self.model if self._last_gen_mode == "ai" else None,
        }
        if source:
            log_entry["source"] = source

        log_path = Path(self.log_file)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logging.error("FractalMind: could not create log directory %s: %s", log_path.parent, e)
            return

        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                log = json.load(f)
        except FileNotFoundError:
            log = []
        except (json.JSONDecodeError, TypeError) as e:
            logging.warning("FractalMind log reset (invalid JSON): %s", e)
            log = []

        if not isinstance(log, list):
            log = []

        log.append(log_entry)
        
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(log, f, indent=4)
        except Exception as e:
            logging.error(f"Failed to save log: {e}")
    
    def process_task(
        self,
        prompt: str,
        depth: Optional[int] = None,
        save_log: bool = True,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a task and return structured result.
        
        Args:
            prompt: Task prompt (must be str — dicts are rejected)
            depth: Optional depth override
            save_log: Whether to save to log file
            source: Optional caller label (e.g. guardian_autonomy) stored in JSON log
        
        Returns:
            Dictionary with subtasks and metadata
        """
        if not isinstance(prompt, str):
            raise TypeError(
                f"FractalMind.process_task expects prompt: str, got {type(prompt).__name__}. "
                "Pass a natural-language task description."
            )
        prompt = prompt.strip()
        if not prompt:
            return {
                "prompt": "",
                "subtasks": [],
                "count": 0,
                "ambiguous": False,
                "timestamp": str(datetime.now()),
                "error": "empty_prompt",
            }

        subtasks = self.generate_subtasks(prompt, depth)
        
        result = {
            "prompt": prompt,
            "subtasks": subtasks,
            "count": len(subtasks),
            "ambiguous": self.is_ambiguous(prompt),
            "timestamp": str(datetime.now()),
            "mode": getattr(self, "_last_gen_mode", "fallback"),
            "model": self.model if getattr(self, "_last_gen_mode", "") == "ai" else None,
        }
        if source:
            result["source"] = source
        
        if save_log:
            self.save_log(prompt, subtasks, source=source, requested_depth=depth)
        
        return result


# Example usage
if __name__ == "__main__":
    # Test with fallback mode
    fractalmind = FractalMind()
    
    test_prompt = "I'm not sure how to prepare for an AI job interview."
    result = fractalmind.process_task(test_prompt)
    
    print(f"Prompt: {result['prompt']}")
    print(f"Ambiguous: {result['ambiguous']}")
    print(f"Subtasks ({result['count']}):")
    for i, subtask in enumerate(result['subtasks'], 1):
        print(f"  {i}. {subtask}")


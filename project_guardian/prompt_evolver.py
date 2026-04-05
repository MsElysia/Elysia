# project_guardian/prompt_evolver.py
# PromptEvolver: Evolve prompts by using the AI API to improve them
# Uses the AI API to suggest better prompts based on prompt→response→outcome history

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from threading import Lock

try:
    from .ask_ai import AskAI, AIProvider
except ImportError:
    try:
        from ask_ai import AskAI, AIProvider
    except ImportError:
        AskAI = None
        AIProvider = None

logger = logging.getLogger(__name__)


@dataclass
class PromptRecord:
    """A logged prompt–response–outcome for evolution."""
    record_id: str
    task_type: str  # e.g., "dream_insight", "code_gen", "persona", "conversation"
    prompt: str
    system_prompt: Optional[str] = None
    response: str = ""
    score: float = 0.5
    feedback: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "task_type": self.task_type,
            "prompt": self.prompt[:2000],
            "system_prompt": self.system_prompt[:1000] if self.system_prompt else None,
            "response": self.response[:2000],
            "score": self.score,
            "feedback": self.feedback,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class EvolvedPrompt:
    """An evolved prompt variant with performance history."""
    prompt_id: str
    task_type: str
    original_prompt: str
    evolved_prompt: str
    evolution_reason: Optional[str] = None
    times_used: int = 0
    avg_score: float = 0.5
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_used_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PromptEvolver:
    """
    Evolves prompts by using the AI API to suggest improvements.
    
    - Logs prompt → response → score interactions
    - Uses AI to analyze low-scoring prompts and suggest better versions
    - Stores evolved prompts per task_type for reuse
    - Can evolve PersonaForge system prompts and task-specific prompts
    """

    EVOLUTION_SYSTEM = """You are a prompt engineering expert. Your task is to suggest an improved version of a prompt that will yield better AI responses.

Guidelines:
- Be concrete: output a ready-to-use improved prompt, not vague advice.
- Preserve the original intent and constraints.
- Add clarity, structure, or examples only where they help.
- Keep length reasonable (don't balloon the prompt).
- If the original is already good, make minor refinements only."""

    def __init__(
        self,
        storage_path: str = "data/prompt_evolver.json",
        ask_ai: Optional["AskAI"] = None,
    ):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.ask_ai = ask_ai
        self._lock = Lock()

        self.records: List[PromptRecord] = []
        self.evolved_prompts: Dict[str, List[Dict]] = {}  # task_type -> [EvolvedPrompt]
        self._load()

    def _load(self):
        """Load persisted data."""
        if not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                for r in data.get("records", [])[-500:]:
                    self.records.append(PromptRecord(
                        record_id=r.get("record_id", ""),
                        task_type=r.get("task_type", "unknown"),
                        prompt=r.get("prompt", ""),
                        system_prompt=r.get("system_prompt"),
                        response=r.get("response", ""),
                        score=float(r.get("score", 0.5)),
                        feedback=r.get("feedback"),
                        timestamp=r.get("timestamp", ""),
                        metadata=r.get("metadata", {}),
                    ))
                self.evolved_prompts = data.get("evolved_prompts", {})
            logger.debug(f"PromptEvolver loaded {len(self.records)} records")
        except Exception as e:
            logger.warning(f"PromptEvolver load error: {e}")

    def _save(self):
        """Persist data."""
        try:
            with self._lock:
                data = {
                    "records": [r.to_dict() if hasattr(r, "to_dict") else r for r in self.records[-500:]],
                    "evolved_prompts": self.evolved_prompts,
                    "updated_at": datetime.now().isoformat(),
                }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"PromptEvolver save error: {e}")

    def log_interaction(
        self,
        task_type: str,
        prompt: str,
        response: str,
        score: float = 0.5,
        system_prompt: Optional[str] = None,
        feedback: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Log a prompt–response–outcome for later evolution.
        
        Returns:
            record_id
        """
        import uuid
        record_id = f"prompt_{uuid.uuid4().hex[:12]}"
        record = PromptRecord(
            record_id=record_id,
            task_type=task_type,
            prompt=prompt,
            system_prompt=system_prompt,
            response=response,
            score=score,
            feedback=feedback,
            metadata=metadata or {},
        )
        with self._lock:
            self.records.append(record)
        self._save()
        return record_id

    def evolve_prompt(
        self,
        original_prompt: str,
        response: str,
        score: float,
        task_type: str = "general",
        feedback: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Optional[str]:
        """
        Use the AI API to suggest an improved prompt.
        
        Returns:
            Evolved prompt string, or None if evolution failed
        """
        if not self.ask_ai:
            logger.debug("PromptEvolver: no AskAI, skipping evolution")
            return None

        hardening_ctx = ""
        hints = getattr(self, "_adversarial_hardening_hints", [])
        if hints:
            hardening_ctx = "\n\nAdversarial hardening context (address these failure patterns in the improved prompt):\n" + "\n".join(f"- {h.get('summary', '')[:150]}" for h in hints[-3:])
        evolution_request = f"""Original prompt:
---
{original_prompt}
---

Response received:
---
{response[:1500]}
---

Outcome: score {score:.2f}/1.0{f' - {feedback}' if feedback else ''}
{f'System prompt used: {system_prompt[:500]}' if system_prompt else ''}
{hardening_ctx}

Provide ONLY the improved prompt text, no preamble. Output the new prompt that would likely yield better results."""

        try:
            result = self.ask_ai.ask(
                prompt=evolution_request,
                system_prompt=self.EVOLUTION_SYSTEM,
                temperature=0.4,
                max_tokens=1500,
                fallback=True,
            )
            if result.success and result.content:
                evolved = result.content.strip()
                evolved = self._strip_markdown_blocks(evolved)
                self._store_evolved(task_type, original_prompt, evolved, f"Score was {score:.2f}")
                return evolved
        except Exception as e:
            logger.warning(f"PromptEvolver evolution failed: {e}")
        return None

    def _strip_markdown_blocks(self, text: str) -> str:
        """Remove ``` blocks if AI wrapped output."""
        if text.startswith("```"):
            lines = text.split("\n")
            out = []
            in_block = False
            for line in lines:
                if line.strip().startswith("```"):
                    in_block = not in_block
                    continue
                if in_block or (out and not in_block):
                    out.append(line)
                elif not in_block and not out:
                    out.append(line)
            return "\n".join(out) if out else text
        return text

    def _store_evolved(
        self,
        task_type: str,
        original: str,
        evolved: str,
        reason: Optional[str] = None,
    ):
        import uuid
        pid = f"evolved_{uuid.uuid4().hex[:8]}"
        entry = {
            "prompt_id": pid,
            "task_type": task_type,
            "original_prompt": original[:1000],
            "evolved_prompt": evolved,
            "evolution_reason": reason,
            "times_used": 0,
            "avg_score": 0.5,
            "created_at": datetime.now().isoformat(),
            "last_used_at": None,
        }
        with self._lock:
            if task_type not in self.evolved_prompts:
                self.evolved_prompts[task_type] = []
            self.evolved_prompts[task_type].append(entry)
            # Keep last 20 per task type
            self.evolved_prompts[task_type] = self.evolved_prompts[task_type][-20:]
        self._save()
        logger.info(f"PromptEvolver stored evolved prompt for task_type={task_type}")

    def get_evolved_prompt(self, task_type: str) -> Optional[str]:
        """
        Get the best evolved prompt for a task type (highest avg_score).
        
        Returns:
            Evolved prompt string or None
        """
        with self._lock:
            entries = self.evolved_prompts.get(task_type, [])
        if not entries:
            return None
        best = max(entries, key=lambda e: (e.get("times_used", 0) > 0 and e.get("avg_score", 0) or 0))
        return best.get("evolved_prompt")

    def evolve_system_prompt(
        self,
        current_system_prompt: str,
        persona_name: Optional[str] = None,
        sample_responses: Optional[List[Tuple[str, str, float]]] = None,
    ) -> Optional[str]:
        """
        Use AI to evolve a PersonaForge-style system prompt.
        
        Args:
            current_system_prompt: Current system prompt
            persona_name: Optional persona name for context
            sample_responses: Optional [(prompt, response, score), ...] for context
            
        Returns:
            Evolved system prompt or None
        """
        if not self.ask_ai:
            return None

        context = ""
        if sample_responses:
            context = "\n\nSample interactions (prompt → response, score):\n"
            for p, r, s in sample_responses[:5]:
                context += f"- User: {p[:200]}... -> Score: {s:.2f}\n"
                context += f"  Response: {r[:150]}...\n"

        evolution_request = f"""Current system prompt:
---
{current_system_prompt}
---
{f'Persona: {persona_name}' if persona_name else ''}
{context}

Suggest an improved system prompt. Output ONLY the new system prompt text."""

        try:
            result = self.ask_ai.ask(
                prompt=evolution_request,
                system_prompt=self.EVOLUTION_SYSTEM,
                temperature=0.3,
                max_tokens=800,
                fallback=True,
            )
            if result.success and result.content:
                evolved = result.content.strip()
                evolved = self._strip_markdown_blocks(evolved)
                return evolved
        except Exception as e:
            logger.warning(f"PromptEvolver system prompt evolution failed: {e}")
        return None

    def run_evolution_pass(self, min_records: int = 5, score_threshold: float = 0.5) -> int:
        """
        Run evolution on recent low-scoring records.
        
        Returns:
            Number of prompts evolved
        """
        with self._lock:
            low_scoring = [r for r in self.records if r.score < score_threshold]
            low_scoring = low_scoring[-50:]  # Last 50
        if len(low_scoring) < min_records:
            logger.debug("PromptEvolver: not enough low-scoring records for evolution pass")
            return 0

        evolved_count = 0
        by_task: Dict[str, List[PromptRecord]] = {}
        for r in low_scoring:
            by_task.setdefault(r.task_type, []).append(r)

        for task_type, recs in by_task.items():
            if len(recs) >= 2:  # At least 2 low-scoring for this task
                rec = recs[-1]  # Most recent
                new_prompt = self.evolve_prompt(
                    original_prompt=rec.prompt,
                    response=rec.response,
                    score=rec.score,
                    task_type=task_type,
                    feedback=rec.feedback,
                    system_prompt=rec.system_prompt,
                )
                if new_prompt:
                    evolved_count += 1

        return evolved_count

    def get_stats(self) -> Dict[str, Any]:
        """Get evolution statistics."""
        with self._lock:
            total_evolved = sum(len(v) for v in self.evolved_prompts.values())
            task_types = list(self.evolved_prompts.keys())
        return {
            "total_records": len(self.records),
            "total_evolved_prompts": total_evolved,
            "task_types_with_evolved": task_types,
        }


def _load_prompt_evolver_config() -> Dict[str, Any]:
    """Load config/prompt_evolver.json if it exists."""
    try:
        cfg_path = Path(__file__).parent.parent / "config" / "prompt_evolver.json"
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"enabled": True, "interval_hours": 6, "min_records": 5}


class AutoPromptEvolutionScheduler:
    """Background scheduler that automatically runs prompt evolution periodically."""

    def __init__(
        self,
        prompt_evolver: PromptEvolver,
        interval_hours: float = 6.0,
        min_records: int = 5,
        enabled: bool = True,
    ):
        cfg = _load_prompt_evolver_config()
        self.prompt_evolver = prompt_evolver
        self.enabled = cfg.get("enabled", enabled)
        iv = cfg.get("interval_hours") or interval_hours
        self.interval_sec = max(3600, float(iv) * 3600)  # min 1 hour
        self.min_records = cfg.get("min_records", min_records)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_run: Optional[datetime] = None

    def _run_once(self) -> None:
        """Run a single evolution pass."""
        try:
            if not self.prompt_evolver.ask_ai:
                logger.debug("[AutoPromptEvolution] Skipping: no AskAI")
                return
            evolved = self.prompt_evolver.run_evolution_pass(min_records=self.min_records)
            self._last_run = datetime.now()
            if evolved > 0:
                logger.info("[AutoPromptEvolution] Pass complete: evolved %d prompts", evolved)
            else:
                logger.debug("[AutoPromptEvolution] Pass complete: nothing to evolve")
        except Exception as e:
            logger.warning("[AutoPromptEvolution] Pass failed: %s", e)

    def _loop(self) -> None:
        """Background loop."""
        while self._running:
            self._run_once()
            for _ in range(int(self.interval_sec)):
                if not self._running:
                    break
                time.sleep(1)

    def start(self) -> None:
        """Start the background scheduler."""
        if not self.enabled or not self.prompt_evolver:
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="AutoPromptEvolution",
        )
        self._thread.start()
        logger.info(
            "[AutoPromptEvolution] Started (interval=%.1fh, min_records=%d)",
            self.interval_sec / 3600,
            self.min_records,
        )

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[AutoPromptEvolution] Stopped")

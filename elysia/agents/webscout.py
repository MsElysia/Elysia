"""WebScout agent wrapper for Elysia-WebScout integration."""

from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..core.proposal_system import ProposalSystem
from ..events import EventBus

logger = logging.getLogger(__name__)


class WebScoutAgent:
    """Wrapper for Elysia-WebScout agent that creates proposals."""

    def __init__(
        self,
        proposals_root: Path,
        proposal_system: ProposalSystem,
        event_bus: Optional[EventBus] = None,
        require_api_keys: bool = False,
        repo_root: Optional[Path] = None,
    ):
        self.proposals_root = Path(proposals_root)
        self.repo_root = Path(repo_root or Path.cwd()).resolve()
        self.proposal_system = proposal_system
        self.event_bus = event_bus
        self.require_api_keys = require_api_keys

        self._running = False
        self._background_thread: Optional[threading.Thread] = None
        self._webscout_instance: Optional[Any] = None

        # Try to import the actual WebScout implementation
        self._init_webscout()

    def _init_webscout(self):
        """Initialize the WebScout agent instance."""
        try:
            # Try importing from project_guardian
            from project_guardian.webscout_agent import ElysiaWebScout

            self._webscout_instance = ElysiaWebScout(
                proposals_root=self.proposals_root,
                require_api_keys=self.require_api_keys,
            )
            logger.info("WebScout agent initialized")
            if self.event_bus:
                self.event_bus.emit("webscout", "initialized", {})
        except ImportError:
            logger.warning("ElysiaWebScout not available - WebScout functionality disabled")
            self._webscout_instance = None
        except Exception as e:
            logger.error(f"Failed to initialize WebScout: {e}")
            self._webscout_instance = None

    def _slugify_topic(self, value: str) -> str:
        """Create a proposal-safe topic slug."""
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug[:80] or "research-topic"

    def _patterns_from_sources(self, sources: Iterable[Any], limit: int = 8) -> List[str]:
        patterns: List[str] = []
        for source in sources:
            extracted = getattr(source, "extracted_patterns", None)
            if isinstance(extracted, list):
                for item in extracted:
                    text = str(item).strip()
                    if text and text not in patterns:
                        patterns.append(text)
                        if len(patterns) >= limit:
                            return patterns
        return patterns

    def _build_architecture_doc(
        self,
        *,
        proposal_id: str,
        topic: str,
        domain: str,
        summary: str,
        sources: List[Any],
    ) -> str:
        """Build a concrete design document from WebScout research artifacts."""
        patterns = self._patterns_from_sources(sources)
        source_lines = []
        for source in sources[:5]:
            title = str(getattr(source, "title", "") or "Research source").strip()
            url = str(getattr(source, "url", "") or "").strip()
            relevance = str(getattr(source, "relevance", "") or "unknown").strip()
            source_lines.append(f"- {title} ({relevance})" + (f": {url}" if url else ""))

        pattern_lines = [f"- {pattern}" for pattern in patterns] or [
            "- Preserve the current proposal lifecycle: research, design, proposal, approval, implementation.",
            "- Keep network and file-writing behavior routed through existing guarded components.",
        ]
        sources_section = "\n".join(source_lines) if source_lines else "- No external sources were available; use local simulated research as the first draft."

        return (
            f"# Architecture Design\n\n"
            f"**Proposal**: {proposal_id}\n"
            f"**Topic**: {topic}\n"
            f"**Domain**: {domain}\n\n"
            f"## Research Basis\n\n"
            f"{summary.strip()}\n\n"
            f"## Design Direction\n\n"
            f"The implementation should convert the research findings into a small, reviewable change that fits the existing Elysia proposal workflow. "
            f"Favor local integrations already present in the codebase before introducing new services or broad abstractions.\n\n"
            f"## Patterns To Carry Forward\n\n"
            f"{chr(10).join(pattern_lines)}\n\n"
            f"## Source Notes\n\n"
            f"{sources_section}\n"
        )

    def _build_integration_doc(self, *, proposal_id: str, topic: str, domain: str) -> str:
        """Describe where this proposal plugs into the current runtime."""
        return (
            f"# Integration Design\n\n"
            f"**Proposal**: {proposal_id}\n\n"
            f"## Runtime Touchpoints\n\n"
            f"- Proposal domain: `{domain}`\n"
            f"- Research entrypoint: `elysia.agents.webscout.WebScoutAgent.research_topic()`\n"
            f"- Proposal storage: `{self.proposals_root}`\n"
            f"- Approval path: `ProposalSystem.approve_proposal()` before implementation work is applied\n\n"
            f"## Expected Flow\n\n"
            f"1. WebScout creates this proposal package for `{topic}`.\n"
            f"2. The proposal watcher or caller reviews the generated research, design, and TODOs.\n"
            f"3. An approver transitions the proposal to `approved`.\n"
            f"4. The implementer consumes the TODOs and applies concrete code changes with tests.\n\n"
            f"## Safety Notes\n\n"
            f"Keep irreversible repository changes behind the existing approval and implementation gates. "
            f"Network research should continue to use the configured WebReader/search adapters when available.\n"
        )

    def _build_implementation_todos(self, *, topic: str, sources: List[Any]) -> List[Dict[str, str]]:
        """Create implementation TODOs that are specific enough for the implementer to consume."""
        patterns = self._patterns_from_sources(sources, limit=4)
        pattern_note = "; ".join(patterns) if patterns else "Use the generated research summary as the source of truth."
        return [
            {
                "task": f"Review research findings for {topic}",
                "priority": "high",
                "notes": pattern_note,
            },
            {
                "task": "Identify the smallest code path needed for the proposal",
                "priority": "high",
                "notes": "Map the proposal to existing modules before adding new abstractions.",
            },
            {
                "task": "Implement the approved change with guarded file edits",
                "priority": "medium",
                "notes": "Keep changes scoped and route risky behavior through existing trust/review gates.",
            },
            {
                "task": "Add or update focused tests",
                "priority": "medium",
                "notes": "Cover the user-visible behavior and the proposal lifecycle transition.",
            },
        ]

    def _proposal_relative_path(self, proposal_id: str, *parts: str) -> Optional[str]:
        """Return a repo-relative proposal artifact path when the proposal root is inside repo_root."""
        target_path = (self.proposals_root / proposal_id).joinpath(*parts).resolve()
        try:
            return target_path.relative_to(self.repo_root).as_posix()
        except ValueError:
            logger.warning(
                "Cannot build executable plan for %s because proposals root is outside repo root %s",
                proposal_id,
                self.repo_root,
            )
            return None

    def _sanitize_code_fence_content(self, value: str) -> str:
        """Prevent nested fences from breaking generated implementation plans."""
        return value.replace("```", "~~~").strip()

    def _build_generated_plan_brief(
        self,
        *,
        proposal_id: str,
        topic: str,
        domain: str,
        summary: str,
        sources: List[Any],
    ) -> str:
        """Build the proposal-local artifact that the generated plan will create."""
        patterns = self._patterns_from_sources(sources, limit=8)
        pattern_lines = "\n".join(f"- {pattern}" for pattern in patterns) or "- No extracted patterns were available."

        source_lines = []
        for source in sources[:5]:
            title = str(getattr(source, "title", "") or "Research source").strip()
            url = str(getattr(source, "url", "") or "").strip()
            relevance = str(getattr(source, "relevance", "") or "unknown").strip()
            source_lines.append(f"- {title} ({relevance})" + (f": {url}" if url else ""))
        sources_section = "\n".join(source_lines) if source_lines else "- No sources were captured."

        return (
            f"# Generated Implementation Brief\n\n"
            f"**Proposal**: {proposal_id}\n"
            f"**Topic**: {topic}\n"
            f"**Domain**: {domain}\n\n"
            f"## Boundary\n\n"
            f"This brief was generated automatically from WebScout research. It is a conservative proposal-local artifact, not an application-code edit. "
            f"Use it to review the research and produce a caller-supplied implementation plan with exact file replacements when code changes are ready.\n\n"
            f"## Research Summary\n\n"
            f"{summary.strip() or 'No research summary was available.'}\n\n"
            f"## Extracted Patterns\n\n"
            f"{pattern_lines}\n\n"
            f"## Candidate Work Items\n\n"
            f"- Map the research findings to existing modules before editing code.\n"
            f"- Identify exact target files and full replacement content for any source changes.\n"
            f"- Add focused tests for the approved behavior.\n"
            f"- Run implementation through the approval and implementer gates.\n\n"
            f"## Source Notes\n\n"
            f"{sources_section}\n"
        )

    def _build_generated_implementation_plan(
        self,
        *,
        proposal_id: str,
        topic: str,
        domain: str,
        summary: str,
        sources: List[Any],
    ) -> Optional[str]:
        """Create a conservative executable plan when no caller-supplied patch plan exists."""
        target_path = self._proposal_relative_path(proposal_id, "implementation", "generated_plan.md")
        if not target_path:
            return None

        brief = self._sanitize_code_fence_content(
            self._build_generated_plan_brief(
                proposal_id=proposal_id,
                topic=topic,
                domain=domain,
                summary=summary,
                sources=sources,
            )
        )
        return (
            "# Implementation Plan\n\n"
            "This plan was generated automatically from WebScout research. It creates a proposal-local implementation brief so the approved proposal has a concrete, reviewable artifact before any application-code files are changed.\n\n"
            f"## Step 1: Create file {target_path}\n\n"
            "Create the generated implementation brief for reviewers and later code-specific planning.\n\n"
            "```markdown\n"
            f"{brief}\n"
            "```\n"
        )

    def _write_implementation_plan(self, *, proposal_id: str, implementation_plan: Optional[str]) -> Optional[Path]:
        """Write an explicit executable implementation plan when a caller provides one."""
        if not implementation_plan or not implementation_plan.strip():
            return None

        proposal_path = self.proposals_root / proposal_id
        plan_path = proposal_path / "design" / "implementation_plan.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(implementation_plan.strip() + "\n", encoding="utf-8")
        return plan_path

    def start_background_loop(self):
        """Start WebScout background processing loop."""
        if self._running:
            logger.warning("WebScout already running")
            return

        if not self._webscout_instance:
            logger.warning("WebScout not available, cannot start background loop")
            return

        self._running = True

        def _background_loop():
            """Background loop for WebScout processing."""
            logger.info("WebScout background loop started")
            while self._running:
                try:
                    # Background queue integration can be added here when a scheduler owns research requests.
                    time.sleep(30)  # Check every 30 seconds

                    if self.event_bus:
                        self.event_bus.emit("webscout", "heartbeat", {"status": "running"})
                except Exception as e:
                    logger.exception(f"Error in WebScout background loop: {e}")
                    time.sleep(5)

        self._background_thread = threading.Thread(target=_background_loop, daemon=True)
        self._background_thread.start()

        if self.event_bus:
            self.event_bus.emit("webscout", "started", {})

    def stop(self):
        """Stop WebScout agent."""
        if not self._running:
            return

        logger.info("Stopping WebScout agent...")
        self._running = False

        if self._background_thread:
            self._background_thread.join(timeout=2)

        if self.event_bus:
            self.event_bus.emit("webscout", "stopped", {})

    def create_proposal(
        self, title: str, description: str, domain: str = "elysia_core", **kwargs
    ) -> Optional[str]:
        """
        Create a new proposal via WebScout.

        Returns proposal_id if successful, None otherwise.
        """
        if not self._webscout_instance:
            logger.error("WebScout not available")
            return None

        try:
            topic = str(kwargs.get("topic") or self._slugify_topic(title)).strip()
            tags = kwargs.get("tags")
            check_duplicates = bool(kwargs.get("check_duplicates", True))
            result = self._webscout_instance.create_proposal(
                task_description=description,
                topic=topic,
                domain=domain,
                tags=tags,
                check_duplicates=check_duplicates,
            )
            proposal_id = result.get("proposal_id") if isinstance(result, dict) else None
            if not proposal_id:
                raise RuntimeError("WebScout did not return a proposal_id")

            if self.event_bus:
                self.event_bus.emit(
                    "webscout",
                    "proposal_created",
                    {
                        "proposal_id": proposal_id,
                        "title": title,
                        "domain": domain,
                        "similar_proposals": result.get("similar_proposals", []) if isinstance(result, dict) else [],
                    },
                )
            logger.info(f"WebScout proposal created: {proposal_id}")
            return str(proposal_id)
        except Exception as e:
            logger.error(f"Failed to create proposal via WebScout: {e}")
            return None

    def research_topic(
        self,
        topic: str,
        domain: str = "elysia_core",
        *,
        max_sources: int = 5,
        tags: Optional[List[str]] = None,
        check_duplicates: bool = True,
        implementation_plan: Optional[str] = None,
        auto_generate_implementation_plan: bool = True,
    ) -> Dict[str, Any]:
        """
        Request WebScout to research a topic and create a proposal.

        Returns a dict with status and proposal_id if created.
        """
        if not self._webscout_instance:
            return {"status": "error", "message": "WebScout not available"}

        try:
            if self.event_bus:
                self.event_bus.emit(
                    "webscout",
                    "research_started",
                    {"topic": topic, "domain": domain},
                )

            topic_slug = self._slugify_topic(topic)
            task_description = f"Research and propose an implementation plan for: {topic}"
            creation = self._webscout_instance.create_proposal(
                task_description=task_description,
                topic=topic_slug,
                domain=domain,
                tags=tags or [domain, topic_slug],
                check_duplicates=check_duplicates,
            )
            proposal_id = creation.get("proposal_id") if isinstance(creation, dict) else None
            if not proposal_id:
                raise RuntimeError("WebScout did not return a proposal_id")

            sources, summary = self._webscout_instance.conduct_web_research(topic, max_sources=max_sources)
            source_list = list(sources or [])
            self._webscout_instance.add_research(proposal_id, source_list, summary or "")

            architecture = self._build_architecture_doc(
                proposal_id=proposal_id,
                topic=topic,
                domain=domain,
                summary=summary or "",
                sources=source_list,
            )
            integration = self._build_integration_doc(proposal_id=proposal_id, topic=topic, domain=domain)
            self._webscout_instance.add_design(proposal_id, architecture, integration)
            implementation_plan_source = "provided" if implementation_plan and implementation_plan.strip() else None
            if implementation_plan_source is None and auto_generate_implementation_plan:
                implementation_plan = self._build_generated_implementation_plan(
                    proposal_id=proposal_id,
                    topic=topic,
                    domain=domain,
                    summary=summary or "",
                    sources=source_list,
                )
                if implementation_plan:
                    implementation_plan_source = "generated"

            implementation_plan_path = self._write_implementation_plan(
                proposal_id=proposal_id,
                implementation_plan=implementation_plan,
            )

            todos = self._build_implementation_todos(topic=topic, sources=source_list)
            self._webscout_instance.add_implementation(
                proposal_id,
                todos,
                tests=(
                    "# Test Plan\n\n"
                    "- Validate the proposal metadata loads through `ProposalSystem.get_proposal()`.\n"
                    "- Validate generated research, design, and implementation artifacts exist.\n"
                    "- Add behavior-specific tests when the approved implementation is applied.\n"
                ),
            )

            if implementation_plan_path and self.event_bus:
                self.event_bus.emit(
                    "webscout",
                    "implementation_plan_written",
                    {
                        "proposal_id": proposal_id,
                        "path": str(implementation_plan_path),
                        "source": implementation_plan_source,
                    },
                )

            if self.event_bus:
                self.event_bus.emit(
                    "webscout",
                    "research_completed",
                    {
                        "proposal_id": proposal_id,
                        "topic": topic,
                        "domain": domain,
                        "source_count": len(source_list),
                    },
                )

            proposal_path = self.proposals_root / proposal_id
            artifacts = {
                "research_summary": str(proposal_path / "research" / "summary.md"),
                "architecture": str(proposal_path / "design" / "architecture.md"),
                "integration": str(proposal_path / "design" / "integration.md"),
                "todos": str(proposal_path / "implementation" / "todos.md"),
            }
            if implementation_plan_path:
                artifacts["implementation_plan"] = str(implementation_plan_path)

            return {
                "status": "proposal",
                "proposal_id": proposal_id,
                "proposal_path": str(proposal_path),
                "topic": topic,
                "domain": domain,
                "source_count": len(source_list),
                "similar_proposals": creation.get("similar_proposals", []) if isinstance(creation, dict) else [],
                "implementation_plan_source": implementation_plan_source or "none",
                "artifacts": artifacts,
                "message": "Research proposal package created",
            }
        except Exception as e:
            logger.error(f"Failed to start research: {e}")
            if self.event_bus:
                self.event_bus.emit(
                    "webscout",
                    "research_failed",
                    {"topic": topic, "error": str(e)},
                )
            return {"status": "error", "message": str(e)}


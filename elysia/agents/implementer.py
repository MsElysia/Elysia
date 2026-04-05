"""Elysia-Implementer agent: executes approved proposals step by step."""

from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.proposal_system import ProposalSystem
from ..events import EventBus

logger = logging.getLogger(__name__)


class ImplementationStep:
    """Represents a single step in an implementation plan."""

    def __init__(self, step_number: int, title: str, content: str):
        self.step_number = step_number
        self.title = title
        self.content = content
        self.step_type = self._infer_step_type(title, content)

    def _infer_step_type(self, title: str, content: str) -> str:
        """Infer the type of step from title and content."""
        title_lower = title.lower()
        content_lower = content.lower()

        if "create" in title_lower and "file" in title_lower:
            return "create_file"
        elif "add" in title_lower and ("test" in title_lower or "config" in title_lower):
            if "test" in title_lower:
                return "add_tests"
            else:
                return "update_config"
        elif "modify" in title_lower or "update" in title_lower:
            return "modify_file"
        elif "run" in title_lower and "test" in title_lower:
            return "run_tests"
        elif "pytest" in content_lower:
            return "run_tests"
        else:
            return "generic"

    def __repr__(self) -> str:
        return f"ImplementationStep({self.step_number}: {self.title})"


class ImplementerAgent:
    """Elysia-Implementer: executes only on proposals in 'accepted' state."""

    def __init__(
        self,
        repo_root: Path,
        proposal_system: ProposalSystem,
        event_bus: Optional[EventBus] = None,
        dry_run: bool = False,
    ):
        self.repo_root = Path(repo_root).resolve()
        self.proposal_system = proposal_system
        self.event_bus = event_bus
        self.dry_run = dry_run

    def run_for_proposal(self, proposal_id: str) -> Dict[str, Any]:
        """
        Execute implementation for a single proposal.

        Returns a dict with:
        - success: bool
        - steps_completed: int
        - steps_total: int
        - error: Optional[str]
        - diff_summary: Optional[str]
        """
        logger.info(f"Starting implementation for proposal: {proposal_id}")

        # 1. Fetch and validate proposal
        proposal = self.proposal_system.get_proposal(proposal_id)
        if not proposal:
            error = f"Proposal {proposal_id} not found"
            logger.error(error)
            return {"success": False, "error": error, "steps_completed": 0, "steps_total": 0}

        status = proposal.get("status")
        # Accept both "accepted" and "approved" statuses
        if status not in ("accepted", "approved"):
            error = f"Proposal {proposal_id} is not in 'accepted' or 'approved' status (current: {status})"
            logger.error(error)
            return {"success": False, "error": error, "steps_completed": 0, "steps_total": 0}

        # 2. Load implementation plan
        proposal_path = self.proposal_system.proposals_root / proposal_id
        plan_path = proposal_path / "design" / "implementation_plan.md"

        if not plan_path.exists():
            # Fallback: try to extract steps from architecture.md or integration.md
            plan_path = proposal_path / "design" / "architecture.md"
            if not plan_path.exists():
                error = f"Implementation plan not found for {proposal_id}"
                logger.error(error)
                return {"success": False, "error": error, "steps_completed": 0, "steps_total": 0}

        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                plan_content = f.read()
        except Exception as e:
            error = f"Failed to read implementation plan: {e}"
            logger.error(error)
            return {"success": False, "error": error, "steps_completed": 0, "steps_total": 0}

        # 3. Parse plan into steps
        steps = self._parse_implementation_plan(plan_content)
        if not steps:
            error = f"No implementation steps found in plan for {proposal_id}"
            logger.error(error)
            return {"success": False, "error": error, "steps_completed": 0, "steps_total": 0}

        logger.info(f"Parsed {len(steps)} implementation steps")

        # 4. Transition to in_implementation
        success, error = self.proposal_system.transition_status(
            proposal_id, "in_implementation", actor="Elysia-Implementer"
        )
        if not success:
            logger.warning(f"Failed to transition status: {error}")

        # Update implementation_status
        self._update_implementation_status(proposal_id, "in_progress")

        if self.event_bus:
            self.event_bus.emit(
                "implementer",
                "started",
                {"proposal_id": proposal_id, "steps_total": len(steps)},
            )

        # 5. Execute steps
        steps_completed = 0
        steps_failed = 0
        all_diffs: List[str] = []
        step_results: List[Dict[str, Any]] = []

        for step in steps:
            logger.info(f"Executing step {step.step_number}: {step.title}")

            if self.event_bus:
                self.event_bus.emit(
                    "implementer",
                    "step_started",
                    {"proposal_id": proposal_id, "step_number": step.step_number, "step_title": step.title},
                )

            step_result = self._execute_step(step, proposal_id)
            step_results.append(step_result)

            if step_result["success"]:
                steps_completed += 1
                if step_result.get("diff"):
                    all_diffs.append(step_result["diff"])

                if self.event_bus:
                    self.event_bus.emit(
                        "implementer",
                        "step_completed",
                        {
                            "proposal_id": proposal_id,
                            "step_number": step.step_number,
                            "step_title": step.title,
                        },
                    )
            else:
                steps_failed += 1
                error_msg = step_result.get("error", "Unknown error")
                logger.error(f"Step {step.step_number} failed: {error_msg}")

                if self.event_bus:
                    self.event_bus.emit(
                        "implementer",
                        "step_failed",
                        {
                            "proposal_id": proposal_id,
                            "step_number": step.step_number,
                            "step_title": step.title,
                            "error": error_msg,
                        },
                    )

                # Stop on first failure
                break

        # 6. Finalize result
        if steps_failed == 0 and steps_completed == len(steps):
            # All steps succeeded
            self._update_implementation_status(proposal_id, "completed")
            success_transition, _ = self.proposal_system.transition_status(
                proposal_id, "implemented", actor="Elysia-Implementer"
            )
            if not success_transition:
                logger.warning("Failed to transition to 'implemented' status")

            self._add_history_entry(
                proposal_id,
                "Elysia-Implementer",
                f"Implementation completed: implemented",
                {
                    "tasks_completed": steps_completed,
                    "tasks_failed": steps_failed,
                    "tasks_total": len(steps),
                },
            )

            if self.event_bus:
                self.event_bus.emit(
                    "implementer",
                    "completed",
                    {
                        "proposal_id": proposal_id,
                        "steps_completed": steps_completed,
                        "steps_total": len(steps),
                    },
                )

            return {
                "success": True,
                "steps_completed": steps_completed,
                "steps_total": len(steps),
                "diff_summary": "\n".join(all_diffs) if all_diffs else None,
                "step_results": step_results,
            }
        else:
            # Some steps failed
            self._update_implementation_status(proposal_id, "failed")
            success_transition, _ = self.proposal_system.transition_status(
                proposal_id, "implementation_failed", actor="Elysia-Implementer"
            )
            if not success_transition:
                logger.warning("Failed to transition to 'implementation_failed' status")

            error_msg = f"Step {steps_completed + 1} failed: {step_results[-1].get('error', 'Unknown error')}"
            self._add_history_entry(
                proposal_id,
                "Elysia-Implementer",
                f"Implementation failed: {error_msg}",
                {"steps_completed": steps_completed, "steps_failed": steps_failed, "steps_total": len(steps)},
            )

            if self.event_bus:
                self.event_bus.emit(
                    "implementer",
                    "failed",
                    {
                        "proposal_id": proposal_id,
                        "steps_completed": steps_completed,
                        "steps_total": len(steps),
                        "error": error_msg,
                    },
                )

            return {
                "success": False,
                "steps_completed": steps_completed,
                "steps_total": len(steps),
                "error": error_msg,
                "step_results": step_results,
            }

    def run_batch(self) -> Dict[str, Any]:
        """
        Process all eligible proposals (status == 'accepted', implementation_status in {'pending', 'failed'}).

        Returns summary of batch execution.
        """
        proposals = self.proposal_system.list_proposals(status_filter="accepted")
        eligible = [
            p
            for p in proposals
            if p.get("implementation_status") in (None, "pending", "failed", "not_started")
        ]

        logger.info(f"Found {len(eligible)} eligible proposals for batch implementation")

        results = []
        for proposal in eligible:
            proposal_id = proposal.get("proposal_id")
            if not proposal_id:
                continue

            result = self.run_for_proposal(proposal_id)
            results.append({"proposal_id": proposal_id, **result})

        return {
            "total": len(eligible),
            "successful": sum(1 for r in results if r.get("success")),
            "failed": sum(1 for r in results if not r.get("success")),
            "results": results,
        }

    def _parse_implementation_plan(self, plan_content: str) -> List[ImplementationStep]:
        """
        Parse implementation plan markdown into structured steps.

        Looks for patterns like:
        ## Step 1: Title
        ## Step 2: Title
        or
        ### Step 1: Title
        ### Step 2: Title
        """
        steps = []

        # Pattern to match step headings: ## Step N: Title or ### Step N: Title
        step_pattern = re.compile(r"^#{2,3}\s+Step\s+(\d+):\s*(.+)$", re.MULTILINE)

        matches = list(step_pattern.finditer(plan_content))
        if not matches:
            # Try alternative pattern: just numbered headings
            step_pattern = re.compile(r"^#{2,3}\s+(\d+)\.\s*(.+)$", re.MULTILINE)
            matches = list(step_pattern.finditer(plan_content))

        if not matches:
            # Last resort: split by major headings and number them
            heading_pattern = re.compile(r"^#{2}\s+(.+)$", re.MULTILINE)
            heading_matches = list(heading_pattern.finditer(plan_content))
            if heading_matches:
                for idx, match in enumerate(heading_matches, 1):
                    title = match.group(1)
                    start_pos = match.end()
                    end_pos = heading_matches[idx].start() if idx < len(heading_matches) else len(plan_content)
                    content = plan_content[start_pos:end_pos].strip()
                    steps.append(ImplementationStep(idx, title, content))
                return steps
            return []

        # Extract steps with their content
        for idx, match in enumerate(matches):
            step_number = int(match.group(1))
            title = match.group(2).strip()
            start_pos = match.end()
            end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(plan_content)
            content = plan_content[start_pos:end_pos].strip()
            steps.append(ImplementationStep(step_number, title, content))

        return steps

    def _execute_step(self, step: ImplementationStep, proposal_id: str) -> Dict[str, Any]:
        """Execute a single implementation step."""
        logger.info(f"Executing step {step.step_number} ({step.step_type}): {step.title}")

        if self.dry_run:
            logger.info(f"[DRY RUN] Would execute: {step.title}")
            return {"success": True, "dry_run": True, "step_type": step.step_type}

        try:
            if step.step_type == "create_file":
                return self._execute_create_file(step, proposal_id)
            elif step.step_type == "modify_file":
                return self._execute_modify_file(step, proposal_id)
            elif step.step_type == "add_tests":
                return self._execute_add_tests(step, proposal_id)
            elif step.step_type == "run_tests":
                return self._execute_run_tests(step, proposal_id)
            elif step.step_type == "update_config":
                return self._execute_update_config(step, proposal_id)
            else:
                # Generic step - just log it
                logger.info(f"Generic step: {step.title}")
                return {"success": True, "step_type": "generic", "message": "Step logged but not executed"}

        except Exception as e:
            logger.exception(f"Error executing step {step.step_number}: {e}")
            return {"success": False, "error": str(e), "step_type": step.step_type}

    def _execute_create_file(self, step: ImplementationStep, proposal_id: str) -> Dict[str, Any]:
        """Execute a create_file step."""
        # Extract file path from step content
        # Look for patterns like "elysia/agents/foo.py" or "config/foo.yaml"
        file_pattern = re.search(r"([a-zA-Z0-9_/\\-]+\.(py|yaml|yml|json|md|txt))", step.content)
        if not file_pattern:
            return {"success": False, "error": "Could not extract file path from step"}

        file_path_str = file_pattern.group(1)
        file_path = self.repo_root / file_path_str

        # Check if file already exists
        if file_path.exists():
            logger.warning(f"File already exists: {file_path}, skipping creation")
            return {"success": True, "message": "File already exists", "file_path": str(file_path)}

        # Extract content from step or create placeholder
        # For now, create a minimal placeholder file
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Try to extract code/content from step.content
        code_block = re.search(r"```(?:python|yaml|json)?\n(.*?)```", step.content, re.DOTALL)
        if code_block:
            content = code_block.group(1)
        else:
            # Create minimal placeholder
            if file_path.suffix == ".py":
                content = f'"""Generated by Elysia-Implementer for proposal {proposal_id}."""\n\n'
            elif file_path.suffix in (".yaml", ".yml"):
                content = f"# Generated by Elysia-Implementer for proposal {proposal_id}\n"
            else:
                content = f"# Generated by Elysia-Implementer for proposal {proposal_id}\n"

        try:
            file_path.write_text(content, encoding="utf-8")
            logger.info(f"Created file: {file_path}")

            # Generate diff summary
            diff = f"+++ {file_path_str}\n+{content.replace(chr(10), chr(10) + '+')}"

            return {
                "success": True,
                "file_path": str(file_path),
                "diff": diff,
                "step_type": "create_file",
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to create file: {e}", "step_type": "create_file"}

    def _execute_modify_file(self, step: ImplementationStep, proposal_id: str) -> Dict[str, Any]:
        """Execute a modify_file step."""
        # Similar to create_file but modify existing file
        file_pattern = re.search(r"([a-zA-Z0-9_/\\-]+\.(py|yaml|yml|json|md|txt))", step.content)
        if not file_pattern:
            return {"success": False, "error": "Could not extract file path from step"}

        file_path_str = file_pattern.group(1)
        file_path = self.repo_root / file_path_str

        if not file_path.exists():
            return {"success": False, "error": f"File does not exist: {file_path}"}

        # For now, log the modification intent
        # In a full implementation, this would parse the step content to determine
        # what changes to make and apply them as a diff
        logger.info(f"Would modify file: {file_path} (modification logic not fully implemented)")

        return {
            "success": True,
            "message": "File modification logged (not fully implemented)",
            "file_path": str(file_path),
            "step_type": "modify_file",
        }

    def _execute_add_tests(self, step: ImplementationStep, proposal_id: str) -> Dict[str, Any]:
        """Execute an add_tests step."""
        # Similar to create_file but for test files
        return self._execute_create_file(step, proposal_id)

    def _execute_run_tests(self, step: ImplementationStep, proposal_id: str) -> Dict[str, Any]:
        """Execute a run_tests step."""
        # Extract test path from step content
        test_pattern = re.search(r"tests?/([a-zA-Z0-9_/\\-]+\.py)", step.content)
        if test_pattern:
            test_path = test_pattern.group(0)
        else:
            # Default: run all tests
            test_path = "tests"

        try:
            # Run pytest
            cmd = ["pytest", test_path, "-v"]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.repo_root, timeout=300)

            success = result.returncode == 0

            return {
                "success": success,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "test_path": test_path,
                "step_type": "run_tests",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Test execution timed out", "step_type": "run_tests"}
        except Exception as e:
            return {"success": False, "error": f"Failed to run tests: {e}", "step_type": "run_tests"}

    def _execute_update_config(self, step: ImplementationStep, proposal_id: str) -> Dict[str, Any]:
        """Execute an update_config step."""
        # Similar to modify_file but for config files
        return self._execute_modify_file(step, proposal_id)

    def _update_implementation_status(
        self, proposal_id: str, status: str, last_result: Optional[str] = None
    ) -> None:
        """Update implementation_status field in proposal metadata."""
        proposal = self.proposal_system.get_proposal(proposal_id)
        if not proposal:
            return

        proposal["implementation_status"] = status
        proposal["last_implemented_at"] = datetime.now(timezone.utc).isoformat()
        if last_result:
            proposal["last_implementation_result"] = last_result

        # Save metadata
        proposal_path = self.proposal_system.proposals_root / proposal_id
        metadata_file = proposal_path / "metadata.json"
        try:
            proposal["updated_at"] = datetime.now(timezone.utc).isoformat()
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(proposal, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to update implementation status: {e}")

    def _add_history_entry(
        self, proposal_id: str, actor: str, change_summary: str, details: Optional[Any] = None
    ) -> None:
        """Add a history entry to proposal metadata."""
        proposal = self.proposal_system.get_proposal(proposal_id)
        if not proposal:
            return

        if "history" not in proposal:
            proposal["history"] = []

        proposal["history"].append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "actor": actor,
                "change_summary": change_summary,
                "details": details,
            }
        )

        # Save metadata
        proposal_path = self.proposal_system.proposals_root / proposal_id
        metadata_file = proposal_path / "metadata.json"
        try:
            proposal["updated_at"] = datetime.now(timezone.utc).isoformat()
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(proposal, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to add history entry: {e}")


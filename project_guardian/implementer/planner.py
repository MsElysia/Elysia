"""
Planner - Turns abstract proposals into concrete implementation plans
"""

import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

from .data_models import ImplementationPlan, ImplementationStep, Task, TaskGraph

logger = logging.getLogger(__name__)


class Planner:
    """
    Converts proposals into concrete implementation plans.
    For now, uses simple static planning. Later will use LLM for dynamic planning.
    """
    
    def __init__(self, api_manager=None):
        """
        Initialize planner.
        
        Args:
            api_manager: Optional API key manager for LLM access (for future use)
        """
        self.api_manager = api_manager
        self.has_llm = api_manager and api_manager.has_llm_access() if api_manager else False
    
    def build_plan(self, proposal: Dict[str, Any]) -> ImplementationPlan:
        """
        Build implementation plan from proposal.
        
        Args:
            proposal: Proposal metadata dict
        
        Returns:
            ImplementationPlan
        """
        proposal_id = proposal.get("proposal_id", "unknown")
        domain = proposal.get("domain", "unknown")
        design_impact = proposal.get("design_impact", {})
        
        # For now, use simple static planning based on domain
        # Later: Use LLM to interpret design documents and generate steps
        
        steps = self._generate_steps_for_domain(domain, proposal, design_impact)
        
        plan = ImplementationPlan(
            proposal_id=proposal_id,
            steps=steps,
            assumptions=self._extract_assumptions(proposal),
            risks=self._extract_risks(proposal),
            domain=domain
        )
        
        logger.info(f"Built implementation plan for {proposal_id} with {len(steps)} steps")
        return plan
    
    def build_task_graph(self, plan: ImplementationPlan) -> TaskGraph:
        """
        Convert implementation plan into executable task graph.
        
        Args:
            plan: ImplementationPlan
        
        Returns:
            TaskGraph
        """
        tasks = []
        
        for step in plan.steps:
            # Create one or more tasks per step
            task = Task(
                id=f"task-{step.id}",
                step_id=step.id,
                description=step.description,
                target_files=step.targets,
                depends_on=[f"task-{dep}" for dep in step.dependencies]
            )
            tasks.append(task)
        
        task_graph = TaskGraph(tasks=tasks)
        logger.info(f"Built task graph with {len(tasks)} tasks")
        return task_graph
    
    def _generate_steps_for_domain(self, domain: str, proposal: Dict[str, Any], 
                                   design_impact: Dict[str, Any]) -> List[ImplementationStep]:
        """
        Generate implementation steps based on domain.
        This is a simple static planner - will be replaced with LLM-based planning.
        """
        steps = []
        
        if domain == "elysia_core":
            steps = [
                ImplementationStep(
                    id="step-1",
                    description="Create new module structure",
                    type="code_add",
                    targets=["core_modules/new_module/__init__.py", "core_modules/new_module/module.py"],
                    acceptance_criteria=["Module files created", "Basic structure in place"]
                ),
                ImplementationStep(
                    id="step-2",
                    description="Add tests for new module",
                    type="test_add",
                    targets=["tests/test_new_module.py"],
                    acceptance_criteria=["Test file created", "At least 3 test cases"],
                    dependencies=["step-1"]
                ),
                ImplementationStep(
                    id="step-3",
                    description="Integrate module into Architect-Core",
                    type="code_modify",
                    targets=["core_modules/elysia_core_comprehensive/architect_core.py"],
                    acceptance_criteria=["Module registered", "Tests pass"],
                    dependencies=["step-1", "step-2"]
                )
            ]
        
        elif domain == "hestia_scraping":
            steps = [
                ImplementationStep(
                    id="step-1",
                    description="Create scraper class",
                    type="code_add",
                    targets=["hestia/scrapers/new_scraper.py"],
                    acceptance_criteria=["Scraper class created", "Basic structure in place"]
                ),
                ImplementationStep(
                    id="step-2",
                    description="Add configuration",
                    type="config_update",
                    targets=["config/scrapers.json"],
                    acceptance_criteria=["Config entry added", "Valid JSON"]
                ),
                ImplementationStep(
                    id="step-3",
                    description="Add error handling and retry logic",
                    type="code_modify",
                    targets=["hestia/scrapers/new_scraper.py"],
                    acceptance_criteria=["Retry logic implemented", "Error handling added"],
                    dependencies=["step-1"]
                )
            ]
        
        else:
            # Generic steps for unknown domains
            steps = [
                ImplementationStep(
                    id="step-1",
                    description="Implement core functionality",
                    type="code_add",
                    targets=["implementation/main.py"],
                    acceptance_criteria=["Core functionality implemented"]
                ),
                ImplementationStep(
                    id="step-2",
                    description="Add tests",
                    type="test_add",
                    targets=["tests/test_implementation.py"],
                    acceptance_criteria=["Tests created and passing"],
                    dependencies=["step-1"]
                )
            ]
        
        return steps
    
    def _extract_assumptions(self, proposal: Dict[str, Any]) -> List[str]:
        """Extract assumptions from proposal"""
        design_impact = proposal.get("design_impact", {})
        assumptions = design_impact.get("assumptions", [])
        if isinstance(assumptions, list):
            return assumptions
        return []
    
    def _extract_risks(self, proposal: Dict[str, Any]) -> List[str]:
        """Extract risks from proposal"""
        risks = []
        risk_level = proposal.get("risk_level", "medium")
        risks.append(f"Risk level: {risk_level}")
        
        design_impact = proposal.get("design_impact", {})
        if design_impact.get("breaking_changes", False):
            risks.append("Contains breaking changes")
        
        return risks


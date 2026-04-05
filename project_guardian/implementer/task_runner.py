"""
TaskRunner - Executes tasks from task graph
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

from .data_models import Task, TaskGraph, TaskResult, TaskStatus, ImplementationResult, ImplementationStatus
from .repo_adapter import RepoAdapter
from .codegen_client import CodeGenClient
from .test_runner import TestRunner

logger = logging.getLogger(__name__)


@dataclass
class Guardrails:
    """Configuration for safety guardrails"""
    halt_on_first_failure: bool = True
    max_files_per_task: int = 10
    max_tasks_per_proposal: int = 50
    require_tests_pass: bool = True
    dry_run: bool = False


class TaskRunner:
    """
    Executes tasks from a task graph.
    Handles dependencies, applies patches, runs tests.
    """
    
    def __init__(self, 
                 repo_adapter: RepoAdapter,
                 codegen_client: CodeGenClient,
                 test_runner: TestRunner,
                 guardrails: Guardrails):
        """
        Initialize task runner.
        
        Args:
            repo_adapter: Repository adapter for file operations
            codegen_client: Code generation client
            test_runner: Test runner
            guardrails: Safety guardrails
        """
        self.repo = repo_adapter
        self.codegen = codegen_client
        self.tests = test_runner
        self.guardrails = guardrails
    
    def execute(self, task_graph: TaskGraph, proposal: Dict[str, Any]) -> ImplementationResult:
        """
        Execute all tasks in the task graph.
        
        Args:
            task_graph: Graph of tasks to execute
            proposal: Proposal metadata
        
        Returns:
            ImplementationResult
        """
        proposal_id = proposal.get("proposal_id", "unknown")
        domain = proposal.get("domain")
        
        logger.info(f"Executing task graph for proposal {proposal_id}")
        
        # Get tasks in dependency order
        ordered_tasks = task_graph.topological_sort()
        
        task_results = []
        tasks_completed = 0
        tasks_failed = 0
        
        for task in ordered_tasks:
            # Check dependencies
            if not self._dependencies_passed(task, task_results):
                logger.warning(f"Task {task.id} skipped due to failed dependencies")
                result = TaskResult(
                    task_id=task.id,
                    status=TaskStatus.SKIPPED,
                    error="Dependencies failed"
                )
                task_results.append(result)
                tasks_failed += 1
                continue
            
            # Execute task
            logger.info(f"Executing task {task.id}: {task.description}")
            result = self._execute_single_task(task, proposal)
            task_results.append(result)
            
            if result.status == TaskStatus.PASSED:
                tasks_completed += 1
            else:
                tasks_failed += 1
                if self.guardrails.halt_on_first_failure:
                    logger.error(f"Task {task.id} failed, halting execution")
                    break
        
        # Determine overall status
        if tasks_failed == 0:
            status = ImplementationStatus.IMPLEMENTED
        elif tasks_completed > 0:
            status = ImplementationStatus.IMPLEMENTATION_PARTIAL
        else:
            status = ImplementationStatus.IMPLEMENTATION_FAILED
        
        # Generate diff summary
        diff_summary = self.repo.generate_diff() if not self.guardrails.dry_run else "Dry run - no changes"
        
        # Run final tests
        test_results = None
        if self.guardrails.require_tests_pass and not self.guardrails.dry_run:
            test_results = self.tests.run_tests(domain=domain)
        
        result = ImplementationResult(
            proposal_id=proposal_id,
            status=status,
            branch_name=self.repo.current_branch,
            tasks_completed=tasks_completed,
            tasks_failed=tasks_failed,
            tasks_total=len(ordered_tasks),
            task_results=task_results,
            diff_summary=diff_summary,
            test_results=test_results
        )
        
        logger.info(f"Task execution complete: {tasks_completed}/{len(ordered_tasks)} tasks passed")
        return result
    
    def _execute_single_task(self, task: Task, proposal: Dict[str, Any]) -> TaskResult:
        """
        Execute a single task.
        
        Args:
            task: Task to execute
            proposal: Proposal metadata
        
        Returns:
            TaskResult
        """
        try:
            # Get current file contents
            current_files = self.repo.get_relevant_files(
                task.description,
                task.target_files
            )
            
            # Get step info from proposal (simplified - in real implementation, would get from plan)
            step_description = task.description
            acceptance_criteria = ["Code compiles", "Tests pass"]  # Simplified
            
            if self.guardrails.dry_run:
                # Dry run: just generate patches, don't apply
                patches = self.codegen.generate_patch(
                    step_description=step_description,
                    current_files=current_files,
                    target_files=task.target_files,
                    acceptance_criteria=acceptance_criteria,
                    context={"proposal": proposal}
                )
                
                return TaskResult(
                    task_id=task.id,
                    status=TaskStatus.PASSED,
                    output=f"Dry run: Would generate patches for {len(patches)} files"
                )
            
            # Generate patches
            patches = self.codegen.generate_patch(
                step_description=step_description,
                current_files=current_files,
                target_files=task.target_files,
                acceptance_criteria=acceptance_criteria,
                context={"proposal": proposal}
            )
            
            # Validate patches
            is_valid, error = self.codegen.validate_patch(patches, task.target_files)
            if not is_valid:
                return TaskResult(
                    task_id=task.id,
                    status=TaskStatus.FAILED,
                    error=error
                )
            
            # Apply patches
            files_changed = []
            for file_path, content in patches.items():
                if self.repo.apply_patch(file_path, content):
                    files_changed.append(file_path)
            
            if not files_changed:
                return TaskResult(
                    task_id=task.id,
                    status=TaskStatus.FAILED,
                    error="No files were successfully modified"
                )
            
            # Run tests if this task has a test command
            test_results = None
            if task.command and "test" in task.command.lower():
                test_results = self.tests.run_tests(specific_tests=task.target_files)
            
            # Generate diff for this task
            diff = self.repo.generate_diff()
            
            return TaskResult(
                task_id=task.id,
                status=TaskStatus.PASSED,
                output=f"Successfully modified {len(files_changed)} files",
                files_changed=files_changed,
                diff=diff,
                test_results=test_results
            )
        
        except Exception as e:
            logger.error(f"Error executing task {task.id}: {e}")
            return TaskResult(
                task_id=task.id,
                status=TaskStatus.FAILED,
                error=str(e)
            )
    
    def _dependencies_passed(self, task: Task, completed_results: list[TaskResult]) -> bool:
        """Check if all dependencies passed"""
        if not task.depends_on:
            return True
        
        completed_ids = {r.task_id for r in completed_results if r.status == TaskStatus.PASSED}
        
        for dep_id in task.depends_on:
            if dep_id not in completed_ids:
                # Check if dependency was skipped or failed
                dep_result = next((r for r in completed_results if r.task_id == dep_id), None)
                if dep_result and dep_result.status != TaskStatus.PASSED:
                    return False
        
        return True


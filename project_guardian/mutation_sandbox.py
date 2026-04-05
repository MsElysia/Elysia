# project_guardian/mutation_sandbox.py
# MutationSandbox: Isolated Test Execution
# Tests mutations in isolated environment before applying to main codebase

import logging
import subprocess
import tempfile
import shutil
import importlib.util
import sys
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
from threading import Lock
from enum import Enum
from dataclasses import dataclass
import uuid
import json

try:
    from .mutation_engine import MutationProposal, MutationStatus
    from .metacoder import MetaCoder
except ImportError:
    from mutation_engine import MutationProposal, MutationStatus
    try:
        from metacoder import MetaCoder
    except ImportError:
        MetaCoder = None

logger = logging.getLogger(__name__)


class TestResult(Enum):
    """Test execution result."""
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


@dataclass
class SandboxTestResult:
    """Result of sandbox test execution."""
    test_id: str
    mutation_id: str
    result: TestResult
    passed: bool
    execution_time: float  # seconds
    output: str
    errors: List[str]
    warnings: List[str]
    test_coverage: Optional[float] = None  # 0.0-1.0
    module_imported: bool = False
    syntax_valid: bool = False
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "test_id": self.test_id,
            "mutation_id": self.mutation_id,
            "result": self.result.value,
            "passed": self.passed,
            "execution_time": self.execution_time,
            "output": self.output,
            "errors": self.errors,
            "warnings": self.warnings,
            "test_coverage": self.test_coverage,
            "module_imported": self.module_imported,
            "syntax_valid": self.syntax_valid,
            "metadata": self.metadata
        }


class MutationSandbox:
    """
    Isolated test execution environment for mutations.
    Tests mutations in a temporary environment before applying to main codebase.
    """
    
    def __init__(
        self,
        project_root: str = ".",
        test_command: Optional[str] = None,
        timeout: int = 60,
        cleanup: bool = True,
        metacoder: Optional[MetaCoder] = None
    ):
        """
        Initialize MutationSandbox.
        
        Args:
            project_root: Root directory of project
            test_command: Command to run tests (e.g., "pytest", "python -m pytest")
            timeout: Test timeout in seconds
            cleanup: If True, cleanup sandbox after tests
            metacoder: Optional MetaCoder for code validation
        """
        self.project_root = Path(project_root)
        self.test_command = test_command or "pytest"
        self.timeout = timeout
        self.cleanup = cleanup
        self.metacoder = metacoder
        
        # Thread-safe operations
        self._lock = Lock()
        
        # Active sandboxes (mutation_id -> sandbox_path)
        self.active_sandboxes: Dict[str, Path] = {}
        
        # Test history
        self.test_history: Dict[str, SandboxTestResult] = {}
        
        # Statistics
        self.stats = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "timeouts": 0,
            "average_execution_time": 0.0
        }
    
    def create_sandbox(
        self,
        mutation_id: str,
        proposal: MutationProposal,
        include_dependencies: bool = True
    ) -> Optional[Path]:
        """
        Create isolated sandbox environment for mutation testing.
        
        Args:
            mutation_id: Mutation ID
            proposal: Mutation proposal
            include_dependencies: If True, copy dependency modules
            
        Returns:
            Path to sandbox directory or None if failed
        """
        try:
            # Create temporary directory
            sandbox_path = Path(tempfile.mkdtemp(prefix=f"mutation_sandbox_{mutation_id}_"))
            
            # Copy project structure
            target_module_path = self.project_root / proposal.target_module
            target_dir = sandbox_path / target_module_path.parent
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy target module
            if target_module_path.exists():
                shutil.copy2(target_module_path, target_dir / target_module_path.name)
            
            # Copy dependencies if requested
            if include_dependencies:
                # Copy common dependencies
                dependencies = self._find_dependencies(proposal.target_module)
                for dep in dependencies:
                    dep_path = self.project_root / dep
                    if dep_path.exists():
                        dep_dir = sandbox_path / dep_path.parent
                        dep_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(dep_path, dep_dir / dep_path.name)
            
            # Copy test files
            test_dir = self.project_root / "tests"
            if test_dir.exists():
                sandbox_tests = sandbox_path / "tests"
                shutil.copytree(test_dir, sandbox_tests, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            
            # Apply mutation to sandbox
            sandbox_target = sandbox_path / proposal.target_module
            if sandbox_target.exists():
                sandbox_target.write_text(proposal.proposed_code, encoding="utf-8")
                logger.info(f"Applied mutation to sandbox: {sandbox_target}")
            
            # Store sandbox path
            with self._lock:
                self.active_sandboxes[mutation_id] = sandbox_path
            
            logger.info(f"Created sandbox for mutation {mutation_id} at {sandbox_path}")
            return sandbox_path
            
        except Exception as e:
            logger.error(f"Failed to create sandbox for {mutation_id}: {e}", exc_info=True)
            return None
    
    def _find_dependencies(self, module_path: str) -> List[str]:
        """Find module dependencies by analyzing imports."""
        dependencies = []
        
        try:
            module_file = self.project_root / module_path
            if not module_file.exists():
                return dependencies
            
            content = module_file.read_text(encoding="utf-8")
            
            # Simple import parsing
            import re
            # Find relative imports
            relative_imports = re.findall(r'from\s+\.(\w+)\s+import', content)
            for imp in relative_imports:
                # Construct potential path
                parent_dir = module_file.parent
                dep_path = parent_dir / f"{imp}.py"
                if dep_path.exists():
                    rel_path = str(dep_path.relative_to(self.project_root))
                    if rel_path not in dependencies:
                        dependencies.append(rel_path)
            
            # Find absolute imports from project
            absolute_imports = re.findall(r'from\s+project_guardian\.(\w+)\s+import', content)
            for imp in absolute_imports:
                dep_path = self.project_root / "project_guardian" / f"{imp}.py"
                if dep_path.exists():
                    rel_path = str(dep_path.relative_to(self.project_root))
                    if rel_path not in dependencies:
                        dependencies.append(rel_path)
        
        except Exception as e:
            logger.debug(f"Error finding dependencies: {e}")
        
        return dependencies
    
    def test_mutation(
        self,
        mutation_id: str,
        proposal: MutationProposal,
        test_filter: Optional[str] = None
    ) -> SandboxTestResult:
        """
        Test mutation in isolated sandbox.
        
        Args:
            mutation_id: Mutation ID
            proposal: Mutation proposal
            test_filter: Optional test filter (e.g., "test_specific_module")
            
        Returns:
            SandboxTestResult
        """
        self.stats["total_tests"] += 1
        test_id = str(uuid.uuid4())
        start_time = datetime.now()
        
        try:
            # Create sandbox
            sandbox_path = self.create_sandbox(mutation_id, proposal)
            if not sandbox_path:
                return SandboxTestResult(
                    test_id=test_id,
                    mutation_id=mutation_id,
                    result=TestResult.ERROR,
                    passed=False,
                    execution_time=0.0,
                    output="Failed to create sandbox",
                    errors=["Sandbox creation failed"],
                    warnings=[],
                    metadata={"error": "Sandbox creation failed"}
                )
            
            # Validate syntax first
            syntax_valid = False
            if self.metacoder:
                validation = self.metacoder.validate_code_syntax(proposal.proposed_code)
                syntax_valid = validation.get("valid", False)
                if not syntax_valid:
                    return SandboxTestResult(
                        test_id=test_id,
                        mutation_id=mutation_id,
                        result=TestResult.ERROR,
                        passed=False,
                        execution_time=0.0,
                        output="Syntax validation failed",
                        errors=validation.get("errors", []),
                        warnings=[],
                        syntax_valid=False,
                        metadata={"validation": validation}
                    )
            else:
                # Basic syntax check
                try:
                    compile(proposal.proposed_code, proposal.target_module, "exec")
                    syntax_valid = True
                except SyntaxError as e:
                    return SandboxTestResult(
                        test_id=test_id,
                        mutation_id=mutation_id,
                        result=TestResult.ERROR,
                        passed=False,
                        execution_time=0.0,
                        output=f"Syntax error: {e}",
                        errors=[str(e)],
                        warnings=[],
                        syntax_valid=False
                    )
            
            # Try to import module in sandbox
            module_imported = False
            try:
                module_imported = self._test_module_import(sandbox_path, proposal.target_module)
            except Exception as e:
                logger.debug(f"Module import test failed: {e}")
            
            # Run tests in sandbox
            test_result = self._run_tests_in_sandbox(
                sandbox_path,
                test_filter=test_filter
            )
            
            # Calculate execution time
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # Update statistics
            with self._lock:
                if test_result["passed"]:
                    self.stats["passed"] += 1
                else:
                    self.stats["failed"] += 1
                
                # Update average execution time
                total_time = self.stats["average_execution_time"] * (self.stats["total_tests"] - 1)
                total_time += execution_time
                self.stats["average_execution_time"] = total_time / self.stats["total_tests"]
            
            # Create result
            result = SandboxTestResult(
                test_id=test_id,
                mutation_id=mutation_id,
                result=TestResult.PASSED if test_result["passed"] else TestResult.FAILED,
                passed=test_result["passed"],
                execution_time=execution_time,
                output=test_result.get("output", ""),
                errors=test_result.get("errors", []),
                warnings=test_result.get("warnings", []),
                module_imported=module_imported,
                syntax_valid=syntax_valid,
                metadata={
                    "sandbox_path": str(sandbox_path),
                    "test_command": self.test_command,
                    "test_filter": test_filter
                }
            )
            
            # Store result
            with self._lock:
                self.test_history[test_id] = result
            
            # Cleanup sandbox
            if self.cleanup:
                self.cleanup_sandbox(mutation_id)
            
            return result
            
        except subprocess.TimeoutExpired:
            execution_time = (datetime.now() - start_time).total_seconds()
            self.stats["timeouts"] += 1
            
            result = SandboxTestResult(
                test_id=test_id,
                mutation_id=mutation_id,
                result=TestResult.TIMEOUT,
                passed=False,
                execution_time=execution_time,
                output=f"Test timeout after {self.timeout} seconds",
                errors=[f"Timeout after {self.timeout}s"],
                warnings=[]
            )
            
            with self._lock:
                self.test_history[test_id] = result
            
            if self.cleanup:
                self.cleanup_sandbox(mutation_id)
            
            return result
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error testing mutation {mutation_id}: {e}", exc_info=True)
            self.stats["errors"] += 1
            
            result = SandboxTestResult(
                test_id=test_id,
                mutation_id=mutation_id,
                result=TestResult.ERROR,
                passed=False,
                execution_time=execution_time,
                output=f"Error: {str(e)}",
                errors=[str(e)],
                warnings=[]
            )
            
            with self._lock:
                self.test_history[test_id] = result
            
            if self.cleanup:
                self.cleanup_sandbox(mutation_id)
            
            return result
    
    def _test_module_import(self, sandbox_path: Path, module_path: str) -> bool:
        """Test if module can be imported in sandbox."""
        try:
            # Create a test script
            test_script = sandbox_path / "test_import.py"
            test_script.write_text(f"""
import sys
sys.path.insert(0, '{sandbox_path}')

try:
    # Try to import the module
    module_name = '{module_path.replace('/', '.').replace('.py', '')}'
    exec(f"import {{module_name}}")
    print("IMPORT_SUCCESS")
except Exception as e:
    print(f"IMPORT_ERROR: {{e}}")
    sys.exit(1)
""")
            
            # Run import test
            result = subprocess.run(
                ["python", str(test_script)],
                cwd=str(sandbox_path),
                capture_output=True,
                text=True,
                timeout=10
            )
            
            return "IMPORT_SUCCESS" in result.stdout
            
        except Exception as e:
            logger.debug(f"Module import test failed: {e}")
            return False
    
    def _run_tests_in_sandbox(
        self,
        sandbox_path: Path,
        test_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run tests in sandbox environment."""
        try:
            # Build test command
            cmd = self.test_command.split()
            
            # Add test filter if provided
            if test_filter:
                cmd.append(test_filter)
            
            # Run tests
            result = subprocess.run(
                cmd,
                cwd=str(sandbox_path),
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            # Parse results
            passed = result.returncode == 0
            output = result.stdout + result.stderr
            
            errors = []
            warnings = []
            
            if not passed:
                # Extract errors from output
                error_lines = [
                    line for line in output.splitlines()
                    if "ERROR" in line or "FAILED" in line or "AssertionError" in line
                ]
                errors.extend(error_lines[:10])  # Limit to first 10 errors
            
            return {
                "passed": passed,
                "output": output,
                "errors": errors,
                "warnings": warnings,
                "return_code": result.returncode
            }
            
        except subprocess.TimeoutExpired:
            raise
        except Exception as e:
            logger.error(f"Error running tests: {e}")
            return {
                "passed": False,
                "output": f"Test execution error: {e}",
                "errors": [str(e)],
                "warnings": []
            }
    
    def cleanup_sandbox(self, mutation_id: str) -> bool:
        """
        Cleanup sandbox for mutation.
        
        Args:
            mutation_id: Mutation ID
            
        Returns:
            True if successful
        """
        try:
            sandbox_path = self.active_sandboxes.get(mutation_id)
            if sandbox_path and sandbox_path.exists():
                shutil.rmtree(sandbox_path)
                logger.info(f"Cleaned up sandbox for mutation {mutation_id}")
            
            with self._lock:
                if mutation_id in self.active_sandboxes:
                    del self.active_sandboxes[mutation_id]
            
            return True
            
        except Exception as e:
            logger.error(f"Error cleaning up sandbox for {mutation_id}: {e}")
            return False
    
    def get_test_result(self, test_id: str) -> Optional[SandboxTestResult]:
        """Get test result by test ID."""
        return self.test_history.get(test_id)
    
    def get_mutation_test_history(self, mutation_id: str) -> List[SandboxTestResult]:
        """Get all test results for a mutation."""
        return [
            result for result in self.test_history.values()
            if result.mutation_id == mutation_id
        ]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get sandbox statistics."""
        return {
            "total_tests": self.stats["total_tests"],
            "passed": self.stats["passed"],
            "failed": self.stats["failed"],
            "errors": self.stats["errors"],
            "timeouts": self.stats["timeouts"],
            "pass_rate": self.stats["passed"] / max(1, self.stats["total_tests"]),
            "average_execution_time": self.stats["average_execution_time"],
            "active_sandboxes": len(self.active_sandboxes)
        }


# Integration helper
def integrate_with_mutation_publisher(
    mutation_publisher,
    sandbox: MutationSandbox
):
    """
    Integrate MutationSandbox with MutationPublisher to test before publishing.
    
    Args:
        mutation_publisher: MutationPublisher instance
        sandbox: MutationSandbox instance
    """
    original_publish = mutation_publisher.publish_mutation
    
    def enhanced_publish_mutation(
        mutation_id: str,
        verify_before_publish: bool = True,
        create_backup: bool = True,
        run_sandbox_tests: bool = True
    ):
        """Enhanced publish that runs sandbox tests first."""
        if not mutation_publisher.mutation_engine:
            return original_publish(mutation_id, verify_before_publish, create_backup)
        
        proposal = mutation_publisher.mutation_engine.get_proposal(mutation_id)
        if not proposal:
            return original_publish(mutation_id, verify_before_publish, create_backup)
        
        # Run sandbox tests if requested
        if run_sandbox_tests:
            logger.info(f"Running sandbox tests for mutation {mutation_id}")
            test_result = sandbox.test_mutation(mutation_id, proposal)
            
            if not test_result.passed:
                logger.warning(f"Sandbox tests failed for mutation {mutation_id}")
                return {
                    "success": False,
                    "error": "Sandbox tests failed",
                    "test_result": test_result.to_dict(),
                    "publish_id": None
                }
            
            logger.info(f"Sandbox tests passed for mutation {mutation_id}")
        
        # Proceed with normal publish
        return original_publish(mutation_id, verify_before_publish, create_backup)
    
    mutation_publisher.publish_mutation = enhanced_publish_mutation
    logger.info("MutationSandbox integrated with MutationPublisher")


# Example usage
if __name__ == "__main__":
    # Initialize sandbox
    sandbox = MutationSandbox(
        project_root=".",
        test_command="pytest",
        timeout=60
    )
    
    # Test a mutation
    # proposal = mutation_engine.get_proposal("mut_123")
    # result = sandbox.test_mutation("mut_123", proposal)
    # print(f"Test result: {result.passed}")


"""
TestRunner - Executes tests and linters
"""

import subprocess
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class TestRunner:
    """
    Runs tests, linters, and type checkers.
    Returns structured results.
    """
    
    def __init__(self, repo_root: Path, test_profiles: Optional[Dict[str, List[str]]] = None):
        """
        Initialize test runner.
        
        Args:
            repo_root: Root of repository
            test_profiles: Optional dict mapping domain -> list of test commands
        """
        self.repo_root = Path(repo_root)
        self.test_profiles = test_profiles or {}
    
    def run_tests(self, domain: Optional[str] = None, specific_tests: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Run tests.
        
        Args:
            domain: Optional domain to determine test profile
            specific_tests: Optional list of specific test files/paths to run
        
        Returns:
            Dict with status, failed_tests, logs, etc.
        """
        if specific_tests:
            return self._run_specific_tests(specific_tests)
        
        # Run pytest by default
        return self._run_pytest()
    
    def run_linters(self) -> Dict[str, Any]:
        """
        Run linters (ruff, flake8, black --check, etc.)
        
        Returns:
            Dict with status and results
        """
        results = {
            "status": "passed",
            "linters": {},
            "errors": []
        }
        
        # Try ruff
        ruff_result = self._run_command(["ruff", "check", "."], "ruff")
        results["linters"]["ruff"] = ruff_result
        if ruff_result["status"] != "passed":
            results["status"] = "failed"
            results["errors"].extend(ruff_result.get("errors", []))
        
        # Try black check
        black_result = self._run_command(["black", "--check", "."], "black")
        results["linters"]["black"] = black_result
        if black_result["status"] != "passed" and results["status"] == "passed":
            results["status"] = "warning"  # Black is formatting, not critical
        
        return results
    
    def run_type_check(self) -> Dict[str, Any]:
        """
        Run type checker (mypy or pyright).
        
        Returns:
            Dict with status and results
        """
        # Try mypy first
        mypy_result = self._run_command(["mypy", "."], "mypy")
        if mypy_result["status"] != "not_available":
            return mypy_result
        
        # Fallback to pyright
        pyright_result = self._run_command(["pyright", "."], "pyright")
        return pyright_result
    
    def _run_pytest(self) -> Dict[str, Any]:
        """Run pytest"""
        return self._run_command(["pytest", "-v"], "pytest")
    
    def _run_specific_tests(self, test_paths: List[str]) -> Dict[str, Any]:
        """Run specific test files"""
        cmd = ["pytest", "-v"] + test_paths
        return self._run_command(cmd, "pytest")
    
    def _run_command(self, cmd: List[str], tool_name: str) -> Dict[str, Any]:
        """
        Run a command and return structured results.
        
        Args:
            cmd: Command to run
            tool_name: Name of tool for logging
        
        Returns:
            Dict with status, output, errors, etc.
        """
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                return {
                    "status": "passed",
                    "output": result.stdout,
                    "tool": tool_name
                }
            else:
                return {
                    "status": "failed",
                    "output": result.stdout + result.stderr,
                    "errors": self._parse_errors(result.stdout + result.stderr, tool_name),
                    "tool": tool_name,
                    "returncode": result.returncode
                }
        
        except FileNotFoundError:
            logger.warning(f"{tool_name} not found")
            return {
                "status": "not_available",
                "tool": tool_name,
                "error": f"{tool_name} not installed"
            }
        
        except subprocess.TimeoutExpired:
            logger.error(f"{tool_name} timed out")
            return {
                "status": "timeout",
                "tool": tool_name,
                "error": "Command timed out"
            }
        
        except Exception as e:
            logger.error(f"Error running {tool_name}: {e}")
            return {
                "status": "error",
                "tool": tool_name,
                "error": str(e)
            }
    
    def _parse_errors(self, output: str, tool_name: str) -> List[str]:
        """Parse errors from tool output"""
        errors = []
        
        if tool_name == "pytest":
            # Parse pytest errors
            lines = output.split('\n')
            for line in lines:
                if 'FAILED' in line or 'ERROR' in line:
                    errors.append(line.strip())
        
        elif tool_name in ["ruff", "black", "mypy"]:
            # Parse linter/type checker errors
            lines = output.split('\n')
            for line in lines:
                if 'error' in line.lower() or 'warning' in line.lower():
                    errors.append(line.strip())
        
        return errors[:10]  # Limit to first 10 errors


# project_guardian/metacoder.py
# MetaCoder: Code Mutation and Self-Modification Engine
# Based on elysia 4 (Main Consolidation) designs
#
# SECURITY: This module performs code mutations and should be used with caution.
# All external operations route through gateways (FileWriter, SubprocessRunner).

import logging
import json
import ast
import inspect
import importlib
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from threading import Lock
import uuid

try:
    from .mutation_engine import MutationEngine, MutationProposal
    from .trust_eval_action import TrustEvalAction
except ImportError:
    from mutation_engine import MutationEngine, MutationProposal
    from trust_eval_action import TrustEvalAction

logger = logging.getLogger(__name__)


class MetaCoder:
    """
    Reads, mutates, and validates Elysia's own code.
    Integrates with MutationEngine for proposals and test suite for validation.
    """
    
    def __init__(
        self,
        mutation_engine: Optional[MutationEngine] = None,
        trust_eval: Optional[TrustEvalAction] = None,
        file_writer=None,  # FileWriter instance (required for gateway)
        subprocess_runner=None,  # SubprocessRunner instance (required for gateway)
        project_root: str = ".",
        storage_path: str = "data/metacoder.json"
    ):
        self.mutation_engine = mutation_engine
        self.trust_eval = trust_eval
        self.file_writer = file_writer
        self.subprocess_runner = subprocess_runner
        self.project_root = Path(project_root)
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Thread-safe operations
        self._lock = Lock()
        
        # Mutation history
        self.mutation_history: List[Dict[str, Any]] = []
        
        # Backup directory
        self.backup_dir = self.project_root / "backups" / "metacoder"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        self.load()
    
    def read_module_source(self, module_path: str) -> Optional[str]:
        """
        Read source code from a module file.
        
        Args:
            module_path: Path to module file (relative to project_root)
            
        Returns:
            Source code as string or None if not found
        """
        file_path = self.project_root / module_path
        
        if not file_path.exists():
            logger.error(f"Module file not found: {module_path}")
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading module {module_path}: {e}")
            return None
    
    def backup_module(self, module_path: str) -> Optional[str]:
        """
        Create a backup of a module file.
        
        Args:
            module_path: Path to module file
            
        Returns:
            Backup file path or None if failed
        """
        file_path = self.project_root / module_path
        
        if not file_path.exists():
            logger.error(f"Cannot backup non-existent file: {module_path}")
            return None
        
        # Create backup filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"{file_path.stem}_{timestamp}{file_path.suffix}"
        backup_path = self.backup_dir / backup_filename
        
        try:
            # Route backup through FileWriter gateway
            if self.file_writer:
                # Read original content
                original_content = file_path.read_text(encoding='utf-8')
                # Write backup via gateway (use full path)
                self.file_writer.write_file(
                    file_path=str(backup_path),
                    content=original_content,
                    mode="w",
                    caller_identity="MetaCoder",
                    task_id=None
                )
                logger.info(f"Backed up {module_path} to {backup_path}")
                return str(backup_path)
            else:
                logger.error("FileWriter not available for backup")
                return None
        except Exception as e:
            logger.error(f"Error backing up {module_path}: {e}")
            return None
    
    def validate_code_syntax(self, code: str) -> Dict[str, Any]:
        """
        Validate Python code syntax.
        
        Args:
            code: Code to validate
            
        Returns:
            Validation result dictionary
        """
        try:
            ast.parse(code)
            return {
                "valid": True,
                "errors": []
            }
        except SyntaxError as e:
            return {
                "valid": False,
                "errors": [{
                    "type": "SyntaxError",
                    "message": str(e),
                    "line": e.lineno,
                    "offset": e.offset
                }]
            }
        except Exception as e:
            return {
                "valid": False,
                "errors": [{
                    "type": type(e).__name__,
                    "message": str(e)
                }]
            }
    
    def run_tests(
        self,
        test_command: Optional[str] = None,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """
        Run test suite to validate code changes.
        
        Args:
            test_command: Optional custom test command (defaults to pytest)
            timeout: Test timeout in seconds
            
        Returns:
            Test result dictionary
        """
        if test_command is None:
            test_command = ["python", "-m", "pytest", "project_guardian/tests", "-v"]
        
        try:
            # Route through SubprocessRunner gateway
            if self.subprocess_runner:
                result = self.subprocess_runner.run_command(
                    command=test_command if isinstance(test_command, list) else test_command.split(),
                    caller_identity="MetaCoder",
                    task_id=None,
                    timeout=timeout
                )
                
                return {
                    "success": result.get("returncode", -1) == 0,
                    "return_code": result.get("returncode", -1),
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                    "passed": result.get("returncode", -1) == 0
                }
            else:
                return {
                    "success": False,
                    "error": "SubprocessRunner not available",
                    "passed": False
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "passed": False
            }
    
    def apply_mutation(
        self,
        module_path: str,
        new_code: str,
        mutation_reason: str = "Optimization",
        run_tests: bool = True
    ) -> Dict[str, Any]:
        """
        Apply a code mutation to a module file.
        
        Args:
            module_path: Path to module file
            new_code: New code to write
            mutation_reason: Reason for mutation
            run_tests: Whether to run tests after mutation
            
        Returns:
            Result dictionary
        """
        # Validate syntax first
        validation = self.validate_code_syntax(new_code)
        if not validation["valid"]:
            return {
                "success": False,
                "error": "Syntax validation failed",
                "validation_errors": validation["errors"]
            }
        
        file_path = self.project_root / module_path
        
        # Backup original
        original_code = self.read_module_source(module_path)
        if not original_code:
            return {
                "success": False,
                "error": "Could not read original code"
            }
        
        backup_path = self.backup_module(module_path)
        if not backup_path:
            logger.warning(f"Backup failed, proceeding anyway")
        
        # Write new code via FileWriter gateway
        try:
            if self.file_writer:
                self.file_writer.write_file(
                    file_path=str(file_path),
                    content=new_code,
                    mode="w",
                    caller_identity="MetaCoder",
                    task_id=None
                )
            else:
                # Fallback if FileWriter not available (should not happen)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_code)
            
            logger.info(f"Applied mutation to {module_path}")
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to write file: {e}"
            }
        
        # Run tests if requested
        test_result = None
        if run_tests:
            test_result = self.run_tests()
            
            if not test_result.get("passed"):
                # Rollback on test failure
                logger.warning(f"Tests failed, rolling back mutation")
                self.rollback_mutation(module_path, original_code)
                
                return {
                    "success": False,
                    "error": "Tests failed after mutation",
                    "test_result": test_result,
                    "rolled_back": True
                }
        
        # Record mutation
        mutation_record = {
            "mutation_id": str(uuid.uuid4()),
            "module_path": module_path,
            "timestamp": datetime.now().isoformat(),
            "reason": mutation_reason,
            "backup_path": backup_path,
            "test_passed": test_result.get("passed") if test_result else None,
            "success": True
        }
        
        with self._lock:
            self.mutation_history.append(mutation_record)
            
            # Keep only last 1000 mutations
            if len(self.mutation_history) > 1000:
                self.mutation_history = self.mutation_history[-1000:]
            
            self.save()
        
        return {
            "success": True,
            "mutation_id": mutation_record["mutation_id"],
            "test_result": test_result
        }
    
    def rollback_mutation(
        self,
        module_path: str,
        original_code: Optional[str] = None
    ) -> bool:
        """
        Rollback a mutation by restoring original code.
        
        Args:
            module_path: Path to module file
            original_code: Original code to restore (if None, uses latest backup)
            
        Returns:
            True if successful
        """
        file_path = self.project_root / module_path
        
        if original_code:
            # Restore from provided code
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(original_code)
                logger.info(f"Rolled back {module_path} from provided code")
                return True
            except Exception as e:
                logger.error(f"Error rolling back {module_path}: {e}")
                return False
        else:
            # Find latest backup
            backups = sorted(
                self.backup_dir.glob(f"{file_path.stem}_*{file_path.suffix}"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            if not backups:
                logger.error(f"No backups found for {module_path}")
                return False
            
            latest_backup = backups[0]
            
            try:
                # Route rollback through FileWriter gateway
                if self.file_writer:
                    backup_content = Path(latest_backup).read_text(encoding='utf-8')
                    self.file_writer.write_file(
                        file_path=str(file_path),
                        content=backup_content,
                        mode="w",
                        caller_identity="MetaCoder",
                        task_id=None
                    )
                    logger.info(f"Rolled back {module_path} from backup {latest_backup}")
                    return True
                else:
                    logger.error("FileWriter not available for rollback")
                    return False
            except Exception as e:
                logger.error(f"Error rolling back from backup: {e}")
                return False
    
    def propose_mutation_via_engine(
        self,
        module_path: str,
        mutation_type: str,
        description: str,
        proposed_code: str
    ) -> Optional[str]:
        """
        Propose a mutation via MutationEngine.
        
        Args:
            module_path: Module to mutate
            mutation_type: Type of mutation
            description: Mutation description
            proposed_code: Proposed code
            
        Returns:
            Mutation ID or None if failed
        """
        if not self.mutation_engine:
            logger.error("MutationEngine not configured")
            return None
        
        # Read original code
        original_code = self.read_module_source(module_path)
        
        # Propose mutation
        mutation_id = self.mutation_engine.propose_mutation(
            target_module=module_path,
            mutation_type=mutation_type,
            description=description,
            proposed_code=proposed_code,
            original_code=original_code
        )
        
        return mutation_id
    
    def analyze_module(self, module_path: str) -> Dict[str, Any]:
        """
        Analyze a module and extract information.
        
        Args:
            module_path: Path to module file
            
        Returns:
            Analysis dictionary
        """
        source = self.read_module_source(module_path)
        if not source:
            return {
                "success": False,
                "error": "Could not read module"
            }
        
        try:
            tree = ast.parse(source)
            
            # Count elements
            classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            
            return {
                "success": True,
                "module_path": module_path,
                "lines": len(source.splitlines()),
                "classes": classes,
                "class_count": len(classes),
                "functions": functions,
                "function_count": len(functions),
                "size_bytes": len(source.encode('utf-8'))
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_mutation_history(
        self,
        module_path: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get mutation history, optionally filtered."""
        with self._lock:
            history = self.mutation_history[-limit:] if limit > 0 else self.mutation_history
            
            if module_path:
                history = [m for m in history if m.get("module_path") == module_path]
            
            return history
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get MetaCoder statistics."""
        with self._lock:
            successful = len([m for m in self.mutation_history if m.get("success")])
            failed = len([m for m in self.mutation_history if not m.get("success")])
            
            # Modules mutated
            modules_mutated = set(m.get("module_path") for m in self.mutation_history)
            
            return {
                "total_mutations": len(self.mutation_history),
                "successful_mutations": successful,
                "failed_mutations": failed,
                "modules_mutated": len(modules_mutated),
                "module_list": list(modules_mutated)
            }
    
    def save(self):
        """Save MetaCoder state."""
        with self._lock:
            data = {
                "mutation_history": self.mutation_history[-500:],  # Last 500
                "updated_at": datetime.now().isoformat()
            }
            
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
    
    def load(self):
        """Load MetaCoder state."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                self.mutation_history = data.get("mutation_history", [])
            
            logger.info(f"Loaded {len(self.mutation_history)} mutation records")
        except Exception as e:
            logger.error(f"Error loading MetaCoder state: {e}")


# Example usage
if __name__ == "__main__":
    metacoder = MetaCoder()
    
    # Analyze a module
    analysis = metacoder.analyze_module("project_guardian/memory.py")
    print(f"Module analysis: {analysis}")
    
    # Get statistics
    stats = metacoder.get_statistics()
    print(f"Statistics: {stats}")


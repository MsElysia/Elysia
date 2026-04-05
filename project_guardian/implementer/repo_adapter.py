"""
RepoAdapter - Abstraction over codebase operations
Handles branching, file access, and patch application
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RepoConfig:
    """Configuration for repo operations"""
    repo_root: Path
    allowed_directories: List[str]  # Whitelist of directories that can be modified
    read_only_directories: List[str] = None  # Directories that are read-only
    max_files_per_proposal: int = 50
    max_diff_size_kb: int = 500
    auto_commit: bool = False  # Whether to auto-commit changes


class RepoAdapter:
    """
    Abstraction over repository operations.
    Handles branching, file access, and patch application with safety constraints.
    """
    
    def __init__(self, config: RepoConfig):
        self.config = config
        self.repo_root = Path(config.repo_root).resolve()
        self.current_branch: Optional[str] = None
        self.read_only_dirs = set(config.read_only_directories or [])
        
        # Validate repo root exists
        if not self.repo_root.exists():
            raise ValueError(f"Repo root does not exist: {self.repo_root}")
        
        # Non-git roots are supported (branch names used for tracking only)
        if not (self.repo_root / ".git").exists():
            logger.debug("Repo root %s has no .git; git operations will be no-ops", self.repo_root)
    
    def create_work_branch(self, proposal_id: str) -> str:
        """
        Create a new branch for implementing a proposal.
        
        Returns:
            Branch name
        """
        branch_name = f"implement/{proposal_id}"
        
        # Check if git is available
        if not (self.repo_root / ".git").exists():
            logger.debug("Not a git repository, using branch name %s for tracking only", branch_name)
            self.current_branch = branch_name
            return branch_name
        
        try:
            # Check if branch already exists
            result = subprocess.run(
                ["git", "branch", "--list", branch_name],
                cwd=self.repo_root,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0 and result.stdout.strip():
                logger.info(f"Branch {branch_name} already exists, checking it out")
                subprocess.run(
                    ["git", "checkout", branch_name],
                    cwd=self.repo_root,
                    check=True
                )
            else:
                # Create new branch from current branch or main
                subprocess.run(
                    ["git", "checkout", "-b", branch_name],
                    cwd=self.repo_root,
                    check=True
                )
                logger.info(f"Created branch: {branch_name}")
            
            self.current_branch = branch_name
            return branch_name
            
        except subprocess.CalledProcessError as e:
            logger.warning(f"Git branch creation failed: {e}, continuing without git")
            self.current_branch = branch_name
            return branch_name
        except FileNotFoundError:
            logger.warning("Git not found, continuing without git")
            self.current_branch = branch_name
            return branch_name
    
    def get_relevant_files(self, step_description: str, target_files: List[str]) -> Dict[str, str]:
        """
        Get contents of relevant files for a step.
        
        Args:
            step_description: Description of what needs to be done
            target_files: List of file paths (relative to repo root)
        
        Returns:
            Dict mapping file paths to their contents
        """
        files = {}
        
        for file_path in target_files:
            full_path = self.repo_root / file_path
            
            # Validate path is within repo
            try:
                full_path.resolve().relative_to(self.repo_root)
            except ValueError:
                logger.warning(f"File {file_path} is outside repo root, skipping")
                continue
            
            # Check if in allowed directory
            if not self._is_allowed_path(full_path):
                logger.warning(f"File {file_path} is not in allowed directories, skipping")
                continue
            
            if full_path.exists():
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        files[file_path] = f.read()
                except Exception as e:
                    logger.error(f"Failed to read {file_path}: {e}")
                    files[file_path] = ""
            else:
                files[file_path] = ""  # New file
        
        return files
    
    def apply_patch(self, file_path: str, patch_content: str, create_if_missing: bool = True) -> bool:
        """
        Apply a patch to a file.
        
        Args:
            file_path: Relative path to file
            patch_content: New file content (not a diff, but full content)
            create_if_missing: Whether to create file if it doesn't exist
        
        Returns:
            True if successful
        """
        full_path = self.repo_root / file_path
        
        # Validate path
        try:
            full_path.resolve().relative_to(self.repo_root)
        except ValueError:
            logger.error(f"File {file_path} is outside repo root")
            return False
        
        # Check if in allowed directory
        if not self._is_allowed_path(full_path):
            logger.error(f"File {file_path} is not in allowed directories")
            return False
        
        # Check if read-only
        if self._is_read_only_path(full_path):
            logger.error(f"File {file_path} is in read-only directory")
            return False
        
        try:
            # Create parent directories if needed
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(patch_content)
            
            logger.info(f"Applied patch to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to apply patch to {file_path}: {e}")
            return False
    
    def create_commit(self, message: str, files: Optional[List[str]] = None) -> bool:
        """
        Create a commit with changes.
        
        Args:
            message: Commit message
            files: Optional list of files to commit (if None, commits all changes)
        
        Returns:
            True if successful
        """
        if not self.config.auto_commit:
            logger.info(f"Auto-commit disabled, would commit: {message}")
            return True
        
        try:
            # Stage files
            if files:
                for file_path in files:
                    subprocess.run(
                        ["git", "add", file_path],
                        cwd=self.repo_root,
                        check=True
                    )
            else:
                subprocess.run(
                    ["git", "add", "-A"],
                    cwd=self.repo_root,
                    check=True
                )
            
            # Create commit
            subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.repo_root,
                check=True
            )
            
            logger.info(f"Created commit: {message}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create commit: {e}")
            return False
    
    def generate_diff(self) -> str:
        """Generate diff of current changes"""
        try:
            result = subprocess.run(
                ["git", "diff"],
                cwd=self.repo_root,
                capture_output=True,
                text=True
            )
            return result.stdout
        except Exception as e:
            logger.error(f"Failed to generate diff: {e}")
            return ""
    
    def get_status(self) -> Dict[str, Any]:
        """Get git status information"""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.repo_root,
                capture_output=True,
                text=True
            )
            return {
                "branch": self.current_branch,
                "status": result.stdout,
                "has_changes": bool(result.stdout.strip())
            }
        except Exception as e:
            logger.error(f"Failed to get git status: {e}")
            return {"error": str(e)}
    
    def _is_allowed_path(self, path: Path) -> bool:
        """Check if path is in allowed directories"""
        if not self.config.allowed_directories:
            return True  # No restrictions
        
        path_str = str(path.relative_to(self.repo_root))
        for allowed in self.config.allowed_directories:
            if path_str.startswith(allowed):
                return True
        return False
    
    def _is_read_only_path(self, path: Path) -> bool:
        """Check if path is in read-only directories"""
        if not self.read_only_dirs:
            return False
        
        path_str = str(path.relative_to(self.repo_root))
        for read_only in self.read_only_dirs:
            if path_str.startswith(read_only):
                return True
        return False


# project_guardian/analysis_engine.py
# Read-Only Analysis Engine for Project Guardian
# Performs analysis without mutations or subprocess execution

import hashlib
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from .memory import MemoryCore
from .external import WebReader, TrustDeniedError, TrustReviewRequiredError


class AnalysisEngine:
    """
    Read-only analysis engine.
    Performs analysis on files/URLs without mutations or subprocess execution.
    """
    
    # Maximum lines to include in FILE_SET preview
    MAX_PREVIEW_LINES = 50
    
    # Directories to exclude from REPO_SUMMARY
    EXCLUDED_DIRS = {"venv", "__pycache__", ".git", "node_modules", "REPORTS", "TASKS", "MUTATIONS", "guardian_backups"}
    
    def __init__(
        self,
        memory: MemoryCore,
        web_reader: Optional[WebReader] = None,
        repo_root: Optional[Path] = None
    ):
        self.memory = memory
        self.web_reader = web_reader
        
        # Determine repo root
        if repo_root is None:
            # Compute from file location: go up from project_guardian/analysis_engine.py to project root
            self.repo_root = Path(__file__).resolve().parent.parent
        else:
            self.repo_root = Path(repo_root).resolve()
    
    def run(self, kind: str, inputs: List[Dict[str, str]], task_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Run analysis based on kind and inputs.
        
        Args:
            kind: Analysis kind (REPO_SUMMARY, FILE_SET, URL_RESEARCH)
            inputs: List of input dicts with 'type' and 'value' keys
            task_id: Optional task ID for audit
            
        Returns:
            Dict with analysis results
            
        Raises:
            ValueError: If kind is unknown or inputs invalid
            TrustDeniedError: If network access denied (for URL_RESEARCH)
            TrustReviewRequiredError: If network access requires review (for URL_RESEARCH)
        """
        if kind == "REPO_SUMMARY":
            return self._run_repo_summary(inputs, task_id)
        elif kind == "FILE_SET":
            return self._run_file_set(inputs, task_id)
        elif kind == "URL_RESEARCH":
            return self._run_url_research(inputs, task_id)
        else:
            raise ValueError(f"Unknown analysis kind: {kind}")
    
    def _run_repo_summary(self, inputs: List[Dict[str, str]], task_id: Optional[str] = None) -> Dict[str, Any]:
        """Run REPO_SUMMARY analysis."""
        # Walk repo root, excluding certain directories
        file_counts: Dict[str, int] = {}
        total_lines = 0
        top_level_dirs: List[str] = []
        
        # Get top-level directories
        for item in self.repo_root.iterdir():
            if item.is_dir() and item.name not in self.EXCLUDED_DIRS:
                top_level_dirs.append(item.name)
        
        top_level_dirs.sort()
        
        # Walk files
        for path in self.repo_root.rglob("*"):
            # Skip excluded directories
            if any(excluded in path.parts for excluded in self.EXCLUDED_DIRS):
                continue
            
            if path.is_file():
                # Count by extension
                ext = path.suffix or "(no extension)"
                file_counts[ext] = file_counts.get(ext, 0) + 1
                
                # Rough line count (read first chunk only for performance)
                try:
                    # Try UTF-8 first, then fallback to alternative encodings
                    chunk = None
                    for encoding in ["utf-8", "latin-1", "cp1252"]:
                        try:
                            with open(path, "r", encoding=encoding) as f:
                                chunk = f.read(10240)  # Read first 10KB to estimate
                            break
                        except UnicodeDecodeError:
                            continue
                    
                    if chunk is None:
                        logger.debug(f"Failed to decode {path} with any encoding (likely binary), skipping line count")
                        continue
                    
                    total_lines += chunk.count("\n")
                except (PermissionError, OSError):
                    # Permission error or file system error - skip
                    pass
        
        self.memory.remember(
            f"[AnalysisEngine] REPO_SUMMARY completed: {len(file_counts)} extensions, {total_lines} lines (est)",
            category="analysis",
            priority=0.6
        )
        
        return {
            "kind": "REPO_SUMMARY",
            "file_counts_by_extension": file_counts,
            "total_lines_estimate": total_lines,
            "top_level_directories": top_level_dirs,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "repo_root": str(self.repo_root)
        }
    
    def _run_file_set(self, inputs: List[Dict[str, str]], task_id: Optional[str] = None) -> Dict[str, Any]:
        """Run FILE_SET analysis."""
        results: List[Dict[str, Any]] = []
        
        for inp in inputs:
            if inp.get("type") != "file":
                continue
            
            file_path_str = inp.get("value", "")
            if not file_path_str:
                continue
            
            # Resolve path relative to repo root
            file_path = (self.repo_root / file_path_str).resolve()
            
            # Safety: ensure path is within repo root
            try:
                file_path.relative_to(self.repo_root)
            except ValueError:
                # Path outside repo root - skip
                continue
            
            if not file_path.exists() or not file_path.is_file():
                results.append({
                    "filename": file_path_str,
                    "status": "not_found",
                    "error": "File does not exist or is not a file"
                })
                continue
            
            # Read file
            try:
                file_size = file_path.stat().st_size
                
                # Compute SHA256
                sha256_hash = hashlib.sha256()
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        sha256_hash.update(chunk)
                file_hash = sha256_hash.hexdigest()
                
                # Read first N lines
                preview_lines: List[str] = []
                try:
                    # Try UTF-8 first, then fallback to alternative encodings
                    content_lines = None
                    for encoding in ["utf-8", "latin-1", "cp1252"]:
                        try:
                            with open(file_path, "r", encoding=encoding) as f:
                                content_lines = []
                                for i, line in enumerate(f):
                                    if i >= self.MAX_PREVIEW_LINES:
                                        break
                                    content_lines.append(line.rstrip("\n\r"))
                            break
                        except UnicodeDecodeError:
                            continue
                    
                    if content_lines is None:
                        logger.debug(f"Failed to decode {file_path} with any encoding (likely binary), skipping preview")
                        preview_lines = ["<binary or unreadable>"]
                    else:
                        preview_lines = content_lines
                except (PermissionError, OSError) as e:
                    # Permission error or file system error - skip preview
                    logger.debug(f"Cannot read {file_path} for preview: {e}")
                    preview_lines = ["<binary or unreadable>"]
                
                results.append({
                    "filename": file_path_str,
                    "status": "success",
                    "size_bytes": file_size,
                    "sha256": file_hash,
                    "preview_lines": preview_lines,
                    "preview_line_count": len(preview_lines)
                })
                
            except Exception as e:
                results.append({
                    "filename": file_path_str,
                    "status": "error",
                    "error": str(e)
                })
        
        self.memory.remember(
            f"[AnalysisEngine] FILE_SET completed: {len(results)} files analyzed",
            category="analysis",
            priority=0.6
        )
        
        return {
            "kind": "FILE_SET",
            "files": results,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def _run_url_research(self, inputs: List[Dict[str, str]], task_id: Optional[str] = None) -> Dict[str, Any]:
        """Run URL_RESEARCH analysis."""
        if not self.web_reader:
            raise ValueError("WebReader not available for URL_RESEARCH")
        
        results: List[Dict[str, Any]] = []
        
        for inp in inputs:
            if inp.get("type") != "url":
                continue
            
            url = inp.get("value", "")
            if not url:
                continue
            
            # Use WebReader.fetch() - subject to TrustMatrix and SSRF rules
            # This may raise TrustDeniedError or TrustReviewRequiredError
            try:
                # WebReader.fetch() returns string content (or None)
                content = self.web_reader.fetch(
                    url=url,
                    caller_identity="AnalysisEngine",
                    task_id=task_id
                )
                
                # Extract information
                content_str = content if content else ""
                
                # Get first N characters (e.g., 1000)
                preview_chars = content_str[:1000] if content_str else ""
                
                results.append({
                    "url": url,
                    "status": "success",
                    "content_length": len(content_str),
                    "preview_chars": preview_chars,
                    "preview_length": len(preview_chars)
                })
                
            except TrustDeniedError as e:
                # Network access denied - re-raise so Core can handle appropriately
                # Do not include in results (no partial results on deny)
                raise
                
            except TrustReviewRequiredError as e:
                # Network access requires review - re-raise so Core can enqueue and return needs_review
                raise
        
        self.memory.remember(
            f"[AnalysisEngine] URL_RESEARCH completed: {len(results)} URLs analyzed",
            category="analysis",
            priority=0.6
        )
        
        return {
            "kind": "URL_RESEARCH",
            "urls": results,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

#!/usr/bin/env python3
"""
Repository Audit Tool
- Scans the project for structure issues
- Reports missing __init__.py packages
- Detects duplicate module names across directories
- Finds imports that reference missing modules/packages
- Summarizes candidate canonical packages for Elysia

Usage:
  python scripts/repo_audit.py
"""
from __future__ import annotations

import os
import sys
import ast
import re
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Directories to analyze as code (skip venvs, compiled, backups, zips, large data)
DEFAULT_INCLUDE_DIRS = [
    "organized_project",
    "organized_projects",
    "project_guardian",
    "elysia_core",
    "core_modules",
    "modules",
    "src",
]

DEFAULT_EXCLUDE_DIR_PATTERNS = [
    ".venv", "venv", "elysia_core_venv", "__pycache__", "elysia_core_compiled", "build", "dist",
    "backups", "backup", "archive", "archives", "*.egg-info", "node_modules",
    "*.zip", "*.tar", "*.gz", "*.bz2", "*.7z",
    "data/cache", "logs", "documentation", "docs", "tests",
]

PYTHON_FILE_SUFFIXES = (".py",)


def is_excluded(path: Path) -> bool:
    lower = str(path).lower()
    for patt in DEFAULT_EXCLUDE_DIR_PATTERNS:
        if patt.startswith("*") and lower.endswith(patt[1:].lower()):
            return True
        if patt in lower.split(os.sep):
            return True
    return False


def discover_python_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for include in DEFAULT_INCLUDE_DIRS:
        dir_path = root / include
        if not dir_path.exists():
            continue
        for p in dir_path.rglob("*.py"):
            if is_excluded(p):
                continue
            files.append(p)
    return files


def find_missing_init_packages(root: Path) -> List[Path]:
    missing: List[Path] = []
    for include in DEFAULT_INCLUDE_DIRS:
        dir_path = root / include
        if not dir_path.exists():
            continue
        for d in dir_path.rglob("*"):
            if d.is_dir():
                if is_excluded(d):
                    continue
                # Treat a directory as package if it contains .py files
                if any(fp.suffix in PYTHON_FILE_SUFFIXES for fp in d.iterdir() if fp.is_file()):
                    init_file = d / "__init__.py"
                    if not init_file.exists():
                        missing.append(d)
    return missing


def collect_module_names(files: List[Path]) -> Dict[str, List[Path]]:
    name_to_paths: Dict[str, List[Path]] = defaultdict(list)
    for f in files:
        mod_name = f.stem
        name_to_paths[mod_name].append(f)
    return name_to_paths


def parse_imports(py_file: Path) -> Set[str]:
    try:
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(text)
    except Exception:
        return set()
    imports: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.add(n.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])
    return imports


def detect_broken_top_level_imports(files: List[Path]) -> Dict[Path, List[str]]:
    # Consider top-level packages available in repo root
    available_top_levels: Set[str] = set()
    for child in PROJECT_ROOT.iterdir():
        if child.is_dir() and (child / "__init__.py").exists():
            available_top_levels.add(child.name)
        if child.is_dir() and any((child / inc).exists() for inc in ("__init__.py",)):
            # already handled
            pass
    # Also include known source roots as top-level namespaces
    available_top_levels.update(["organized_project", "organized_projects", "project_guardian", "elysia_core"]) 

    missing_by_file: Dict[Path, List[str]] = {}
    for f in files:
        imports = parse_imports(f)
        missing = []
        for top in imports:
            # Skip stdlib-ish quick filter
            if top in ("os","sys","re","json","typing","asyncio","pathlib","logging","dataclasses","datetime","time","functools","itertools"):
                continue
            # Heuristic: if a directory exists matching top name anywhere under roots
            exists_anywhere = any((PROJECT_ROOT / top).exists() for _ in [0])
            if not exists_anywhere:
                # Allow third-party packages to be missing (we only warn for likely in-repo packages)
                if top.lower() in ("elysia_core","organized_project","project_guardian"):
                    missing.append(top)
        if missing:
            missing_by_file[f] = missing
    return missing_by_file


def main() -> int:
    print(f"Repo audit at: {PROJECT_ROOT}")

    files = discover_python_files(PROJECT_ROOT)
    print(f"- Python files scanned: {len(files)}")

    missing_pkgs = find_missing_init_packages(PROJECT_ROOT)
    print(f"- Packages missing __init__.py: {len(missing_pkgs)}")
    for d in sorted(missing_pkgs)[:50]:
        print(f"  [pkg-missing-init] {d.relative_to(PROJECT_ROOT)}")
    if len(missing_pkgs) > 50:
        print(f"  ... and {len(missing_pkgs) - 50} more")

    name_to_paths = collect_module_names(files)
    dupes = {name: paths for name, paths in name_to_paths.items() if len(paths) > 3}
    print(f"- Duplicate module names (>3 occurrences): {len(dupes)}")
    for name, paths in list(dupes.items())[:20]:
        sample = ", ".join(str(p.relative_to(PROJECT_ROOT)) for p in paths[:3])
        print(f"  [dupe] {name}: {len(paths)} files (e.g., {sample})")
    if len(dupes) > 20:
        print(f"  ... and {len(dupes) - 20} more")

    missing_imports = detect_broken_top_level_imports(files)
    print(f"- Files importing missing top-level in-repo packages: {len(missing_imports)}")
    for f, miss in list(missing_imports.items())[:50]:
        print(f"  [missing-import] {f.relative_to(PROJECT_ROOT)} -> {', '.join(sorted(set(miss)))}")
    if len(missing_imports) > 50:
        print(f"  ... and {len(missing_imports) - 50} more")

    # Recommend canonical structure
    print("\nRecommendation: Canonical Elysia structure")
    print("- Keep one canonical package at repo root: elysia_core/")
    print("- Stage legacy code under legacy/ or archives/")
    print("- Interfaces: elysia_core/api, elysia_core/ui, elysia_core/cli")
    print("- Core: elysia_core/{core,memory,learning,runtime,security,database,streaming,distributed,enterprise,production,deployment}")
    print("- App: project_guardian/ depends on elysia_core")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
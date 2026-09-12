"""Static import-graph analyzer for Elysia / Project Guardian.

This module NEVER imports or executes Guardian code. It parses Python source with
``ast`` and builds a best-effort local import graph so we can distinguish likely
live boot paths from legacy, proposal, backup, and orphaned modules.

It is intentionally conservative and pre-integration safe.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


DEFAULT_ENTRYPOINTS = (
    "project_guardian/__main__.py",
    "project_guardian/system_orchestrator.py",
    "startup.py",
    "start_ui_panel.py",
    "setup_guardian.py",
)

LEGACY_HINTS = (
    "old modules/",
    "backup",
    "backups/",
    "organized_project/",
    "proposals/",
    "archive/",
    "archives/",
)


@dataclass(frozen=True)
class ModuleRecord:
    path: str
    imports: Tuple[str, ...]
    classification: str
    parse_error: Optional[str] = None


def _norm(path: Path) -> str:
    return path.as_posix().lstrip("./")


def classify_path(path: str) -> str:
    lower = path.lower()
    if any(h in lower for h in LEGACY_HINTS):
        if "proposals/" in lower:
            return "PROPOSAL"
        if "backup" in lower:
            return "BACKUP"
        return "LEGACY"
    if "/tests/" in f"/{lower}" or lower.startswith("tests/"):
        return "TEST"
    if lower.endswith(".md") or lower.endswith(".txt"):
        return "DOC"
    return "CANDIDATE"


def module_name_for_file(root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def discover_python_files(root: Path) -> Dict[str, Path]:
    modules: Dict[str, Path] = {}
    for path in root.rglob("*.py"):
        rel = _norm(path.relative_to(root))
        if "/.venv/" in f"/{rel.lower()}/" or "/venv/" in f"/{rel.lower()}/":
            continue
        try:
            modules[module_name_for_file(root, path)] = path
        except Exception:
            continue
    return modules


def parse_imports(path: Path, current_module: str) -> Tuple[Tuple[str, ...], Optional[str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except Exception as exc:
        return tuple(), f"{type(exc).__name__}: {exc}"

    imports: Set[str] = set()
    current_parts = current_module.split(".")
    package_parts = current_parts[:-1]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            level = int(node.level or 0)
            base_parts = list(package_parts)
            if level:
                trim = max(0, level - 1)
                if trim:
                    base_parts = base_parts[:-trim] if trim <= len(base_parts) else []
            if node.module:
                base_parts.extend(node.module.split("."))
                imports.add(".".join(base_parts))
            else:
                for alias in node.names:
                    imports.add(".".join(base_parts + [alias.name]))
    return tuple(sorted(i for i in imports if i)), None


def resolve_local_module(name: str, module_index: Dict[str, Path]) -> Optional[str]:
    if name in module_index:
        return name
    parts = name.split(".")
    while parts:
        candidate = ".".join(parts)
        if candidate in module_index:
            return candidate
        parts.pop()
    return None


def build_graph(root: Path) -> Tuple[Dict[str, ModuleRecord], Dict[str, Set[str]], Dict[str, Path]]:
    index = discover_python_files(root)
    records: Dict[str, ModuleRecord] = {}
    graph: Dict[str, Set[str]] = defaultdict(set)

    for module, path in index.items():
        imports, error = parse_imports(path, module)
        rel = _norm(path.relative_to(root))
        records[module] = ModuleRecord(
            path=rel,
            imports=imports,
            classification=classify_path(rel),
            parse_error=error,
        )
        for imported in imports:
            resolved = resolve_local_module(imported, index)
            if resolved and resolved != module:
                graph[module].add(resolved)
    return records, graph, index


def entrypoint_modules(root: Path, index: Dict[str, Path], entries: Iterable[str]) -> List[str]:
    reverse = {_norm(p.relative_to(root)): m for m, p in index.items()}
    out: List[str] = []
    for entry in entries:
        key = entry.replace("\\", "/").lstrip("./")
        module = reverse.get(key)
        if module:
            out.append(module)
    return out


def reachable_from(entries: Iterable[str], graph: Dict[str, Set[str]]) -> Tuple[Set[str], Dict[str, int]]:
    seen: Set[str] = set()
    depth: Dict[str, int] = {}
    queue = deque((entry, 0) for entry in entries)
    while queue:
        module, d = queue.popleft()
        if module in seen:
            continue
        seen.add(module)
        depth[module] = d
        for child in sorted(graph.get(module, set())):
            if child not in seen:
                queue.append((child, d + 1))
    return seen, depth


def analyze(root: Path, entries: Iterable[str] = DEFAULT_ENTRYPOINTS) -> dict:
    root = root.resolve()
    records, graph, index = build_graph(root)
    roots = entrypoint_modules(root, index, entries)
    reachable, depth = reachable_from(roots, graph)

    reverse_edges: Dict[str, Set[str]] = defaultdict(set)
    for src, dsts in graph.items():
        for dst in dsts:
            reverse_edges[dst].add(src)

    modules = []
    for module, record in sorted(records.items(), key=lambda kv: kv[1].path):
        status = record.classification
        if status == "CANDIDATE":
            status = "LIVE_CANDIDATE" if module in reachable else "ORPHAN_CANDIDATE"
        modules.append(
            {
                **asdict(record),
                "module": module,
                "status": status,
                "reachable": module in reachable,
                "depth": depth.get(module),
                "local_importers": sorted(reverse_edges.get(module, set())),
                "local_imports": sorted(graph.get(module, set())),
            }
        )

    return {
        "analysis_type": "static_ast_import_graph",
        "executes_code": False,
        "root": str(root),
        "requested_entrypoints": list(entries),
        "resolved_entrypoints": roots,
        "module_count": len(records),
        "reachable_count": len(reachable),
        "modules": modules,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Static Guardian boot-path analyzer")
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument("--entry", action="append", dest="entries", default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    result = analyze(args.root, args.entries or DEFAULT_ENTRYPOINTS)
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

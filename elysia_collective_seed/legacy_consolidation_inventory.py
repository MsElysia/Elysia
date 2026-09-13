"""Read-only legacy Guardian/Elysia inventory and correspondence scanner.

The scanner never imports or executes inspected Python code. It fingerprints files,
extracts Python symbols/imports through AST, and compares one or more legacy roots
against a canonical Guardian root.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "dist", "build",
}

GENESIS_HINTS = {
    "constitution", "covenant", "rebuild manifest", "quantum oath", "erebus",
    "elysia", "identity", "ethics", "oath",
}

PRIVATE_HINTS = {
    ".env", "secret", "credential", "token", "api_key", "chatlogs", "personal",
    "database", ".db", ".sqlite", ".sqlite3",
}


@dataclass
class FileRecord:
    root_label: str
    path: str
    size: int
    mtime_ns: int
    sha256: str
    suffix: str
    python_parse_ok: Optional[bool]
    classes: List[str]
    functions: List[str]
    imports: List[str]
    tags: List[str]


@dataclass
class LegacyMatch:
    legacy_root: str
    legacy_path: str
    classification: str
    canonical_candidates: List[str]
    evidence: List[str]
    legacy_sha256: str


def _excluded(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    return any(part in EXCLUDE_DIRS for part in rel.parts)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _python_metadata(path: Path) -> Tuple[Optional[bool], List[str], List[str], List[str]]:
    if path.suffix.lower() != ".py":
        return None, [], [], []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text, filename=str(path))
    except Exception:
        return False, [], [], []
    classes: Set[str] = set()
    functions: Set[str] = set()
    imports: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.add(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return True, sorted(classes), sorted(functions), sorted(imports)


def _tags(path: Path, rel: str) -> List[str]:
    hay = rel.lower().replace("_", " ").replace("-", " ")
    tags: List[str] = []
    if any(h in hay for h in GENESIS_HINTS):
        tags.append("GENESIS_CANDIDATE")
    if any(h in hay for h in PRIVATE_HINTS):
        tags.append("SENSITIVE_OR_PRIVATE_REVIEW")
    parts = {p.lower() for p in Path(rel).parts}
    if "old modules" in hay or "backup" in hay or "archive" in parts:
        tags.append("LEGACY_PATH")
    if "proposal" in hay or "proposals" in parts:
        tags.append("PROPOSAL_OR_DESIGN")
    return tags


def inventory_root(root: Path, label: str) -> List[FileRecord]:
    root = root.resolve()
    out: List[FileRecord] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if _excluded(path, root):
            continue
        try:
            stat = path.stat()
            rel = path.relative_to(root).as_posix()
            parse_ok, classes, functions, imports = _python_metadata(path)
            out.append(FileRecord(
                root_label=label,
                path=rel,
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                sha256=_sha256(path),
                suffix=path.suffix.lower(),
                python_parse_ok=parse_ok,
                classes=classes,
                functions=functions,
                imports=imports,
                tags=_tags(path, rel),
            ))
        except (OSError, PermissionError):
            continue
    return out


def _symbol_set(rec: FileRecord) -> Set[str]:
    return {f"C:{x}" for x in rec.classes} | {f"F:{x}" for x in rec.functions}


def compare_legacy(canonical: List[FileRecord], legacy: List[FileRecord]) -> List[LegacyMatch]:
    by_hash: Dict[str, List[FileRecord]] = {}
    by_path: Dict[str, FileRecord] = {}
    py_records: List[FileRecord] = []
    for rec in canonical:
        by_hash.setdefault(rec.sha256, []).append(rec)
        by_path[rec.path.lower()] = rec
        if rec.suffix == ".py" and rec.python_parse_ok:
            py_records.append(rec)

    out: List[LegacyMatch] = []
    for old in legacy:
        candidates: List[str] = []
        evidence: List[str] = []
        exact = by_hash.get(old.sha256, [])
        if exact:
            candidates = [r.path for r in exact]
            evidence.append("identical_sha256")
            classification = "EXACT_DUPLICATE"
        elif old.path.lower() in by_path:
            cur = by_path[old.path.lower()]
            candidates = [cur.path]
            evidence.extend(["same_relative_path", "different_sha256"])
            if old.mtime_ns > cur.mtime_ns:
                evidence.append("legacy_file_mtime_is_newer")
            elif old.mtime_ns < cur.mtime_ns:
                evidence.append("canonical_file_mtime_is_newer")
            classification = "SAME_PATH_DIFFERENT_CONTENT"
        else:
            classification = "UNIQUE_LEGACY"
            old_symbols = _symbol_set(old)
            best: List[Tuple[float, FileRecord, Set[str]]] = []
            if old_symbols:
                for cur in py_records:
                    cur_symbols = _symbol_set(cur)
                    overlap = old_symbols & cur_symbols
                    union = old_symbols | cur_symbols
                    if overlap and union:
                        score = len(overlap) / len(union)
                        best.append((score, cur, overlap))
                best.sort(key=lambda x: (-x[0], x[1].path))
                if best and best[0][0] >= 0.25:
                    classification = "SYMBOL_OVERLAP"
                    for score, cur, overlap in best[:5]:
                        if score < 0.25:
                            break
                        candidates.append(cur.path)
                        evidence.append(
                            f"symbol_overlap:{cur.path}:score={score:.3f}:symbols={','.join(sorted(overlap))}"
                        )
        if "GENESIS_CANDIDATE" in old.tags:
            evidence.append("genesis_candidate_name_or_path")
        if "SENSITIVE_OR_PRIVATE_REVIEW" in old.tags:
            evidence.append("sensitive_or_private_review")
        out.append(LegacyMatch(
            legacy_root=old.root_label,
            legacy_path=old.path,
            classification=classification,
            canonical_candidates=candidates,
            evidence=evidence,
            legacy_sha256=old.sha256,
        ))
    return out


def build_report(canonical_root: Path, legacy_roots: List[Path]) -> dict:
    canonical = inventory_root(canonical_root, "canonical")
    all_legacy: List[FileRecord] = []
    root_summaries = []
    for idx, root in enumerate(legacy_roots, start=1):
        label = f"legacy_{idx}"
        records = inventory_root(root, label)
        all_legacy.extend(records)
        root_summaries.append({"label": label, "root": str(root.resolve()), "file_count": len(records)})

    matches = compare_legacy(canonical, all_legacy)
    counts: Dict[str, int] = {}
    for m in matches:
        counts[m.classification] = counts.get(m.classification, 0) + 1

    return {
        "analysis_type": "legacy_guardian_correspondence_inventory",
        "executes_inspected_code": False,
        "canonical_root": str(canonical_root.resolve()),
        "canonical_file_count": len(canonical),
        "legacy_roots": root_summaries,
        "classification_counts": counts,
        "canonical_inventory": [asdict(r) for r in canonical],
        "legacy_inventory": [asdict(r) for r in all_legacy],
        "matches": [asdict(m) for m in matches],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Guardian/Elysia legacy correspondence inventory")
    parser.add_argument("canonical_root", type=Path)
    parser.add_argument("legacy_roots", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=Path("legacy_inventory.json"))
    args = parser.parse_args()

    for root in [args.canonical_root, *args.legacy_roots]:
        if not root.exists() or not root.is_dir():
            parser.error(f"directory not found: {root}")

    report = build_report(args.canonical_root, args.legacy_roots)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "canonical_files": report["canonical_file_count"],
        "legacy_roots": report["legacy_roots"],
        "classification_counts": report["classification_counts"],
        "output": str(args.out),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

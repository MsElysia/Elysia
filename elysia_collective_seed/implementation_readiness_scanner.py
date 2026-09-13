"""Static implementation-readiness scanner for Guardian/Elysia Python modules.

This tool does not import or execute project code. It parses source text/AST and
reports signals that a module may be a stub, placeholder, generated skeleton, or
abstract interface rather than an operational capability.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List


PLACEHOLDER_PATTERNS = (
    re.compile(r"\bTODO\b", re.IGNORECASE),
    re.compile(r"\bplaceholder\b", re.IGNORECASE),
    re.compile(r"fake source", re.IGNORECASE),
    re.compile(r"dummy data", re.IGNORECASE),
    re.compile(r"not implemented", re.IGNORECASE),
)

EXCLUDE_PARTS = {".venv", "venv", "node_modules", ".git", "__pycache__"}


@dataclass(frozen=True)
class ReadinessRecord:
    path: str
    parse_error: str | None
    pass_count: int
    not_implemented_count: int
    ellipsis_body_count: int
    placeholder_markers: int
    todo_markers: int
    function_count: int
    class_count: int
    executable_statement_count: int
    readiness: str
    reasons: List[str]


def _is_excluded(path: Path) -> bool:
    return any(part.lower() in EXCLUDE_PARTS for part in path.parts)


def _body_is_ellipsis(body: List[ast.stmt]) -> bool:
    if len(body) != 1:
        return False
    node = body[0]
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and node.value.value is Ellipsis


def scan_source(path: Path, root: Path) -> ReadinessRecord:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = path.relative_to(root).as_posix()
    todo_count = len(re.findall(r"\bTODO\b", text, flags=re.IGNORECASE))
    placeholder_count = sum(len(p.findall(text)) for p in PLACEHOLDER_PATTERNS)

    try:
        tree = ast.parse(text, filename=str(path))
        parse_error = None
    except Exception as exc:
        return ReadinessRecord(
            path=rel,
            parse_error=f"{type(exc).__name__}: {exc}",
            pass_count=0,
            not_implemented_count=0,
            ellipsis_body_count=0,
            placeholder_markers=placeholder_count,
            todo_markers=todo_count,
            function_count=0,
            class_count=0,
            executable_statement_count=0,
            readiness="PARSE_ERROR",
            reasons=["source_does_not_parse"],
        )

    pass_count = 0
    not_impl = 0
    ellipsis_count = 0
    functions = 0
    classes = 0
    executable = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.Pass):
            pass_count += 1
        elif isinstance(node, ast.Raise):
            exc = node.exc
            if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                not_impl += 1
            elif isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name) and exc.func.id == "NotImplementedError":
                not_impl += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions += 1
            if _body_is_ellipsis(node.body):
                ellipsis_count += 1
        elif isinstance(node, ast.ClassDef):
            classes += 1
            if _body_is_ellipsis(node.body):
                ellipsis_count += 1

    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            executable += 1

    reasons: List[str] = []
    lower_rel = rel.lower()
    if "old modules/" in lower_rel or "backup" in lower_rel:
        reasons.append("legacy_or_backup_path")
    if "proposals/" in lower_rel:
        reasons.append("proposal_path")
    if todo_count:
        reasons.append("todo_markers")
    if placeholder_count:
        reasons.append("placeholder_markers")
    if not_impl:
        reasons.append("not_implemented_raises")
    if ellipsis_count:
        reasons.append("ellipsis_bodies")

    # `pass` alone is weak evidence because exception handlers and intentionally
    # empty branches use it legitimately. Escalate only when combined with other
    # stub signals or when the file has almost no executable structure.
    if pass_count and (todo_count or placeholder_count or not_impl or ellipsis_count):
        reasons.append("pass_with_stub_signals")

    if "legacy_or_backup_path" in reasons or "proposal_path" in reasons:
        readiness = "NON_RUNTIME_CANDIDATE"
    elif not_impl or ellipsis_count:
        readiness = "PARTIAL_OR_ABSTRACT"
    elif placeholder_count >= 2 or (todo_count >= 2 and executable <= 1):
        readiness = "LIKELY_STUB"
    elif reasons:
        readiness = "REVIEW"
    else:
        readiness = "IMPLEMENTATION_CANDIDATE"

    return ReadinessRecord(
        path=rel,
        parse_error=parse_error,
        pass_count=pass_count,
        not_implemented_count=not_impl,
        ellipsis_body_count=ellipsis_count,
        placeholder_markers=placeholder_count,
        todo_markers=todo_count,
        function_count=functions,
        class_count=classes,
        executable_statement_count=executable,
        readiness=readiness,
        reasons=reasons,
    )


def scan_tree(root: Path) -> dict:
    root = root.resolve()
    records: List[ReadinessRecord] = []
    for path in sorted(root.rglob("*.py")):
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if _is_excluded(rel):
            continue
        records.append(scan_source(path, root))

    counts: Dict[str, int] = {}
    for rec in records:
        counts[rec.readiness] = counts.get(rec.readiness, 0) + 1

    return {
        "analysis_type": "static_implementation_readiness",
        "executes_code": False,
        "root": str(root),
        "file_count": len(records),
        "readiness_counts": counts,
        "files": [asdict(r) for r in records],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Static Guardian implementation-readiness scanner")
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    result = scan_tree(args.root)
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

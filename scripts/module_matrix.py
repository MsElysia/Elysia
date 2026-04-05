#!/usr/bin/env python3
"""
Module Completeness Matrix Generator
=====================================
Scans project_guardian modules and generates completeness reports.
"""

import ast
import json
import os
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict

# Project root (assumes script is in scripts/)
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

# Directories
PROJECT_GUARDIAN_DIR = PROJECT_ROOT / "project_guardian"
SPEC_MODULES_DIR = PROJECT_ROOT / "SPEC_MODULES"
REPORTS_DIR = PROJECT_ROOT / "REPORTS"
TESTS_DIR = PROJECT_ROOT / "tests"
TASKS_DIR = PROJECT_ROOT / "TASKS"

# Allowed external-action surfaces (gateways)
ALLOWED_EXTERNAL_ACTION_MODULES = {
    "external",  # network gateway
    "file_writer",  # file write gateway
    "subprocess_runner",  # subprocess gateway
    "mutation",  # mutation engine (allowed file writes)
    "ui",  # UI app (allowed to write REPORTS/TASKS/MUTATIONS)
}

# Network libraries to detect
NETWORK_LIBS = {"requests", "httpx", "urllib", "aiohttp", "websocket", "playwright"}

# Subprocess patterns
SUBPROCESS_PATTERNS = {"subprocess", "os.system", "os.popen"}

# File write patterns
FILE_WRITE_PATTERNS = {
    'open(..., "w"', 'open(..., "a"', 'open(..., "wb"', 'open(..., "ab"',
    '.write_text', '.write_bytes', 'shutil.move', 'shutil.copy', 'os.replace'
}


def get_module_shortname(module_path: Path) -> str:
    """Get module shortname from path"""
    rel_path = module_path.relative_to(PROJECT_ROOT)
    parts = rel_path.parts
    
    if parts[0] == "project_guardian":
        if len(parts) == 2:
            # project_guardian/trust.py -> trust
            return parts[1].replace(".py", "")
        elif len(parts) == 3 and parts[1] == "ui":
            # project_guardian/ui/app.py -> ui
            return "ui"
        elif len(parts) == 3:
            # project_guardian/implementer/codegen_client.py -> implementer.codegen_client
            return f"{parts[1]}.{parts[2].replace('.py', '')}"
    
    # Fallback
    return module_path.stem


def find_python_modules() -> List[Path]:
    """Find all Python modules under project_guardian/"""
    modules = []
    
    if not PROJECT_GUARDIAN_DIR.exists():
        return modules
    
    for py_file in PROJECT_GUARDIAN_DIR.rglob("*.py"):
        # Skip templates
        if "templates" in py_file.parts:
            continue
        # Skip __init__.py (optional, but we'll include it)
        # Skip __pycache__
        if "__pycache__" in py_file.parts:
            continue
        modules.append(py_file)
    
    return sorted(modules)


def check_spec_exists(shortname: str) -> bool:
    """Check if spec file exists"""
    if shortname == "ui":
        spec_file = SPEC_MODULES_DIR / "ui.md"
    else:
        spec_file = SPEC_MODULES_DIR / f"{shortname}.md"
    return spec_file.exists()


def check_audit_exists(shortname: str) -> bool:
    """Check if audit file exists"""
    if shortname == "ui":
        audit_file = REPORTS_DIR / "module_audit_ui.md"
    else:
        audit_file = REPORTS_DIR / f"module_audit_{shortname}.md"
    return audit_file.exists()


def check_tests_exist(shortname: str, module_dotted: str) -> bool:
    """Check if tests exist (heuristic)"""
    if not TESTS_DIR.exists():
        return False
    
    # Check for dedicated smoke test
    smoke_test = TESTS_DIR / f"test_{shortname}_smoke.py"
    if smoke_test.exists():
        return True
    
    # Check if any test file references the module
    for test_file in TESTS_DIR.rglob("test_*.py"):
        try:
            content = test_file.read_text(encoding='utf-8')
            if shortname in content or module_dotted in content:
                return True
        except (IOError, UnicodeDecodeError):
            continue
    
    return False


def check_wired_in_core(shortname: str, module_dotted: str) -> bool:
    """Check if module is wired in core.py (AST-based)"""
    core_file = PROJECT_GUARDIAN_DIR / "core.py"
    if not core_file.exists():
        return False
    
    try:
        content = core_file.read_text(encoding='utf-8')
        tree = ast.parse(content, filename=str(core_file))
        
        for node in ast.walk(tree):
            # Check imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if module_dotted in alias.name or shortname in alias.name:
                        return True
            elif isinstance(node, ast.ImportFrom):
                if node.module and (module_dotted in node.module or shortname in node.module):
                    return True
                # Check if importing from project_guardian
                if node.module and node.module.startswith("project_guardian"):
                    for alias in node.names:
                        if shortname in str(alias.name):
                            return True
        
        # Also check for string references (less precise but catches more)
        if f"project_guardian.{shortname}" in content or f"from project_guardian import {shortname}" in content:
            return True
        if shortname in content and "import" in content:
            # Heuristic: if shortname appears near import statements
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if shortname in line and ("import" in line or i > 0 and "import" in lines[i-1]):
                    return True
    
    except (IOError, SyntaxError, UnicodeDecodeError):
        return False
    
    return False


def check_bypass_clean(module_path: Path, shortname: str) -> Tuple[bool, List[str]]:
    """Check if module has bypass issues (script-level approximation)"""
    if shortname in ALLOWED_EXTERNAL_ACTION_MODULES:
        # Gateway modules are allowed to have external actions
        if shortname == "ui":
            return True, ["UI writes (allowed)"]
        elif shortname == "mutation":
            return True, ["Mutation file writes (allowed)"]
        else:
            return True, ["Gateway module (allowed)"]
    
    issues = []
    
    try:
        content = module_path.read_text(encoding='utf-8')
        
        # Check for network libs
        for lib in NETWORK_LIBS:
            if f"import {lib}" in content or f"from {lib}" in content:
                issues.append(f"Network library: {lib}")
        
        # Check for subprocess
        for pattern in SUBPROCESS_PATTERNS:
            if pattern in content:
                issues.append(f"Subprocess: {pattern}")
        
        # Check for file writes (simple string matching)
        for pattern in FILE_WRITE_PATTERNS:
            if pattern in content:
                # Try to be smarter: check if it's in a comment or string literal
                # For now, just flag it
                issues.append(f"File write pattern: {pattern}")
        
        # More sophisticated: parse AST and check for actual calls
        try:
            tree = ast.parse(content, filename=str(module_path))
            for node in ast.walk(tree):
                # Check for subprocess calls
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id == "system" or node.func.id == "popen":
                            # Check if it's os.system or os.popen
                            if isinstance(node.func.ctx, ast.Load):
                                # Check parent context
                                for parent in ast.walk(tree):
                                    if hasattr(parent, 'value') and parent.value == node:
                                        if isinstance(parent, ast.Attribute) and parent.attr in ("system", "popen"):
                                            issues.append(f"Subprocess call: {parent.attr}")
                    elif isinstance(node.func, ast.Attribute):
                        if node.func.attr in ("write_text", "write_bytes"):
                            issues.append(f"File write: {node.func.attr}")
                        elif node.func.attr in ("move", "copy") and isinstance(node.func.value, ast.Name) and node.func.value.id == "shutil":
                            issues.append(f"File operation: shutil.{node.func.attr}")
        except SyntaxError:
            # If AST parsing fails, rely on string matching
            pass
    
    except (IOError, UnicodeDecodeError):
        return False, ["Cannot read file"]
    
    return len(issues) == 0, issues


def compute_status(record: Dict) -> str:
    """Compute status: ✅ complete / ⚠️ partial / ❌ missing"""
    required_fields = ["spec_exists", "audit_exists", "tests_exist", "wired_in_core", "bypass_clean"]
    true_count = sum(1 for field in required_fields if record.get(field, False))
    
    if true_count == len(required_fields):
        return "✅ complete"
    elif true_count >= len(required_fields) // 2:
        return "⚠️ partial"
    else:
        return "❌ missing"


def generate_notes(record: Dict) -> List[str]:
    """Generate notes list of detected gaps"""
    notes = []
    if not record.get("spec_exists"):
        notes.append("Missing spec")
    if not record.get("audit_exists"):
        notes.append("Missing audit")
    if not record.get("tests_exist"):
        notes.append("Missing tests")
    if not record.get("wired_in_core"):
        notes.append("Not wired in core")
    if not record.get("bypass_clean"):
        notes.append(f"Bypass issues: {', '.join(record.get('bypass_issues', []))}")
    return notes


def analyze_modules() -> List[Dict]:
    """Analyze all modules and return records"""
    modules = find_python_modules()
    records = []
    
    for module_path in modules:
        shortname = get_module_shortname(module_path)
        module_dotted = f"project_guardian.{shortname.replace('.', '.')}"
        
        # Handle nested modules
        if '.' in shortname:
            parts = shortname.split('.')
            module_dotted = f"project_guardian.{'.'.join(parts)}"
        
        spec_exists = check_spec_exists(shortname)
        audit_exists = check_audit_exists(shortname)
        tests_exist = check_tests_exist(shortname, module_dotted)
        wired_in_core = check_wired_in_core(shortname, module_dotted)
        bypass_clean, bypass_issues = check_bypass_clean(module_path, shortname)
        
        record = {
            "module": module_dotted,
            "path": str(module_path.relative_to(PROJECT_ROOT)),
            "shortname": shortname,
            "spec_exists": spec_exists,
            "audit_exists": audit_exists,
            "tests_exist": tests_exist,
            "wired_in_core": wired_in_core,
            "bypass_clean": bypass_clean,
            "bypass_issues": bypass_issues,
        }
        
        record["status"] = compute_status(record)
        record["notes"] = generate_notes(record)
        
        records.append(record)
    
    return records


def generate_json_report(records: List[Dict]) -> Path:
    """Generate JSON report"""
    output_file = REPORTS_DIR / "module_completeness_matrix.json"
    REPORTS_DIR.mkdir(exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=2)
    
    return output_file


def generate_markdown_report(records: List[Dict]) -> Path:
    """Generate Markdown report"""
    output_file = REPORTS_DIR / "module_completeness_matrix.md"
    REPORTS_DIR.mkdir(exist_ok=True)
    
    # Sort by status (worst first)
    status_order = {"❌ missing": 0, "⚠️ partial": 1, "✅ complete": 2}
    records_sorted = sorted(records, key=lambda r: (status_order.get(r["status"], 3), r["module"]))
    
    # Count by status
    status_counts = defaultdict(int)
    for record in records:
        status_counts[record["status"]] += 1
    
    from datetime import datetime
    lines = [
        "# Module Completeness Matrix",
        "",
        f"**Generated:** {datetime.now().isoformat()}",
        "",
        "## Summary",
        "",
        f"- ✅ Complete: {status_counts.get('✅ complete', 0)}",
        f"- ⚠️ Partial: {status_counts.get('⚠️ partial', 0)}",
        f"- ❌ Missing: {status_counts.get('❌ missing', 0)}",
        f"- **Total modules:** {len(records)}",
        "",
        "## Module Status (Worst First)",
        "",
        "| Module | Spec | Audit | Tests | Wired | Bypass Clean | Status | Notes |",
        "|--------|------|-------|-------|-------|--------------|--------|-------|",
    ]
    
    for record in records_sorted:
        spec = "✅" if record["spec_exists"] else "❌"
        audit = "✅" if record["audit_exists"] else "❌"
        tests = "✅" if record["tests_exist"] else "❌"
        wired = "✅" if record["wired_in_core"] else "❌"
        bypass = "✅" if record["bypass_clean"] else "❌"
        status = record["status"]
        notes = ", ".join(record["notes"]) if record["notes"] else "-"
        
        lines.append(f"| {record['module']} | {spec} | {audit} | {tests} | {wired} | {bypass} | {status} | {notes} |")
    
    lines.extend([
        "",
        "## Gap Analysis",
        "",
    ])
    
    # Group by gap type
    missing_specs = [r for r in records if not r["spec_exists"]]
    missing_audits = [r for r in records if not r["audit_exists"]]
    missing_tests = [r for r in records if not r["tests_exist"]]
    not_wired = [r for r in records if not r["wired_in_core"]]
    bypass_issues = [r for r in records if not r["bypass_clean"]]
    
    if missing_specs:
        lines.append(f"### Missing Specs ({len(missing_specs)} modules)")
        for r in missing_specs:
            lines.append(f"- `{r['module']}` ({r['path']})")
        lines.append("")
    
    if missing_audits:
        lines.append(f"### Missing Audits ({len(missing_audits)} modules)")
        for r in missing_audits:
            lines.append(f"- `{r['module']}` ({r['path']})")
        lines.append("")
    
    if missing_tests:
        lines.append(f"### Missing Tests ({len(missing_tests)} modules)")
        for r in missing_tests:
            lines.append(f"- `{r['module']}` ({r['path']})")
        lines.append("")
    
    if not_wired:
        lines.append(f"### Not Wired in Core ({len(not_wired)} modules)")
        for r in not_wired:
            lines.append(f"- `{r['module']}` ({r['path']})")
        lines.append("")
    
    if bypass_issues:
        lines.append(f"### Bypass Issues ({len(bypass_issues)} modules)")
        for r in bypass_issues:
            issues_str = ", ".join(r.get("bypass_issues", []))
            lines.append(f"- `{r['module']}` ({r['path']}): {issues_str}")
        lines.append("")
    
    content = "\n".join(lines)
    output_file.write_text(content, encoding='utf-8')
    
    return output_file


def generate_task_contracts(records: List[Dict]) -> List[Path]:
    """Generate follow-on task contracts"""
    created_files = []
    
    # Group gaps
    missing_specs = [r for r in records if not r["spec_exists"]]
    missing_audits = [r for r in records if not r["audit_exists"]]
    missing_tests = [r for r in records if not r["tests_exist"]]
    not_wired = [r for r in records if not r["wired_in_core"]]
    bypass_issues = [r for r in records if not r["bypass_clean"]]
    
    # TASK-0032-SPECS
    task_file = TASKS_DIR / "TASK-0032-SPECS.md"
    if missing_specs:
        content = f"""# TASK-0032 — Add Missing Module Specifications

## Goal

Add missing module specifications for modules that lack spec documentation.

## Scope

* `SPEC_MODULES/` directory
* Modules listed below

## Non-goals

* No refactors of existing modules
* No changes to module behavior
* Do not redesign architecture

## Modules Requiring Specs

"""
        for r in missing_specs:
            content += f"- `{r['module']}` ({r['path']})\n"
        content += """
## Acceptance Criteria

* Spec files created for all listed modules
* Specs follow format of existing specs (see `SPEC_MODULES/trust.md` as example)
* Each spec includes: purpose, responsibilities, boundaries, integration points
* `pytest -q` passes
* `.\scripts\acceptance.ps1` passes

## Rollback

Remove newly created spec files.
"""
    else:
        content = """# TASK-0032 — Add Missing Module Specifications

## Status: NO-OP

No missing specs found. All modules have specifications.

## Acceptance Criteria

* N/A (no work required)
"""
    
    task_file.write_text(content, encoding='utf-8')
    created_files.append(task_file)
    
    # TASK-0033-TESTS
    task_file = TASKS_DIR / "TASK-0033-TESTS.md"
    if missing_tests:
        content = f"""# TASK-0033 — Add Missing Smoke Tests

## Goal

Add missing smoke tests for modules that lack test coverage.

## Scope

* `tests/` directory
* Modules listed below

## Non-goals

* No refactors of existing modules
* No changes to module behavior
* Do not redesign architecture

## Modules Requiring Tests

"""
        for r in missing_tests:
            content += f"- `{r['module']}` ({r['path']})\n"
        content += """
## Acceptance Criteria

* Smoke test files created for all listed modules (e.g., `test_{module}_smoke.py`)
* Tests cover core functionality and behavioral correctness
* `pytest -q` passes
* `.\scripts\acceptance.ps1` passes

## Rollback

Remove newly created test files.
"""
    else:
        content = """# TASK-0033 — Add Missing Smoke Tests

## Status: NO-OP

No missing tests found. All modules have test coverage.

## Acceptance Criteria

* N/A (no work required)
"""
    
    task_file.write_text(content, encoding='utf-8')
    created_files.append(task_file)
    
    # TASK-0034-AUDITS
    task_file = TASKS_DIR / "TASK-0034-AUDITS.md"
    if missing_audits:
        content = f"""# TASK-0034 — Write Missing Audit Reports

## Goal

Write missing audit reports for modules that lack audit documentation.

## Scope

* `REPORTS/` directory
* Modules listed below

## Non-goals

* No refactors of existing modules
* No changes to module behavior
* Do not redesign architecture

## Modules Requiring Audits

"""
        for r in missing_audits:
            content += f"- `{r['module']}` ({r['path']})\n"
        content += """
## Acceptance Criteria

* Audit report files created for all listed modules (e.g., `REPORTS/module_audit_{module}.md`)
* Audits follow format of existing audits (see `REPORTS/module_audit_trust.md` as example)
* Each audit includes: what exists, what's missing, what's unsafe, next recommended tasks
* `pytest -q` passes
* `.\scripts\acceptance.ps1` passes

## Rollback

Remove newly created audit files.
"""
    else:
        content = """# TASK-0034 — Write Missing Audit Reports

## Status: NO-OP

No missing audits found. All modules have audit reports.

## Acceptance Criteria

* N/A (no work required)
"""
    
    task_file.write_text(content, encoding='utf-8')
    created_files.append(task_file)
    
    # TASK-0035-WIRING
    task_file = TASKS_DIR / "TASK-0035-WIRING.md"
    if not_wired:
        content = f"""# TASK-0035 — Core Wiring Decisions

## Goal

Decide whether modules not wired in core should be integrated or documented as on-demand.

## Scope

* `project_guardian/core.py` (if wiring)
* Documentation (if documenting on-demand usage)

## Non-goals

* No refactors of existing modules
* No changes to module behavior unless required for wiring
* Do not redesign architecture

## Modules Not Wired in Core

"""
        for r in not_wired:
            content += f"- `{r['module']}` ({r['path']})\n"
        content += """
## Decision Required

For each module, decide:
1. **Wire in core**: Integrate module into `GuardianCore` initialization and usage
2. **Document on-demand**: Document that module is used on-demand (not part of core loop)

## Acceptance Criteria

* Decision made for each module (wire or document)
* If wiring: module integrated into core.py
* If documenting: usage pattern documented in module spec or core spec
* `pytest -q` passes
* `.\scripts\acceptance.ps1` passes

## Rollback

Revert core.py changes if wiring was done.
"""
    else:
        content = """# TASK-0035 — Core Wiring Decisions

## Status: NO-OP

All modules are wired in core or intentionally on-demand.

## Acceptance Criteria

* N/A (no work required)
"""
    
    task_file.write_text(content, encoding='utf-8')
    created_files.append(task_file)
    
    # TASK-0036-BYPASS
    task_file = TASKS_DIR / "TASK-0036-BYPASS.md"
    if bypass_issues:
        content = f"""# TASK-0036 — Resolve Bypass Findings

## Goal

Resolve bypass findings: ensure all external actions go through gateways.

## Scope

* Modules listed below
* Gateway modules (if new gateways needed)

## Non-goals

* No refactors unrelated to bypass issues
* Do not redesign architecture

## Modules with Bypass Issues

"""
        for r in bypass_issues:
            issues_str = ", ".join(r.get("bypass_issues", []))
            content += f"- `{r['module']}` ({r['path']}): {issues_str}\n"
        content += """
## Resolution Strategy

For each module:
1. **Route through gateway**: If external action needed, route through appropriate gateway (WebReader, FileWriter, SubprocessRunner)
2. **Remove if unnecessary**: If external action is not needed, remove it
3. **Document exception**: If external action is intentional and safe, document why it's allowed

## Acceptance Criteria

* All bypass issues resolved (routed through gateways or removed)
* Invariant tests pass (no ungated external actions)
* `pytest -q` passes
* `.\scripts\acceptance.ps1` passes

## Rollback

Revert changes to modules.
"""
    else:
        content = """# TASK-0036 — Resolve Bypass Findings

## Status: NO-OP

No bypass issues found. All external actions go through gateways.

## Acceptance Criteria

* N/A (no work required)
"""
    
    task_file.write_text(content, encoding='utf-8')
    created_files.append(task_file)
    
    return created_files


def main():
    """Main entry point"""
    import sys
    
    try:
        print("Generating module completeness matrix...", file=sys.stderr)
        print("Generating module completeness matrix...")
        
        records = analyze_modules()
        print(f"Analyzed {len(records)} modules", file=sys.stderr)
        
        json_file = generate_json_report(records)
        md_file = generate_markdown_report(records)
        task_files = generate_task_contracts(records)
        
        # Count by status
        status_counts = defaultdict(int)
        for record in records:
            status_counts[record["status"]] += 1
        
        print(f"\n✅ Generated reports:", file=sys.stderr)
        print(f"   - {json_file}", file=sys.stderr)
        print(f"   - {md_file}", file=sys.stderr)
        print(f"\n✅ Generated task contracts:", file=sys.stderr)
        for task_file in task_files:
            print(f"   - {task_file}", file=sys.stderr)
        
        print(f"\n📊 Summary:", file=sys.stderr)
        print(f"   - ✅ Complete: {status_counts.get('✅ complete', 0)}", file=sys.stderr)
        print(f"   - ⚠️ Partial: {status_counts.get('⚠️ partial', 0)}", file=sys.stderr)
        print(f"   - ❌ Missing: {status_counts.get('❌ missing', 0)}", file=sys.stderr)
        print(f"   - Total modules: {len(records)}", file=sys.stderr)
        
        # Also print to stdout
        print(f"\n✅ Generated reports:")
        print(f"   - {json_file}")
        print(f"   - {md_file}")
        print(f"\n✅ Generated task contracts:")
        for task_file in task_files:
            print(f"   - {task_file}")
        
        print(f"\n📊 Summary:")
        print(f"   - ✅ Complete: {status_counts.get('✅ complete', 0)}")
        print(f"   - ⚠️ Partial: {status_counts.get('⚠️ partial', 0)}")
        print(f"   - ❌ Missing: {status_counts.get('❌ missing', 0)}")
        print(f"   - Total modules: {len(records)}")
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

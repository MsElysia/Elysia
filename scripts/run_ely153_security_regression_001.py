#!/usr/bin/env python3
"""Run ELY-153-SECURITY-REGRESSION-001 and emit red/green evidence JSON.

Does not modify production code. Uses the exact product SHA under test.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET_SHA = "821b9f4459eb888ad79d7845a8826a9f6cb94e3e"
TEST_FILE = "tests/test_ely153_security_regression_001.py"

BOUNDARY_MAP = {
    "test_A_unauthorized_autonomy_configuration_denied": "A_unauthorized_autonomy_configuration",
    "test_B_unauthorized_task_submission_denied": "B_unauthorized_task_submission",
    "test_C_unauthorized_credential_persistence_denied": "C_credential_persistence",
    "test_D_socketio_rejects_untrusted_origin": "D_socketio_origin_restrictions",
    "test_E_offline_javascript_assets_are_local": "E_offline_javascript_assets",
}


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()


def main() -> int:
    sha = _git_sha()
    out_dir = Path(os.environ.get("ELY153_EVIDENCE_DIR", "/tmp/ely153-security-evidence"))
    out_dir.mkdir(parents=True, exist_ok=True)
    junit = out_dir / "junit.xml"
    raw_log = out_dir / "pytest.log"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        TEST_FILE,
        "-vv",
        "--tb=short",
        f"--junitxml={junit}",
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True)
    raw_log.write_text(proc.stdout + "\n" + proc.stderr, encoding="utf-8")

    # Parse rough per-test outcomes from pytest verbose lines.
    outcomes = {}
    for line in (proc.stdout + "\n" + proc.stderr).splitlines():
        for name in list(BOUNDARY_MAP) + [
            "test_independent_verification_registered_routes",
            "test_independent_verification_socketio_config_object",
            "test_independent_verification_rendered_assets_endpoint",
        ]:
            if name in line and ("PASSED" in line or "FAILED" in line or "ERROR" in line or "SKIPPED" in line):
                if "PASSED" in line:
                    outcomes[name] = "PASSED"
                elif "SKIPPED" in line:
                    outcomes[name] = "SKIPPED"
                elif "ERROR" in line:
                    outcomes[name] = "ERROR"
                elif "FAILED" in line:
                    outcomes[name] = "FAILED"

    def verdict_for(pytest_status: str | None, blocked_hint: bool = False) -> str:
        if sha != TARGET_SHA:
            return "BLOCKED"
        if pytest_status is None:
            return "NEEDS_REVIEW"
        if pytest_status == "PASSED":
            return "PASS"
        if pytest_status in ("ERROR", "SKIPPED"):
            return "BLOCKED"
        if pytest_status == "FAILED":
            return "FAIL"
        return "NEEDS_REVIEW"

    boundaries = {}
    for test_name, boundary in BOUNDARY_MAP.items():
        st = outcomes.get(test_name)
        # Parametrized C may appear as test_C[...] — fold any C failures.
        if boundary == "C_credential_persistence":
            c_statuses = [v for k, v in outcomes.items() if k.startswith("test_C_")]
            if not c_statuses:
                # scan log for parametrized ids
                if "test_C_unauthorized_credential_persistence_denied" in (proc.stdout + proc.stderr):
                    if "FAILED" in proc.stdout and "test_C_" in proc.stdout:
                        st = "FAILED"
                    elif "PASSED" in proc.stdout and "test_C_" in proc.stdout and "FAILED" not in proc.stdout:
                        st = "PASSED"
            else:
                if any(s == "FAILED" for s in c_statuses):
                    st = "FAILED"
                elif any(s == "ERROR" for s in c_statuses):
                    st = "ERROR"
                elif all(s == "PASSED" for s in c_statuses):
                    st = "PASSED"

        v = verdict_for(st)
        # Distinguish security FAIL from fixture BLOCKED via log markers.
        blob = proc.stdout + proc.stderr
        if v == "FAIL" and "BLOCKED:" in blob and test_name in blob and "SECURITY DEFECT" not in blob:
            v = "BLOCKED"
        boundaries[boundary] = {
            "verdict": v,
            "pytest_status": st,
            "test_name": test_name,
            "security_relevant_failure": v == "FAIL",
        }

    # Refine parametrized C from log
    c_failed = "SECURITY DEFECT C" in (proc.stdout + proc.stderr) or (
        "test_C_unauthorized_credential_persistence_denied" in proc.stdout and "FAILED" in proc.stdout
    )
    c_passed_lines = [
        ln
        for ln in proc.stdout.splitlines()
        if "test_C_unauthorized_credential_persistence_denied" in ln and "PASSED" in ln
    ]
    c_failed_lines = [
        ln
        for ln in proc.stdout.splitlines()
        if "test_C_unauthorized_credential_persistence_denied" in ln and "FAILED" in ln
    ]
    if c_failed_lines or c_failed:
        boundaries["C_credential_persistence"]["verdict"] = "FAIL"
        boundaries["C_credential_persistence"]["pytest_status"] = "FAILED"
        boundaries["C_credential_persistence"]["security_relevant_failure"] = True
    elif c_passed_lines and not c_failed_lines:
        boundaries["C_credential_persistence"]["verdict"] = "PASS"
        boundaries["C_credential_persistence"]["pytest_status"] = "PASSED"
        boundaries["C_credential_persistence"]["security_relevant_failure"] = False

    independent = {
        name: outcomes.get(name)
        for name in (
            "test_independent_verification_registered_routes",
            "test_independent_verification_socketio_config_object",
            "test_independent_verification_rendered_assets_endpoint",
        )
    }

    report = {
        "suite": "ELY-153-SECURITY-REGRESSION-001",
        "target_sha_required": TARGET_SHA,
        "product_sha_actual": sha,
        "sha_match": sha == TARGET_SHA,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "python": sys.version.split()[0],
            "machine": platform.machine(),
        },
        "windows_run": platform.system() == "Windows",
        "linux_run": platform.system() == "Linux",
        "pytest_returncode": proc.returncode,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "boundaries": boundaries,
        "independent_verification": independent,
        "notes": [
            "FAIL on a security assertion is valid defect evidence.",
            "BLOCKED means fixture/import/SHA mismatch — not proof of security.",
            "No production code was modified to obtain results.",
            "Native Windows run: not available in this hosted Linux environment.",
        ],
        "smallest_safe_repairs": {
            "A_unauthorized_autonomy_configuration": (
                "Require authentication/CSRF on POST /api/autonomy before any "
                "config/autonomy.json write; default deny when unauthenticated."
            ),
            "B_unauthorized_task_submission": (
                "Require authentication on POST /api/tasks/submit before "
                "module_registry.route_task; do not accept anonymous browser task posts."
            ),
            "C_credential_persistence": (
                "Require authentication on /api/learning/link-facebook and "
                "/api/learning/link-twitter; never persist tokens without auth; "
                "avoid echoing secrets in responses/logs."
            ),
            "D_socketio_origin_restrictions": (
                "Replace SocketIO(cors_allowed_origins='*') with an explicit "
                "allowlist of local origins (e.g. http://127.0.0.1:<port>); "
                "reject untrusted Origin before privileged handlers run."
            ),
            "E_offline_javascript_assets": (
                "Vendor socket.io and chart.js under local static assets and "
                "reference only same-origin script URLs; remove CDN script tags."
            ),
        },
        "log_path": str(raw_log),
        "junit_path": str(junit),
    }

    evidence_path = out_dir / "ELY-153-SECURITY-REGRESSION-001-evidence.json"
    evidence_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nWrote evidence: {evidence_path}", file=sys.stderr)
    return 0 if sha == TARGET_SHA else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Standalone, non-mutating Elysia startup diagnostic.

Usage: python elysia_preflight.py --json
This command deliberately does not import project_guardian.__init__.
"""
import argparse
import importlib.util
import json
from pathlib import Path


def run(config_path: str) -> dict:
    source = Path(__file__).resolve().parent / "project_guardian" / "config_validator.py"
    spec = importlib.util.spec_from_file_location("_elysia_standalone_validator", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load configuration validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ConfigValidator(config_path=config_path, read_only=True).validate_all()


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Elysia startup checks; no services or providers started")
    parser.add_argument("--config", default="config/guardian_config.json")
    parser.add_argument("--json", action="store_true", help="Print machine-readable diagnostics")
    args = parser.parse_args()
    try:
        result = run(args.config)
    except Exception as exc:
        result = {
            "valid": False,
            "errors": [{"component": "preflight", "message": type(exc).__name__}],
            "warnings": [],
            "info": [],
            "total_issues": 1,
        }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("Elysia preflight: " + ("PASS" if result["valid"] else "FAIL"))
        for level in ("errors", "warnings", "info"):
            for issue in result[level]:
                print(f"{level.upper()}: {issue['component']}: {issue['message']}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

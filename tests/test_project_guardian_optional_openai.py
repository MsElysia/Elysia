from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_project_guardian_import_without_openai_sdk():
    repo_root = Path(__file__).resolve().parents[1]
    script = r"""
import builtins
import sys

_real_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name == "openai" or name.startswith("openai."):
        raise ImportError("blocked optional OpenAI SDK")
    if name == "pyttsx3" or name.startswith("pyttsx3."):
        raise ImportError("blocked optional text-to-speech SDK")
    return _real_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
import project_guardian
from project_guardian.mutation import MutationEngine
assert MutationEngine is not None
print("OPTIONAL_SDK_IMPORT_OK")
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    assert "OPTIONAL_SDK_IMPORT_OK" in proc.stdout

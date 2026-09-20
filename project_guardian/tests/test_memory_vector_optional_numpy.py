# Regression coverage for optional NumPy import behavior.

import os
from pathlib import Path
import subprocess
import sys


def test_project_guardian_import_and_memory_vector_use_without_numpy():
    repo_root = Path(__file__).resolve().parents[2]

    script = r"""
import builtins

_real_import = builtins.__import__


def _without_numpy(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "numpy" or name.startswith("numpy."):
        raise ImportError("NumPy deliberately unavailable for regression test")
    return _real_import(name, globals, locals, fromlist, level)


builtins.__import__ = _without_numpy

import project_guardian
from project_guardian import memory_vector_search as mvs

assert mvs.HAS_NUMPY is False

embedder = mvs.SimpleEmbedder()
embedding = embedder.embed("alpha beta", dimension=8)
assert isinstance(embedding, list)
assert len(embedding) == 8

search = mvs.MemoryVectorSearch(use_faiss=False)
search.add_memory("memory-1", "alpha beta gamma")
results = search.search_similar("alpha", limit=3)

assert results
assert results[0][0] == "memory-1"
"""

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(repo_root)
        if not existing_pythonpath
        else str(repo_root) + os.pathsep + existing_pythonpath
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, (
        "project_guardian should import and memory-vector fallback should work "
        "when NumPy is unavailable.\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )

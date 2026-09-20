# Regression coverage for importing and using memory_vector_search without NumPy.

import os
from pathlib import Path
import subprocess
import sys


def test_memory_vector_module_import_and_fallback_without_numpy():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "project_guardian" / "memory_vector_search.py"

    script = f"""
import builtins
import importlib.util

_real_import = builtins.__import__


def _without_numpy(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "numpy" or name.startswith("numpy."):
        raise ImportError("NumPy deliberately unavailable for regression test")
    return _real_import(name, globals, locals, fromlist, level)


builtins.__import__ = _without_numpy

spec = importlib.util.spec_from_file_location(
    "memory_vector_search_optional_numpy_regression",
    {str(module_path)!r},
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

assert module.HAS_NUMPY is False

embedder = module.SimpleEmbedder()
embedding = embedder.embed("alpha beta", dimension=8)
assert isinstance(embedding, list)
assert len(embedding) == 8

search = module.MemoryVectorSearch(use_faiss=False)
search.add_memory("memory-1", "alpha beta gamma")
results = search.search_similar("alpha", limit=3)

assert results
assert results[0][0] == "memory-1"
"""

    env = os.environ.copy()
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, (
        "memory_vector_search should import and use its fallback when NumPy is unavailable.\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )

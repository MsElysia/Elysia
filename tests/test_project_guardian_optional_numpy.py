"""Package import must succeed when optional NumPy is unavailable.

NumPy is not a core requirement. memory_vector_search treats it as optional
and falls back to hash embeddings. This regression blocks NumPy the way
scripts/tests/test_memory_vector_optional_numpy.py does on PR #78, then
imports the full project_guardian package rather than the module alone.
"""

import subprocess
import sys


def test_project_guardian_imports_when_numpy_unavailable():
    script = r"""
import builtins
import importlib.util
import json
import tempfile
from pathlib import Path

_real_import = builtins.__import__


def _without_numpy(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "numpy" or name.startswith("numpy."):
        raise ImportError("NumPy deliberately unavailable for regression test")
    return _real_import(name, globals, locals, fromlist, level)


builtins.__import__ = _without_numpy

spec = importlib.util.find_spec("numpy")
print("numpy_import_blocked", spec)

import project_guardian
from project_guardian import *

assert project_guardian.GuardianCore is GuardianCore
for name in project_guardian.__all__:
    assert name in globals(), name

from project_guardian.memory_vector_search import (
    HAS_NUMPY,
    MemoryVectorSearch,
    SimpleEmbedder,
)

assert HAS_NUMPY is False
embedding = SimpleEmbedder().embed("alpha beta", dimension=8)
assert isinstance(embedding, list)
assert len(embedding) == 8

search = MemoryVectorSearch(use_faiss=False)
search.add_memory("memory-1", "alpha beta gamma")
results = search.search_similar("alpha", limit=3)
assert results
assert results[0][0] == "memory-1"

from project_guardian.local_ingestion.chatgpt_export_ingest import (
    apply_chatgpt_export,
    preview_chatgpt_export,
)
from project_guardian.local_ingestion.memory_intelligence import (
    query_memory_intelligence,
)

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    export = root / "conversations.json"
    dest = root / "dest"
    export.write_text(
        json.dumps(
            [
                {
                    "title": "NumPy free memory test",
                    "id": "conv-no-numpy",
                    "current_node": "node-1",
                    "mapping": {
                        "node-1": {
                            "id": "node-1",
                            "message": {
                                "author": {"role": "user"},
                                "content": {"parts": ["Need a drywall quote from remembered context."]},
                                "create_time": 1700000001,
                            },
                        }
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)
    applied = apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)
    assert applied.report["memory_intelligence_created"] == 1
    hits = query_memory_intelligence(dest, "drywall quote")
    assert hits
    assert any(
        reason.get("type") == "text_relevance"
        for reason in hits[0]["recall_reasons"]
    )

print("optional_numpy_package_import_ok")
print("optional_numpy_memory_intelligence_ok")
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, (
        "project_guardian should import when NumPy is unavailable.\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
    assert "optional_numpy_package_import_ok" in completed.stdout
    assert "optional_numpy_memory_intelligence_ok" in completed.stdout

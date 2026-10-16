"""Main-port package isolation and the actual shared read-only memory bridge."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from project_guardian.brain.memory_intelligence_bridge import ReadOnlyMemoryIntelligenceBridge
from project_guardian.local_ingestion.memory_intelligence import (
    MemoryIntelligenceError, persist_source_intelligence,
)

ROOT = Path(__file__).resolve().parents[1]


def test_package_imports_remain_lazy_under_actual_process_guard(tmp_path):
    code = '''import sys,json
from pathlib import Path
from elysia_offline import install_offline_guard
denied=install_offline_guard(Path(sys.argv[1]))
import project_guardian, project_guardian.brain, project_guardian.local_ingestion, elysia
assert "project_guardian.core" not in sys.modules
assert "elysia.runtime" not in sys.modules
assert "GuardianCore" in project_guardian.__all__
assert set(elysia.__all__)=={"RuntimeConfig","ElysiaRuntime"}
assert denied==[]
print(json.dumps({"lazy":True,"denied":denied}))
'''
    env = {k: v for k, v in os.environ.items()
           if k.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT"}}
    env.update(TEMP=str(tmp_path), TMP=str(tmp_path), PYTHONUTF8="1")
    result = subprocess.run([sys.executable, "-S", "-B", "-c", code, str(tmp_path)],
                            cwd=ROOT, env=env, capture_output=True, text=True,
                            encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {"lazy": True, "denied": []}


def test_shared_bridge_clears_previous_recall_after_corrupted_source(tmp_path):
    persist_source_intelligence(dest_dir=tmp_path, raw_bytes=b"Fictional comet lantern color is amber.",
                                source_identity="elysia-fictional:comet")
    bridge = ReadOnlyMemoryIntelligenceBridge(tmp_path)
    assert bridge.retrieve("comet lantern")
    evidence = bridge.recall_evidence()
    highlight = evidence["hits"][0]["highlights"][0]["highlight_id"]
    assert "amber" in bridge.expand(highlight)["raw_source"]
    raw = next((tmp_path / "memory_intelligence/raw_sources").glob("*.bin"))
    raw.write_bytes(b"Altered unsupported evidence.")
    with pytest.raises(MemoryIntelligenceError):
        bridge.retrieve("comet lantern")
    assert bridge.recall_evidence()["hits"] == []
    with pytest.raises(MemoryIntelligenceError):
        bridge.expand(highlight)

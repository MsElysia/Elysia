"""Bounded end-to-end HTTP probe with a synthetic model peer."""
import json
from pathlib import Path
import subprocess
import sys


def test_actual_http_application_and_local_transport():
    result = subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('local_chat_http_probe.py'))],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert evidence['authorized_application_result']['tools_executed'][0]['result'] == '1680'
    assert evidence['stopped_peer_result']['ok'] is False

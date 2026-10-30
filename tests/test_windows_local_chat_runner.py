"""Contract regressions for offline Windows local-chat test isolation."""
from pathlib import Path
import os
import subprocess
import sys

from scripts.run_windows_offline_tests import (
    TEST_GUARD, TESTS, CHAT_TESTS, BROWSER_TESTS, HTTP_TESTS,
)


def test_coverage_is_explicit_and_unique():
    stages = (TESTS, CHAT_TESTS, BROWSER_TESTS, HTTP_TESTS)
    assert len({name for group in stages for name in group}) == sum(map(len, stages))
    assert set(("tests/test_local_memory_chat.py", "tests/test_local_chat_integration.py")) <= set(CHAT_TESTS)
    assert BROWSER_TESTS == ("tests/test_restricted_browser_bridge.py",)
    assert HTTP_TESTS == ("tests/test_local_chat_http.py",)


# Audit synthetic socket events rather than opening a real network connection.
# -S prevents an inherited sitecustomize from interfering with the child test.
CHILD = r"""
import os, sys
from scripts.run_windows_offline_tests import TEST_GUARD
exec(TEST_GUARD, {})
def accepted(event, *args):
    try:
        sys.audit(event, *args)
        return True
    except RuntimeError:
        return False

loopback = sys.argv[1] == "1"
assert accepted("socket.bind", None, ("127.0.0.1", 0)) == loopback
assert accepted("socket.connect", None, ("127.0.0.1", 50000)) == loopback
assert accepted("socket.getaddrinfo", "127.0.0.1", 50000) == loopback
# The allowance is frozen at startup; a test changing its environment
# cannot promote a strict process to a network-capable one.
os.environ["ELYSIA_CHAT_HTTP_FIXTURE"] = "0" if loopback else "1"
assert accepted("socket.connect", None, ("127.0.0.1", 50000)) == loopback
for event, args in (
    ("socket.bind", (None, ("0.0.0.0", 0))),
    ("socket.bind", (None, ("127.0.0.1", 50000))),
    ("socket.connect", (None, ("198.51.100.10", 443))),
    ("socket.connect", (None, ("127.0.0.2", 50000))),
    ("socket.getaddrinfo", ("example.invalid", 443)),
    ("socket.getaddrinfo", ("localhost", 50000)),
):
    assert not accepted(event, *args), (event, args)
assert not accepted("open", "/synthetic/api_keys.json", "r", 0)
assert not accepted("import", "project_guardian.api_key_manager")
"""


def test_default_network_denial_and_isolated_loopback_exception():
    root = Path(__file__).resolve().parents[1]
    for enabled in (False, True):
        env = os.environ.copy()
        env["ELYSIA_FORBIDDEN_LEARNING_CONFIG"] = str(root / "config/auto_learning.json")
        env.pop("ELYSIA_CHAT_HTTP_FIXTURE", None)
        if enabled:
            env["ELYSIA_CHAT_HTTP_FIXTURE"] = "1"
        result = subprocess.run(
            [sys.executable, "-S", "-B", "-c", CHILD, str(int(enabled))],
            cwd=root, env=env, capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, result.stdout + result.stderr

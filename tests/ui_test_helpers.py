"""Helpers for UI FastAPI tests behind local-only middleware."""

from __future__ import annotations

from typing import Any, Tuple

from fastapi.testclient import TestClient

# ASGI client tuples for TestClient (Starlette >= 0.27).
LOCAL_TEST_CLIENT: Tuple[str, int] = ("127.0.0.1", 50000)
REMOTE_TEST_CLIENT: Tuple[str, int] = ("192.168.1.5", 50000)


def local_test_client(app: Any, **kwargs: Any) -> TestClient:
    """Return TestClient that presents as loopback to local-only middleware."""
    kwargs.setdefault("client", LOCAL_TEST_CLIENT)
    return TestClient(app, **kwargs)

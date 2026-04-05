"""Status command for Elysia runtime."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Optional


def print_status(host: str = "127.0.0.1", port: int = 8123) -> None:
    """Print runtime status from the API."""
    data = _fetch_json(host, port, "/api/status")
    if data is None:
        print("Runtime not reachable.", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(data, indent=2))


def _fetch_json(host: str, port: int, path: str) -> Optional[dict]:
    """Fetch JSON from the API."""
    url = f"http://{host}:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError:
        return None
    except Exception:
        return None


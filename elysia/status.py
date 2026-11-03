"""Status command for Elysia runtime."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


def read_status(
    host: str = "127.0.0.1", port: int = 8123, timeout: float = 5
) -> tuple[int, object, str]:
    """Read GET /api/status.

    Returns ``(http_status, parsed_body, raw_text)``. ``http_status`` is 0 when
    the server does not respond; ``raw_text`` is then the connection error.
    """
    url = f"http://{host}:{port}/api/status"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    except Exception as exc:
        return 0, None, str(exc)

    try:
        body = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        body = None
    return status, body, raw


def print_status(host: str = "127.0.0.1", port: int = 8123) -> None:
    """Print runtime status from the API."""
    status, body, raw = read_status(host, port)
    if status == 0:
        print("Runtime not reachable.", file=sys.stderr)
        sys.exit(1)
    if status != 200 or not isinstance(body, dict):
        error = body.get("error") if isinstance(body, dict) else None
        print(f"[error] HTTP {status}: {error or raw}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(body, indent=2))


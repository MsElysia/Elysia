"""Pure contract helpers for a future local-only Memory dashboard route.

This module does not implement or register a web route. It only centralizes the
allowlist and validation rules future route code must satisfy before serving any
static Memory prototype HTML.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import unquote

ALLOWED_STATIC_MEMORY_PAGES: Tuple[str, ...] = (
    "index.html",
    "memory_hub.html",
    "memory_import_screen.html",
    "memory_review_search.html",
    "memory_first_run_setup.html",
    "memory_safety.html",
    "memory_diagnostics.html",
)

EXPECTED_FUTURE_ROUTES: Tuple[str, ...] = (
    "GET /memory",
    "GET /memory/",
    "GET /memory/<allowlisted_page>",
)

FORBIDDEN_PATH_EXAMPLES: Tuple[str, ...] = (
    "dashboard.html",
    "elysia.py",
    "config.json",
    "anything.exe",
    "memory_unknown.html",
    "../config/autonomy.json",
    "..\\config\\autonomy.json",
    "memory/../../secret.txt",
    "%2e%2e/config/autonomy.json",
    "%252e%252e/config/autonomy.json",
    "memory_hub.html%00.txt",
    "C:\\Users\\example\\secret.txt",
    "/etc/passwd",
    "F:\\ElysiaMemory\\secret.txt",
    ".",
    "..",
    "/",
    "project_guardian/ui/static/",
)

SAFETY_FLAGS = {
    "model_called": False,
    "embeddings_used": False,
    "live_memory_written": False,
    "autonomy_enabled": False,
}

COMMAND_EXECUTION_ENABLED = False
FILE_WRITES_ENABLED = False
BACKEND_MEMORY_COMMANDS_ENABLED = False
DIAGNOSTICS_DEMO_BROWSER_EXECUTION_ENABLED = False
ACCOUNT_API_NETWORK_ACCESS_ENABLED = False
LIVE_MEMORY_VECTOR_WRITES_ENABLED = False


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def static_memory_directory() -> Path:
    return repository_root() / "project_guardian" / "ui" / "static"


def _decoded_variants(value: str) -> Tuple[str, ...]:
    variants = [value]
    current = value
    for _ in range(2):
        decoded = unquote(current)
        variants.append(decoded)
        if decoded == current:
            break
        current = decoded
    return tuple(variants)


def is_safe_static_memory_page_name(value: object) -> bool:
    """Return True only for exact allowlisted Memory static HTML filenames."""
    if not isinstance(value, str):
        return False
    if value != value.strip() or not value:
        return False

    variants = _decoded_variants(value)
    if any(decoded != value for decoded in variants):
        return False

    forbidden_fragments = (
        "\x00",
        "/",
        "\\",
        ":",
        "?",
        "#",
        "..",
        "%",
    )
    if any(fragment in value for fragment in forbidden_fragments):
        return False

    path = Path(value)
    if path.name != value or path.is_absolute():
        return False

    return value in ALLOWED_STATIC_MEMORY_PAGES


def resolve_static_memory_page(value: object) -> Optional[Path]:
    """Resolve an allowlisted page to the fixed static directory, or None."""
    if not is_safe_static_memory_page_name(value):
        return None

    static_dir = static_memory_directory().resolve()
    candidate = (static_dir / str(value)).resolve()
    try:
        candidate.relative_to(static_dir)
    except ValueError:
        return None
    if candidate.name not in ALLOWED_STATIC_MEMORY_PAGES:
        return None
    return candidate

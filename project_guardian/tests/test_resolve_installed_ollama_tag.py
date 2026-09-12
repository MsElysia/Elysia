"""resolve_installed_ollama_tag: pool-first + same-base fallback when canonical tag is missing."""

from __future__ import annotations

from project_guardian.planner_readiness import resolve_installed_ollama_tag


def test_resolve_prefers_pool_member_when_canonical_missing():
    got = resolve_installed_ollama_tag(
        "llama3.2:3b",
        ["llama3.2:3b", "qwen2.5:3b-instruct"],
        ["qwen2.5:3b-instruct", "nomic-embed-text:latest"],
    )
    assert got == "qwen2.5:3b-instruct"


def test_resolve_same_base_prefers_sole_latest():
    got = resolve_installed_ollama_tag(
        "llama3.2:3b",
        ["llama3.2:3b"],
        ["llama3.2:latest", "llama3.2:1b"],
    )
    assert got == "llama3.2:latest"


def test_resolve_returns_none_when_exact_canonical_installed():
    assert (
        resolve_installed_ollama_tag(
            "mistral:7b",
            ["mistral:7b"],
            ["mistral:7b"],
        )
        is None
    )


def test_resolve_stable_sort_when_multiple_same_base_no_latest():
    got = resolve_installed_ollama_tag(
        "llama3.2:3b",
        ["llama3.2:3b"],
        ["llama3.2:8b", "llama3.2:1b"],
    )
    assert got == "llama3.2:1b"

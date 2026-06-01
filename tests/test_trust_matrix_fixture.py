"""Regression guard: TrustMatrix test fixtures must pass MemoryCore."""

import pytest

from project_guardian.memory import MemoryCore
from project_guardian.trust import TrustMatrix


def test_trust_matrix_requires_memory_argument():
    with pytest.raises(TypeError):
        TrustMatrix()  # noqa: B018 — intentional constructor contract check


def test_trust_matrix_accepts_memory_core():
    memory = MemoryCore()
    trust = TrustMatrix(memory)
    assert trust.memory is memory

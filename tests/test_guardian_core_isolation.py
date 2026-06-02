"""Regression: GuardianCore singleton state must not leak between tests."""

import pytest

from project_guardian.core import GuardianCore
from tests.guardian_core_test_helpers import reset_guardian_core_test_state


def test_sequential_guardian_core_construction_with_reset():
    config = {
        "enable_vector_memory": False,
        "enable_resource_monitoring": False,
    }
    for _ in range(3):
        reset_guardian_core_test_state()
        core = GuardianCore(config=config)
        assert core is not None


def test_guardian_core_blocks_second_instance_without_reset():
    reset_guardian_core_test_state()
    config = {
        "enable_vector_memory": False,
        "enable_resource_monitoring": False,
    }
    GuardianCore(config=config)
    with pytest.raises(RuntimeError, match="already exists"):
        GuardianCore(config=config)

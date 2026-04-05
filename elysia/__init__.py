"""
Unified Elysia runtime package.

Provides the command-line interface (`python -m elysia`) and runtime
orchestration used to power the "god switch" workflow described in the
implementation plan.
"""

from .config import RuntimeConfig
from .runtime import ElysiaRuntime

__all__ = ["RuntimeConfig", "ElysiaRuntime"]


"""Lifetime ownership for the restricted runtime; no PID files or process kills."""
from contextlib import contextmanager, ExitStack
import os
from pathlib import Path

from project_guardian.local_ingestion.apply_transaction import (
    ApplyTransactionError, _posix_lock, _windows_mutex, _windows_mutex_name,
)


class RuntimeOwnershipError(RuntimeError):
    pass


@contextmanager
def runtime_owner(code_root):
    """One cooperating runtime per checkout, released by exit or process death.

    Lock the existing code directory, separately from each memory transaction.
    Acquisition creates no files and happens before synthetic store creation.
    The Windows mutex derives from directory identity, not a guessed PID.
    """
    root = Path(code_root).absolute()
    for item in (root, *root.parents):
        if (item.is_symlink()
                or (hasattr(item, "is_junction") and item.is_junction())
                or getattr(item.lstat(), "st_file_attributes", 0) & 0x400):
            raise RuntimeOwnershipError("Linked runtime checkout refused.")
    if not root.is_dir() or root.resolve() != root:
        raise RuntimeOwnershipError("Canonical runtime checkout required.")
    if os.name == "nt":
        lock = _windows_mutex(_windows_mutex_name(root) + ".RestrictedRuntime")
    elif os.name == "posix":
        lock = _posix_lock(root)
    else:
        raise RuntimeOwnershipError("Runtime ownership is unsupported on this platform.")
    with ExitStack() as stack:
        try:
            stack.enter_context(lock)
        except (ApplyTransactionError, OSError) as exc:
            raise RuntimeOwnershipError(
                "Runtime ownership unavailable: another Elysia session may already own "
                "this checkout. Close that session normally, then retry. No process was stopped."
            ) from exc
        yield

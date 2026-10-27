"""Fail-closed delivery identity regressions."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PILOT_DIR = Path(__file__).resolve().parents[1]
if str(PILOT_DIR) not in sys.path:
    sys.path.insert(0, str(PILOT_DIR))

import pilot_identity as ident  # noqa: E402


class TestDeliveryIdentity(unittest.TestCase):
    def test_git_status_nonzero_fail_closed(self):
        with patch.object(
            ident,
            "_GIT_RUNNER",
            side_effect=[
                Mock(returncode=0, stdout="a" * 40 + "\n", stderr=""),
                Mock(returncode=128, stdout="", stderr="fatal: status failed"),
            ],
        ):
            info = ident.read_delivery_identity(Path("C:/does/not/matter"))
        self.assertFalse(info["exact_verified_delivery"])
        self.assertEqual(info["delivery_status"], "git_status_failed")
        self.assertIn("rc=128", info["identity_diagnostic"])

    def test_git_timeout_fail_closed(self):
        with patch.object(
            ident,
            "_GIT_RUNNER",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=1),
        ):
            info = ident.read_delivery_identity(Path("C:/x"))
        self.assertFalse(info["exact_verified_delivery"])
        self.assertEqual(info["delivery_status"], "git_timeout")

    def test_git_unavailable_fail_closed(self):
        with patch.object(
            ident, "_GIT_RUNNER", side_effect=OSError("git missing")
        ):
            info = ident.read_delivery_identity(Path("C:/x"))
        self.assertFalse(info["exact_verified_delivery"])
        self.assertEqual(info["delivery_status"], "git_unavailable")

    def test_malformed_head_fail_closed(self):
        with patch.object(
            ident,
            "_GIT_RUNNER",
            side_effect=[
                Mock(returncode=0, stdout="NOT_A_SHA\n", stderr=""),
            ],
        ):
            info = ident.read_delivery_identity(Path("C:/x"))
        self.assertFalse(info["exact_verified_delivery"])
        self.assertEqual(info["delivery_status"], "git_head_malformed")

    def test_truncated_or_padded_hex_head_not_exact(self):
        for length in (7, 41, 64):
            with self.subTest(length=length):
                with patch.object(
                    ident,
                    "_GIT_RUNNER",
                    side_effect=[
                        Mock(returncode=0, stdout=("a" * length) + "\n", stderr=""),
                        Mock(returncode=0, stdout="", stderr=""),
                    ],
                ):
                    info = ident.read_delivery_identity(Path("C:/x"))
                self.assertFalse(info["exact_verified_delivery"])
                self.assertEqual(info["delivery_status"], "git_head_malformed")

    def test_real_fixture_clean_dirty_untracked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "product.py").write_text("frozen=1\n", encoding="utf-8")
            subprocess.run(["git", "add", "product.py"], cwd=root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=f@example.invalid",
                    "commit",
                    "-qm",
                    "fixture",
                ],
                cwd=root,
                check=True,
            )
            clean = ident.read_delivery_identity(root)
            self.assertTrue(clean["exact_verified_delivery"])
            (root / "product.py").write_text("frozen=2\n", encoding="utf-8")
            dirty = ident.read_delivery_identity(root)
            self.assertFalse(dirty["exact_verified_delivery"])
            (root / "product.py").write_text("frozen=1\n", encoding="utf-8")
            (root / "new_product.py").write_text("new=1\n", encoding="utf-8")
            untracked = ident.read_delivery_identity(root)
            self.assertFalse(untracked["exact_verified_delivery"])


if __name__ == "__main__":
    unittest.main()

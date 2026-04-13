#!/usr/bin/env python3
"""
Diagnostic-only: validate two-USB memory policies without changing Elysia behavior.

Simulates four USB presence scenarios by patching find_elysia_memory_drives() and
MemoryStorageConfig._is_root_usable() to use temp folder "volumes" FAKE_PRI / FAKE_SEC.

Run from project root:
  python scripts/diagnose_two_usb_memory.py
"""

from __future__ import annotations

import io
import logging
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORE = PROJECT_ROOT / "core_modules" / "elysia_core_comprehensive"
# Project-root elysia_config must precede core_modules duplicate; memory_storage_config lives under CORE.
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(PROJECT_ROOT))


def _emit_elysia_style_usb_logs(cfg: dict, elysia_logger: logging.Logger) -> None:
    """Same messages as elysia.py after get_elysia_config()."""
    if not cfg.get("usb_memory_policy"):
        return
    pol = cfg.get("usb_memory_policy")
    pdrv = cfg.get("usb_primary_drive", "")
    sdrv = cfg.get("usb_secondary_drive") or "(none)"
    pa = cfg.get("usb_primary_available")
    sa = cfg.get("usb_secondary_available")
    sp = cfg.get("storage_path")
    targets = cfg.get("usb_active_write_targets") or [sp]
    elysia_logger.info(
        "[USBMemory] policy=%s primary=%s available=%s secondary=%s available=%s active_write_targets=%s",
        pol,
        pdrv,
        pa,
        sdrv,
        sa,
        targets,
    )
    if cfg.get("usb_archive_root"):
        elysia_logger.info("[USBMemory] archive_root=%s", cfg.get("usb_archive_root"))
    if cfg.get("usb_storage_degraded"):
        for note in cfg.get("usb_degraded_notes") or []:
            elysia_logger.warning("[USBMemory] degraded: %s", note)


def _usable_factory(scenario: str, pri_vol: Path, sec_vol: Path):
    """Simulate USB present/absent per root (must distinguish primary vs secondary paths)."""

    def _usable(self, root: Path) -> bool:
        try:
            rp = root.resolve()
        except OSError:
            rp = root
        p_root = (pri_vol / "ElysiaMemory").resolve()
        s_root = (sec_vol / "ElysiaMemory").resolve()
        is_p = rp == p_root
        is_s = rp == s_root
        if scenario == "both":
            ok = is_p or is_s
        elif scenario == "primary_only":
            ok = is_p
        elif scenario == "secondary_only":
            ok = is_s
        elif scenario == "neither":
            ok = False
        else:
            ok = False
        if ok:
            try:
                root.mkdir(parents=True, exist_ok=True)
                t = root / ".elysia_diag"
                t.write_text("x", encoding="utf-8")
                t.unlink(missing_ok=True)
            except OSError:
                return False
        return ok

    return _usable


def _run_scenario(
    scenario: str,
    policy: str,
    pri_vol: Path,
    sec_vol: Path,
    elysia_logger: logging.Logger,
) -> dict:
    os.environ["ELYSIA_USB_MEMORY_POLICY"] = policy
    # Ensure discovery does not use real drives for this run
    for k in ("ELYSIA_THUMB_DRIVE", "ELYSIA_THUMB_DRIVE_SECONDARY"):
        os.environ.pop(k, None)

    def _fake_find():
        return str(pri_vol), str(sec_vol)

    import elysia_config
    from memory_storage_config import MemoryStorageConfig

    with patch.object(elysia_config, "find_elysia_memory_drives", _fake_find):
        with patch.object(
            MemoryStorageConfig, "_is_root_usable", _usable_factory(scenario, pri_vol, sec_vol)
        ):
            cfg = elysia_config.get_elysia_config()

    _emit_elysia_style_usb_logs(cfg, elysia_logger)
    return cfg


def _mirror_write_probe(cfg: dict, pri_vol: Path, sec_vol: Path) -> dict:
    """Check whether notify_usb_persist_mirror copies only the JSON file."""
    from memory_storage_config import notify_usb_persist_mirror

    mem = Path(cfg["memory_filepath"])
    mem.parent.mkdir(parents=True, exist_ok=True)
    mem.write_text('["probe"]', encoding="utf-8")
    decoy_pri = mem.parent / "enhanced_trust.json"
    decoy_pri.write_text("{}", encoding="utf-8")
    notify_usb_persist_mirror(str(mem))

    sec_mem = sec_vol / "ElysiaMemory" / "guardian_memory.json"
    sec_trust = sec_vol / "ElysiaMemory" / "enhanced_trust.json"
    return {
        "secondary_has_guardian_memory": sec_mem.is_file(),
        "secondary_has_trust": sec_trust.is_file(),
        "mirror_copied_only_json": sec_mem.is_file() and not sec_trust.is_file(),
    }


def main() -> int:
    saved_policy = os.environ.get("ELYSIA_USB_MEMORY_POLICY")
    saved_p = os.environ.get("ELYSIA_THUMB_DRIVE")
    saved_s = os.environ.get("ELYSIA_THUMB_DRIVE_SECONDARY")

    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(logging.Formatter("%(name)s - %(levelname)s - %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    elysia_log = logging.getLogger("elysia")
    elysia_log.setLevel(logging.INFO)
    mem_log = logging.getLogger("memory_storage_config")
    mem_log.setLevel(logging.INFO)

    import tempfile
    import importlib

    # --- Unpatched baseline first (env not polluted by simulations) ---
    print("=== UNPATCHED BASELINE (this machine, real discovery) ===\n")
    for k in ("ELYSIA_USB_MEMORY_POLICY", "ELYSIA_THUMB_DRIVE", "ELYSIA_THUMB_DRIVE_SECONDARY"):
        os.environ.pop(k, None)
    os.environ["ELYSIA_USB_MEMORY_POLICY"] = "failover"
    import elysia_config

    importlib.reload(elysia_config)
    real_cfg = elysia_config.get_elysia_config()
    real_handler_out = io.StringIO()
    h2 = logging.StreamHandler(real_handler_out)
    h2.setFormatter(logging.Formatter("%(name)s - %(levelname)s - %(message)s"))
    elysia_log.addHandler(h2)
    _emit_elysia_style_usb_logs(real_cfg, elysia_log)
    elysia_log.removeHandler(h2)
    print(real_handler_out.getvalue().strip() or "(no usb fields)")
    print(f"storage_path={real_cfg.get('storage_path')}")
    print()

    results = []
    policies = ("failover", "mirror", "split")

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        pri_vol = base / "FAKE_PRI"
        sec_vol = base / "FAKE_SEC"
        pri_vol.mkdir()
        sec_vol.mkdir()

        for scenario in ("both", "primary_only", "secondary_only", "neither"):
            for policy in policies:
                buf_before = log_stream.tell()
                cfg = _run_scenario(scenario, policy, pri_vol, sec_vol, elysia_log)
                log_snippet = log_stream.getvalue()[buf_before:]

                mirror_probe = {}
                if policy == "mirror" and scenario == "both":
                    mirror_probe = _mirror_write_probe(cfg, pri_vol, sec_vol)

                active = cfg.get("storage_path", "")
                results.append(
                    {
                        "scenario": scenario,
                        "policy": policy,
                        "active_root": active,
                        "degraded": cfg.get("usb_storage_degraded", False),
                        "notes": cfg.get("usb_degraded_notes") or [],
                        "targets": cfg.get("usb_active_write_targets"),
                        "archive_root": cfg.get("usb_archive_root") or "",
                        "log_snippet": log_snippet.strip(),
                        "mirror_probe": mirror_probe,
                    }
                )

    # Restore caller environment
    def _restore_env(key: str, val):
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val

    _restore_env("ELYSIA_USB_MEMORY_POLICY", saved_policy)
    _restore_env("ELYSIA_THUMB_DRIVE", saved_p)
    _restore_env("ELYSIA_THUMB_DRIVE_SECONDARY", saved_s)

    print("=== SIMULATED SCENARIOS (FAKE_PRI / FAKE_SEC volumes) ===\n")
    # Print full table
    for r in results:
        mp = r.get("mirror_probe") or {}
        mp_s = ""
        if mp:
            mp_s = f" mirror_probe={mp}"
        print(
            f"[{r['scenario']:14} / {r['policy']:8}] active={r['active_root']!s} "
            f"degraded={r['degraded']} archive={r['archive_root']!s}{mp_s}"
        )
        if r["notes"]:
            for n in r["notes"]:
                print(f"    note: {n}")

    print("\n--- Sample [USBMemory] lines (first simulated row with elysia USB line) ---")
    for r in results:
        for line in r["log_snippet"].split("\n"):
            if "[USBMemory] policy=" in line:
                print(line)
                break
        else:
            continue
        break

    print("\n--- Full log snippet: both + mirror ---")
    for r in results:
        if r["scenario"] == "both" and r["policy"] == "mirror":
            print(r["log_snippet"])
            if r.get("mirror_probe"):
                print("mirror_probe:", r["mirror_probe"])
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

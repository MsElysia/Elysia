# Elysia Verified Pilot — delivery handoff for Codex

Date: 2026-10-25. Separate usable installation. Original Elysia shortcut/install untouched.

## Pilot candidate

| Item | Value |
|------|--------|
| Verified source SHA | `6b03b7d645e092c336564fb65bf2d5339a047c8e` |
| Delivery branch | `cursor/elysia-verified-pilot-delivery-001` |
| Pilot checkout | `C:\Users\Owner\Elysia-Verified-Pilot` |
| Persistent data (outside source) | `C:\Users\Owner\Elysia-Verified-Pilot-Data` |
| Interpreter (read-only) | `C:\Users\Owner\Project guardian\.venv\Scripts\python.exe` |
| Desktop shortcut | `C:\Users\Owner\Desktop\Elysia Verified Pilot.lnk` → `pilot\START_ELYSIA_VERIFIED_PILOT.bat` |
| Preferred UI | `http://127.0.0.1:5065/` (scan 5066–5085 if busy; never kill unknown listeners) |

## Delivery changes (bounded)

Under `pilot/` only:
- `pilot_paths.py`, `launch_verified_pilot.py`, `stop_verified_pilot.py`
- `START_ELYSIA_VERIFIED_PILOT.bat`, `STOP_ELYSIA_VERIFIED_PILOT.bat`
- `PILOT.md`

No protected-gate edits. No primary venv modification. Contained entry `scripts/start_contained_browser_memory.py` reused with `--enable-ui --auto-start-ui --keep-alive` and `ELYSIA_DISPOSABLE_ROOT` = pilot data root.

## Shortcut workflow test (PASS)

Evidence: `logs/shortcut-workflow.json`, `logs/stop-port.json`

1. Started **through desktop shortcut** → PID recorded, port 5065 listening  
2. Browser: save Silverbrook → retrieve → correct Mistvale → history (2 revs / 1 current)  
3. `STOP_ELYSIA_VERIFIED_PILOT.bat` → pilot-owned PID only; **5065 released**  
4. Relaunch through shortcut → recall Mistvale + history; **1** unique fact id (`fact_bd8d50e0d5484d2f`); no duplicates  

## Launch / stop

```text
Start:  Desktop "Elysia Verified Pilot"  OR  C:\Users\Owner\Elysia-Verified-Pilot\pilot\START_ELYSIA_VERIFIED_PILOT.bat
Stop:   C:\Users\Owner\Elysia-Verified-Pilot\pilot\STOP_ELYSIA_VERIFIED_PILOT.bat
```

Stop refuses PIDs that are not python / not pilot-owned (marker, contained entry, or pilot data path in cmdline).

## Security note

Loopback contained pilot. Autonomy/providers/learning workers/external storage disabled. Privileged routes gated. **Do not represent the legacy dashboard as fully secure.**

## Rollback

1. Run STOP bat  
2. Delete only `Elysia Verified Pilot.lnk`  
3. Optional: remove `Elysia-Verified-Pilot-Data` and `git worktree remove` the pilot checkout  

## Codex next

Independent verify: launch via shortcut, confirm contained disables, fact persistence after stop/relaunch, stop affects only pilot PID, original launcher unchanged.

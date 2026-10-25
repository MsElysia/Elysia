# Elysia Verified Pilot

Separate contained installation for the Windows browser-memory acceptance candidate.

| Item | Value |
|------|--------|
| Source SHA | `6b03b7d645e092c336564fb65bf2d5339a047c8e` |
| Source checkout | `C:\Users\Owner\Elysia-Verified-Pilot` |
| Persistent data | `C:\Users\Owner\Elysia-Verified-Pilot-Data` (outside source) |
| Interpreter | `C:\Users\Owner\Project guardian\.venv\Scripts\python.exe` (read-only; not modified) |
| Preferred UI | `http://127.0.0.1:5065/` (scans 5066–5085 if busy; never kills unknown listeners) |
| Entry | `scripts/start_contained_browser_memory.py` with `--enable-ui --auto-start-ui --keep-alive` |

## Launch / stop

- Start: `pilot\START_ELYSIA_VERIFIED_PILOT.bat` or desktop **Elysia Verified Pilot**
- Stop: `pilot\STOP_ELYSIA_VERIFIED_PILOT.bat` (pilot PID file only)

## Security posture

Loopback contained runtime. Autonomy / providers / online learning / external storage / background workers disabled via contained config. Privileged routes gated. **The legacy dashboard is not fully secure** — keep loopback-only.

## Rollback

1. Run `STOP_ELYSIA_VERIFIED_PILOT.bat`
2. Delete desktop shortcut `Elysia Verified Pilot.lnk` only
3. Optionally remove `C:\Users\Owner\Elysia-Verified-Pilot-Data` and the worktree  
   (`git worktree remove` from primary repo). Original Elysia install/shortcut untouched.

# Elysia Verified Pilot

Separate contained installation for the Windows browser-memory acceptance candidate.

| Item | Value |
|------|--------|
| Application base SHA | `6b03b7d645e092c336564fb65bf2d5339a047c8e` |
| Delivery commit | Reported at launch from `git rev-parse HEAD` — only “exact verified” when the product tree is clean |
| Source checkout | Directory that contains this `pilot` folder |
| Persistent data | `C:\Users\Owner\Elysia-Windows-Integration-Data` (outside source; not the frozen verified-pilot store) |
| Interpreter | `C:\Users\Owner\Project guardian\.venv\Scripts\python.exe` (read-only; not modified) |
| Preferred UI | `http://127.0.0.1:5065/` (scans 5066–5085 if busy; never kills unknown listeners) |
| Entry | `scripts/start_contained_browser_memory.py` with `--enable-ui --auto-start-ui --keep-alive` |
| Local model | Optional `ELYSIA_LOCAL_MODEL` (launcher defaults to `llama3.2:3b` if unset). Loopback Ollama only; Ask local model + optional labor-calculator checkbox. No cloud fallback. |

## Launch / stop / inbox

- Start: `pilot\START_ELYSIA_VERIFIED_PILOT.bat` from this checkout
- Stop: `pilot\STOP_ELYSIA_VERIFIED_PILOT.bat`
- Stop ownership: PID/runtime marker alone never authorizes kill. Stop verifies live executable, entry point, disposable data root, and process creation time; prefers cooperative Ctrl+C + `shutdown.request`; hard-kill is PID-only (no tree) after re-check. Uncertain ownership is refused.
- Inbox folder: `C:\Users\Owner\Elysia-Windows-Integration-Data\inbox` (`.txt` / `.md` only)
- Inbox scan: **startup and manual only** (`SCAN_INBOX.bat` or automatic scan before UI spawn on launch). Not a background watcher. Browser upload / page drag-and-drop: **not implemented**.
- Manual `SCAN_INBOX.bat` refuses apply while a verified pilot is running (no cross-process MemoryCore lock).

## Security posture

Loopback contained runtime. Autonomy / providers / online learning / external storage / background workers disabled via contained config. Privileged routes gated. **The legacy dashboard is not fully secure** — keep loopback-only.

## Rollback

1. Run `STOP_ELYSIA_VERIFIED_PILOT.bat`
2. Delete desktop shortcut `Elysia Verified Pilot.lnk` only
3. Optionally remove `C:\Users\Owner\Elysia-Windows-Integration-Data` and this worktree  
   (`git worktree remove` from primary repo). Original Elysia install/shortcut untouched.

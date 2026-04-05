# Control Panel Initialization Fix

## Issue
The control panel was stuck showing "Initializing..." even though the ElysiaLoop was running.

## Root Cause
1. **GuardianCore** didn't set `_initialized` and `_running` flags
2. **Status endpoint** checked for `system.initialized` which was always `False`
3. **Control panel** showed "Initializing..." when `system.initialized` was `False`, even though the loop was running

## Fixes Applied

### 1. Fixed Status Display Logic (`ui_control_panel.py`)
- Changed priority: **Loop status > System status**
- If loop is running, show "Running" even if system.initialized is False
- Added fallback: if uptime > 0, assume system is running

### 2. Added Initialization Flags (`core.py`)
- Set `self._initialized = True` after system initialization
- Set `self._running = True` after system initialization
- Initialize flags to `False` in `__init__`

## Result
- Control panel now shows "Running" when ElysiaLoop is active
- Status updates correctly reflect system state
- No more stuck "Initializing..." message

## How It Works Now

When you start the control panel:
1. **GuardianCore** initializes all components
2. **ElysiaLoop** starts automatically
3. **Flags** are set: `_initialized = True`, `_running = True`
4. **Status endpoint** returns proper status
5. **Control panel** displays "Running" instead of "Initializing..."

## Testing
After these changes, refresh the control panel (Ctrl+F5) and you should see:
- Status: **Running** (green indicator)
- Loop Status: **running**
- Uptime: shows actual uptime in seconds


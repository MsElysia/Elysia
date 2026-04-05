@echo off
echo ========================================
echo Elysia Unified Interface Verification
echo ========================================
echo.
echo Starting unified interface...
echo This will verify:
echo   1. Architect-Core initializes without crash
echo   2. No second GuardianCore initialization
echo   3. Web dashboard opens once (no loops)
echo   4. Console remains responsive
echo   5. No heartbeat spam
echo.
echo Press Ctrl+C to stop
echo.
python run_elysia_unified.py

@echo off
REM =========================================================================
REM  auto_update.bat
REM  
REM  Auto-updater for the Experiment Tracking application.
REM  Defaults to continuous polling mode (checks GitHub every 5 minutes).
REM
REM  Usage:
REM    auto_update.bat                          - Poll mode (default, 5 min)
REM    auto_update.bat --interval 600           - Poll every 10 minutes
REM    auto_update.bat --once                   - Run a single check and exit
REM    auto_update.bat --restart-only           - Just restart Streamlit
REM
REM  For Windows Task Scheduler single-check mode, use --once.
REM =========================================================================

:: Change to the project directory (where this bat file lives)
cd /d "%~dp0"

:: Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not on PATH.
    pause
    exit /b 1
)

:: Activate virtual environment
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate
) else (
    echo [WARNING] Virtual environment not found at .venv - using system Python
)

:: Default to --poll mode if no arguments provided.
:: NOTE: cmd.exe does not support "else if", so we use labels/goto.
if "%~1"=="" goto RUN_POLL
if /I "%~1"=="--once" goto RUN_ONCE
goto RUN_WITH_ARGS

:RUN_POLL
echo Starting auto-updater in polling mode (Ctrl+C to stop)...
python -m utils.auto_updater --poll
goto AFTER_RUN

:RUN_ONCE
python -m utils.auto_updater
goto AFTER_RUN

:RUN_WITH_ARGS
python -m utils.auto_updater %*
goto AFTER_RUN

:AFTER_RUN

:: Capture exit code
set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% neq 0 (
    echo [ERROR] Auto-updater exited with code %EXIT_CODE%. Check logs\auto_updater.log for details.
)

pause
exit /b %EXIT_CODE%

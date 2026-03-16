@echo off
echo Starting Experiment Tracker Application...

:: Change to the project directory (where this bat file lives)
:: This ensures the script works regardless of where Windows launches it from
cd /d "%~dp0"

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed! Please install Python 3.8 or higher.
    pause
    exit /b 1
)

:: Activate virtual environment
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate
) else (
    echo Virtual environment not found at .venv!
    echo Run setup_lab_pc.bat first to create it.
    pause
    exit /b 1
)

:: Set environment variables (if needed)
set STREAMLIT_SERVER_PORT=8501
set STREAMLIT_SERVER_ADDRESS=0.0.0.0

:: Start the Streamlit application
:: --server.fileWatcherType none disables the watchdog file watcher,
:: which crashes on Python 3.13 due to threading changes.
:: Not needed in production — the auto-updater handles restarts.
echo Starting Streamlit application...
python -m streamlit run app.py --server.fileWatcherType none
if errorlevel 1 (
    echo Failed to start Streamlit application!
    pause
    exit /b 1
)

:: Keep the window open if there's an error
pause
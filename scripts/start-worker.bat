@echo off
setlocal
echo Starting arq background worker...
cd /d "%~dp0..\backend"
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Backend venv missing. Run scripts\setup.bat first.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
set PYTHONPATH=%CD%
python -m arq app.worker.WorkerSettings
endlocal

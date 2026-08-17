@echo off
setlocal
echo Starting FastAPI backend on http://localhost:8000 ...
cd /d "%~dp0..\backend"
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Backend venv missing. Run scripts\setup.bat first.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
set PYTHONPATH=%CD%
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
endlocal

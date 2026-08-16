@echo off
echo Starting FastAPI backend on http://localhost:8000 ...
cd /d "%~dp0..\backend"
call venv\Scripts\activate.bat
set PYTHONPATH=%~dp0..\backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

@echo off
echo Starting arq background worker...
cd /d "%~dp0..\backend"
call venv\Scripts\activate.bat
set PYTHONPATH=%~dp0..\backend
python -m arq app.worker.WorkerSettings

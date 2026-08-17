@echo off
setlocal
echo ================================================
echo  Autonomous Code Review Agent - Windows Setup
echo ================================================
echo.
echo This project runs natively on Windows (no Docker).
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ from https://python.org
    pause
    exit /b 1
)
echo [OK] Python found

:: Check Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install Node.js 20+ from https://nodejs.org
    pause
    exit /b 1
)
echo [OK] Node.js found

:: Check PostgreSQL
psql --version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] psql not in PATH. Install PostgreSQL and ensure it runs on port 5432.
) else (
    echo [OK] PostgreSQL client found
)

:: Check Redis
redis-cli ping >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Redis not responding on localhost:6379.
    echo           Install: winget install Redis.Redis
    echo           Or: https://github.com/microsoftarchive/redis/releases
) else (
    echo [OK] Redis responding
)

:: Ensure root .env exists
cd /d "%~dp0.."
if not exist ".env" (
    echo.
    echo [INFO] Creating .env from .env.example ...
    copy ".env.example" ".env" >nul
    echo [ACTION] Edit .env with your GitHub App and OpenRouter credentials.
)

echo.
echo --- Setting up Python backend ---
cd /d "%~dp0..\backend"

if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

echo Installing Python dependencies...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q
echo [OK] Backend dependencies installed

echo.
echo --- Setting up Frontend ---
cd /d "%~dp0..\frontend"
if not exist ".env.local" (
    if exist ".env.local.example" (
        copy ".env.local.example" ".env.local" >nul
        echo [OK] Created frontend\.env.local
    )
)
echo Installing Node.js dependencies...
call npm install
echo [OK] Frontend dependencies installed

echo.
echo --- Creating sandbox workspace directory ---
if not exist "%USERPROFILE%\coderev_sandboxes" (
    mkdir "%USERPROFILE%\coderev_sandboxes"
)
echo [OK] %USERPROFILE%\coderev_sandboxes

echo.
echo ================================================
echo  Setup complete!
echo.
echo  Next steps:
echo    1. Edit .env  (GitHub App + OpenRouter key)
echo    2. scripts\setup-db.bat
echo    3. scripts\start-all.bat
echo ================================================
pause
endlocal

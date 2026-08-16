@echo off
echo ================================================
echo  Autonomous Code Review Agent - Windows Setup
echo ================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)
echo [OK] Python found

:: Check Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install from https://nodejs.org
    pause
    exit /b 1
)
echo [OK] Node.js found

:: Check PostgreSQL
psql --version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] psql not in PATH. Make sure PostgreSQL is running on port 5432.
) else (
    echo [OK] PostgreSQL found
)

:: Check Redis
redis-cli ping >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Redis not responding. Install from https://github.com/microsoftarchive/redis/releases
    echo           or use: winget install Redis.Redis
) else (
    echo [OK] Redis found
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
pip install -r requirements.txt -q
echo [OK] Backend dependencies installed

echo.
echo --- Setting up Frontend ---
cd /d "%~dp0..\frontend"
echo Installing Node.js dependencies...
call npm install --silent
echo [OK] Frontend dependencies installed

echo.
echo ================================================
echo  Setup complete!
echo  Run scripts\start-all.bat to launch everything
echo ================================================
pause

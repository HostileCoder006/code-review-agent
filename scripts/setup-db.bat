@echo off
setlocal
echo ================================================
echo  Database Setup (native PostgreSQL)
echo ================================================
echo.
echo Make sure PostgreSQL is running on localhost:5432.
echo.

psql -U postgres -c "CREATE USER coderev WITH PASSWORD 'coderev';" 2>nul
psql -U postgres -c "CREATE DATABASE coderev OWNER coderev;" 2>nul
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE coderev TO coderev;" 2>nul
echo [OK] Database and user ready (coderev / coderev)

echo.
echo Creating tables...
cd /d "%~dp0..\backend"
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Backend venv missing. Run scripts\setup.bat first.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
set PYTHONPATH=%CD%
python scripts\init_db.py
if errorlevel 1 (
    echo [ERROR] Failed to create tables. Check DATABASE_URL in .env and that PostgreSQL is running.
    pause
    exit /b 1
)

echo.
echo Database setup complete!
pause
endlocal

@echo off
echo ================================================
echo  Database Setup
echo ================================================
echo.
echo Creating PostgreSQL database and user...

:: Create user and database (adjust if your postgres password is different)
psql -U postgres -c "CREATE USER coderev WITH PASSWORD 'coderev';" 2>nul
psql -U postgres -c "CREATE DATABASE coderev OWNER coderev;" 2>nul
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE coderev TO coderev;" 2>nul
echo [OK] Database ready

echo.
echo Running Alembic migrations...
cd /d "%~dp0..\backend"
call venv\Scripts\activate.bat
set PYTHONPATH=%~dp0..\backend
alembic upgrade head
echo [OK] Migrations complete

echo.
echo Database setup complete!
pause

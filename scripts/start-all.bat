@echo off
echo ================================================
echo  Autonomous Code Review Agent - Starting All
echo ================================================
echo.
echo This opens 3 terminal windows:
echo   1. Backend  (http://localhost:8000)
echo   2. Worker   (background job processor)
echo   3. Frontend (http://localhost:3000)
echo.

:: Backend
start "CodeRev - Backend" cmd /k "%~dp0start-backend.bat"
timeout /t 3 /nobreak >nul

:: Worker
start "CodeRev - Worker" cmd /k "%~dp0start-worker.bat"
timeout /t 2 /nobreak >nul

:: Frontend
start "CodeRev - Frontend" cmd /k "%~dp0start-frontend.bat"

echo.
echo All services started in separate windows.
echo.
echo  Backend API:  http://localhost:8000
echo  API Docs:     http://localhost:8000/docs
echo  Dashboard:    http://localhost:3000
echo.
echo Press any key to exit this window...
pause >nul

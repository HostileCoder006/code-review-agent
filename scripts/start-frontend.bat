@echo off
setlocal
echo Starting Next.js frontend on http://localhost:3000 ...
cd /d "%~dp0..\frontend"
if not exist "node_modules" (
    echo [ERROR] Frontend dependencies missing. Run scripts\setup.bat first.
    pause
    exit /b 1
)
if not exist ".env.local" (
    if exist ".env.local.example" copy ".env.local.example" ".env.local" >nul
)
npm run dev
endlocal

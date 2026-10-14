@echo off
setlocal

REM ============================================================
REM  Lab Report Review - One-click launcher
REM  Double-click to start backend + frontend and open browser
REM  Close the two new windows to stop the services
REM ============================================================

cd /d "%~dp0"

echo.
echo ============================================
echo   Lab Report Review - starting
echo ============================================
echo.

if not exist "backend\.venv\Scripts\python.exe" (
    echo [ERROR] Backend venv not found: backend\.venv\Scripts\python.exe
    echo.
    echo Run this once to set it up:
    echo     cd backend
    echo     python -m venv .venv
    echo     .venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo [ERROR] Frontend deps not installed: frontend\node_modules
    echo.
    echo Run this once to set it up:
    echo     cd frontend
    echo     npm ci
    echo.
    pause
    exit /b 1
)

echo [1/3] Starting backend on port 8000 ...
start "LabReportReview-Backend" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

timeout /t 4 /nobreak >nul

echo [2/3] Starting frontend on port 5173 ...
start "LabReportReview-Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev -- --host 127.0.0.1 --port 5173 --strictPort"

timeout /t 6 /nobreak >nul

echo [3/3] Opening browser ...
start "" "http://127.0.0.1:5173"

echo.
echo ============================================
echo   Started
echo --------------------------------------------
echo   UI:  http://127.0.0.1:5173
echo   API: http://127.0.0.1:8000/docs
echo.
echo   Keep the two new windows open while using.
echo   Close them to stop the services.
echo ============================================
echo.
echo This window closes in 5 seconds ...
timeout /t 5 /nobreak >nul
exit /b 0

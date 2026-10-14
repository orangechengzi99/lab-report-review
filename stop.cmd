@echo off
setlocal

REM ============================================================
REM  Lab Report Review - Stop the local servers
REM  Double-click to free ports 8000 and 5173
REM ============================================================

echo.
echo ============================================
echo   Lab Report Review - stopping services
echo ============================================
echo.

set FOUND=0

REM --- Stop processes listening on port 8000 (backend) ---
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:"LISTENING" ^| findstr /c:":8000"') do (
    echo Stopping backend  ^(PID %%p^) ...
    taskkill /PID %%p /F >nul 2>&1
    set FOUND=1
)

REM --- Stop processes listening on port 5173 (frontend) ---
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:"LISTENING" ^| findstr /c:":5173"') do (
    echo Stopping frontend ^(PID %%p^) ...
    taskkill /PID %%p /F >nul 2>&1
    set FOUND=1
)

if "%FOUND%"=="0" (
    echo Nothing was running on ports 8000 / 5173.
) else (
    echo.
    echo Done. Ports released.
)

echo.
echo Note: the old service windows may still be open.
echo       You can close them manually - they are no longer serving.
echo.
echo This window closes in 4 seconds ...
timeout /t 4 /nobreak >nul
exit /b 0

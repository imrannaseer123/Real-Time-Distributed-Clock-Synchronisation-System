@echo off
:: ═══════════════════════════════════════════════════════════
::  Distributed Clock Synchronisation System – Launcher
::  Runs: Time Server + 5 Clients + Web Dashboard
::  Usage: start_all.bat [cristian|berkeley]
:: ═══════════════════════════════════════════════════════════

setlocal

:: Default algorithm
set ALGO=cristian
if not "%~1"=="" set ALGO=%~1

:: Resolve the project directory (wherever this bat lives)
set PROJECT_DIR=%~dp0
cd /d "%PROJECT_DIR%"

echo.
echo  =========================================
echo   Distributed Clock Sync System Launcher
echo   Algorithm : %ALGO%
echo   Directory : %PROJECT_DIR%
echo  =========================================
echo.

:: ── 1. Kill any leftover python processes on our ports (optional cleanup) ───
echo [1/3] Cleaning up stale processes on ports 9000-9002, 9100-9104, 5050...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":9000 :9001 :9002 :9100 :9101 :9102 :9103 :9104 :5050" 2^>nul') do (
    taskkill /PID %%p /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

:: ── 2. Start Time Server ─────────────────────────────────────────────────────
echo [2/3] Starting Time Server (port 9000/9001/9002)...
start "Clock-Sync SERVER" cmd /k "cd /d %PROJECT_DIR% && python server.py"
timeout /t 2 /nobreak >nul

:: ── 3. Start 5 Clients ───────────────────────────────────────────────────────
echo [3/3] Starting 5 clients (algorithm: %ALGO%)...
start "Clock-Sync CLIENT-0" cmd /k "cd /d %PROJECT_DIR% && python client.py --id client-0 --port 9100 --algo %ALGO%"
timeout /t 1 /nobreak >nul
start "Clock-Sync CLIENT-1" cmd /k "cd /d %PROJECT_DIR% && python client.py --id client-1 --port 9101 --algo %ALGO%"
timeout /t 1 /nobreak >nul
start "Clock-Sync CLIENT-2" cmd /k "cd /d %PROJECT_DIR% && python client.py --id client-2 --port 9102 --algo %ALGO%"
timeout /t 1 /nobreak >nul
start "Clock-Sync CLIENT-3" cmd /k "cd /d %PROJECT_DIR% && python client.py --id client-3 --port 9103 --algo %ALGO%"
timeout /t 1 /nobreak >nul
start "Clock-Sync CLIENT-4" cmd /k "cd /d %PROJECT_DIR% && python client.py --id client-4 --port 9104 --algo %ALGO%"
timeout /t 2 /nobreak >nul

:: ── 4. Start Dashboard ───────────────────────────────────────────────────────
echo [4/4] Starting Web Dashboard (http://127.0.0.1:5050)...
start "Clock-Sync DASHBOARD" cmd /k "cd /d %PROJECT_DIR% && python dashboard/app.py"
timeout /t 2 /nobreak >nul

:: ── 5. Open browser ──────────────────────────────────────────────────────────
echo Opening dashboard in browser...
start "" "http://127.0.0.1:5050"

echo.
echo  =========================================
echo   All services started!
echo.
echo   Server     : localhost:9000 (Cristian)
echo               localhost:9001 (Berkeley)
echo   Dashboard  : http://127.0.0.1:5050
echo   Clients    : client-0 to client-4
echo   Algorithm  : %ALGO%
echo.
echo   Close the individual windows to stop.
echo   Or run:  taskkill /IM python.exe /F
echo  =========================================
echo.
pause
endlocal

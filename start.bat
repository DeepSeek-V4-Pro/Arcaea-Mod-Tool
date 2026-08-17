@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Arcaea Mod Tool
cd /d "%~dp0"

set "PORT=8000"
if defined AMT_PORT set "PORT=%AMT_PORT%"

echo ============================================
echo   Arcaea Mod Tool
echo ============================================

rem ---------- 1. locate python (venv first, then python, then py launcher) ----------
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
    where py >nul 2>nul && for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%i"
)
if not defined PY (
    echo [ERROR] Python not found. Please install Python 3.10+ and tick "Add to PATH":
    echo        https://www.python.org/downloads/
    pause
    exit /b 1
)

rem ---------- 2. version check ----------
"%PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python 3.10+ required. Current version:
    "%PY%" --version
    pause
    exit /b 1
)

rem ---------- 3. virtualenv: create if missing ----------
if not exist ".venv\Scripts\python.exe" (
    echo [SETUP] Creating virtualenv .venv ...
    "%PY%" -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtualenv. Please install a full Python build.
        pause
        exit /b 1
    )
    set "PY=.venv\Scripts\python.exe"
)

rem ---------- 4. dependencies: install if missing (CN mirrors first) ----------
"%PY%" -c "import fastapi,uvicorn,PIL,cryptography,apksigtool,apksigcopier,python_multipart" >nul 2>nul
if errorlevel 1 (
    echo [SETUP] Installing dependencies ^(mirrors auto-switch^)...
    for %%m in (https://pypi.tuna.tsinghua.edu.cn/simple https://mirrors.aliyun.com/pypi/simple/ https://pypi.org/simple) do (
        echo   trying: %%m
        "%PY%" -m pip install --disable-pip-version-check -q -i %%m -r requirements.txt >nul 2>nul
        if not errorlevel 1 goto deps_ok
    )
    echo [ERROR] Dependency install failed. Check your network and retry.
    pause
    exit /b 1
)
:deps_ok

rem ---------- 5. frontend: build if dist missing (requires Node.js) ----------
if not exist "webui\dist\index.html" (
    where node >nul 2>nul
    if not errorlevel 1 (
        echo [SETUP] Building frontend ^(first run takes 1-2 min^)...
        pushd webui
        if not exist "node_modules\vite\package.json" (
            call npm install --no-audit --no-fund
        )
        call npm run build
        popd
        if not exist "webui\dist\index.html" (
            echo [WARN] Frontend build failed. Backend API still works.
            echo        Retry manually: cd webui ^&^& npm install ^&^& npm run build
        )
    ) else (
        echo [WARN] Node.js not found, cannot build frontend.
        echo        Install Node.js then run: cd webui ^&^& npm install ^&^& npm run build
    )
)

rem ---------- 6. port conflict check ----------
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>nul
if not errorlevel 1 (
    echo [INFO] Port %PORT% is already in use ^(server may already be running^).
    start http://127.0.0.1:%PORT%
    echo Browser opened. Closing this window does not stop the server.
    echo This window will close automatically in 5 seconds...
    timeout /t 5 /nobreak >nul
    exit /b 0
)

rem ---------- 7. start backend in its own window ----------
echo [START] Starting server at http://127.0.0.1:%PORT% ...
start "Arcaea Mod Tool - server" cmd /k ""%PY%" -m app"

rem ---------- 8. wait until ready (max 60s) ----------
set /a TRY=0
:waitloop
set /a TRY+=1
if %TRY% gtr 60 (
    echo [WARN] Server did not become ready. Check the "Arcaea Mod Tool - server" window.
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
where curl >nul 2>nul
if errorlevel 1 (
    powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:%PORT%/api/config' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
) else (
    curl -s -o nul "http://127.0.0.1:%PORT%/api/config" >nul 2>nul
)
if errorlevel 1 goto waitloop

rem ---------- 9. ready, open browser ----------
echo [DONE] Server ready: http://127.0.0.1:%PORT%
start http://127.0.0.1:%PORT%
echo Browser opened. Closing this window does not stop the server;
echo to stop it, close the "Arcaea Mod Tool - server" window.
echo This window will close automatically in 5 seconds...
timeout /t 5 /nobreak >nul

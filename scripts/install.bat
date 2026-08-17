@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Arcaea Mod Tool - setup
cd /d "%~dp0.."

echo ============================================
echo   Arcaea Mod Tool setup
echo ============================================
echo   Tip: running start.bat does all of this automatically.
echo.

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
echo [1/3] Using Python: %PY%

rem ---------- 3. virtualenv ----------
if not exist ".venv\Scripts\python.exe" (
    echo [2/3] Creating virtualenv .venv ...
    "%PY%" -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtualenv. Please install a full Python build.
        pause
        exit /b 1
    )
    set "PY=.venv\Scripts\python.exe"
) else (
    echo [2/3] Virtualenv already exists
)

rem remove legacy fallback marker (start.bat now maintains the venv itself)
if exist ".venv\.fallback" del ".venv\.fallback" >nul 2>nul

rem ---------- 4. dependencies ----------
"%PY%" -c "import fastapi,uvicorn,PIL,cryptography,apksigtool,apksigcopier,python_multipart" >nul 2>nul
if not errorlevel 1 (
    echo [3/3] Dependencies ready
    goto done
)
echo [3/3] Installing dependencies (mirrors auto-switch)...
for %%m in (https://pypi.tuna.tsinghua.edu.cn/simple https://mirrors.aliyun.com/pypi/simple/ https://pypi.org/simple) do (
    echo   trying: %%m
    "%PY%" -m pip install --disable-pip-version-check -q -i %%m -r requirements.txt >nul 2>nul
    if not errorlevel 1 goto done
)
echo [ERROR] Dependency install failed. Check your network and retry.
pause
exit /b 1

:done
echo.
echo [DONE] Setup finished, launching start.bat ...
start "" cmd /c start.bat
pause
exit /b 0

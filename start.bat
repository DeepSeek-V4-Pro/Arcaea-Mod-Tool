@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting Arcaea Mod Tool...
rem 优先使用 venv；venv 不可用或依赖缺失时回退系统 Python
if exist ".venv\.fallback" (
    python -m app
    goto :eof
)
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -c "import fastapi,uvicorn,PIL,cryptography" >nul 2>nul
    if not errorlevel 1 (
        .venv\Scripts\python.exe -m app
        goto :eof
    )
)
python -m app
pause

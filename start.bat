@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem ---------- 前端构建(首次运行或 dist 缺失时自动构建) ----------
if not exist "webui\dist\index.html" (
    where node >nul 2>nul
    if not errorlevel 1 (
        echo [前端] 检测到界面未构建,开始构建(首次约需 1-2 分钟)...
        pushd webui
        call npm install --no-audit --no-fund
        call npm run build
        popd
    ) else (
        echo [警告] 未找到 Node.js,无法构建界面。
        echo        请安装 Node.js 后执行: cd webui ^&^& npm install ^&^& npm run build
    )
)

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

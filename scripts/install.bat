@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Arcaea Mod Tool - 一键安装
cd /d "%~dp0.."

echo ============================================
echo   Arcaea Mod Tool 一键安装
echo ============================================
echo.

rem ---------- 1. find python ----------
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
    where py >nul 2>nul && for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%i"
)
if not defined PY (
    echo [错误] 未找到 Python。请先安装 Python 3.10+：
    echo   方式1: https://www.python.org/downloads/ 安装时勾选 Add to PATH
    echo   方式2: 管理员 PowerShell 执行  winget install Python.Python.3.12
    pause
    exit /b 1
)
%PY% --version >nul 2>nul || (
    echo [错误] Python 不可用: %PY%
    pause
    exit /b 1
)
echo [1/4] 使用 Python: %PY%
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" || (
    echo [错误] 需要 Python 3.10 或更高版本
    pause
    exit /b 1
)

rem ---------- 2. venv ----------
set "VPY=.venv\Scripts\python.exe"
if not exist "%VPY%" (
    echo [2/4] 创建虚拟环境...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo   警告: venv 创建未完全成功，将尝试继续（部分 Python 发行版 ensurepip 异常）
    )
) else (
    echo [2/4] 虚拟环境已存在
)
if not exist "%VPY%" (
    echo [错误] 虚拟环境创建失败，请安装完整版 Python 后重试
    pause
    exit /b 1
)

rem ---------- 3. bootstrap pip if missing ----------
"%VPY%" -m pip --version >nul 2>nul
if errorlevel 1 (
    echo [3/4] venv 缺少 pip，使用系统 Python 引导安装依赖到 venv...
    %PY% -m pip install --disable-pip-version-check -q --target ".venv\Lib\site-packages" ^
        -r requirements.txt
    if errorlevel 1 (
        echo   引导到 venv 失败，回退：直接安装到系统 Python...
        %PY% -m pip install --disable-pip-version-check -q -r requirements.txt
        if errorlevel 1 (
            echo [错误] 依赖安装失败，请检查网络后重试
            pause
            exit /b 1
        )
        rem 回退模式：start.bat 将使用系统 Python
        echo system_fallback> .venv\.fallback
    ) else (
        echo   依赖已安装到 venv（pip 引导模式）
    )
    goto deps_ok
)

rem ---------- 4. pip install (CN mirrors first) ----------
echo [3/4] 安装依赖（国内镜像优先，失败自动切换）...
set "MIRRORS=https://pypi.tuna.tsinghua.edu.cn/simple https://mirrors.aliyun.com/pypi/simple/ https://pypi.doubanio.com/simple/ https://pypi.org/simple"
for %%m in (%MIRRORS%) do (
    echo   尝试镜像: %%m
    "%VPY%" -m pip install --disable-pip-version-check -i %%m -r requirements.txt >nul 2>nul
    if not errorlevel 1 goto deps_ok
)
echo [错误] 依赖安装失败，请检查网络后重试
pause
exit /b 1

:deps_ok

rem ---------- 5. verify imports ----------
"%VPY%" -c "import fastapi,uvicorn,PIL,cryptography" >nul 2>nul
if errorlevel 1 (
    echo [警告] 依赖验证未通过，尝试修复（pip 引导模式）...
    %PY% -m pip install --disable-pip-version-check -q --target ".venv\Lib\site-packages" ^
        -r requirements.txt >nul 2>nul
    "%VPY%" -c "import fastapi,uvicorn,PIL,cryptography" >nul 2>nul || (
        echo [警告] 依赖仍不完整，将使用系统 Python 启动
        echo system_fallback> .venv\.fallback
    )
)

rem ---------- 6. start script ----------
echo [4/4] 完成！正在启动...
if not exist "start.bat" (
    call :make_start
) else (
    rem 重新生成以确保解释器选择逻辑最新
    call :make_start
)
start "" cmd /c "start.bat"
timeout /t 2 >nul
echo 浏览器将打开 http://127.0.0.1:8000 （如未自动打开请手动访问）
start http://127.0.0.1:8000
pause
exit /b 0

:make_start
(
echo @echo off
echo chcp 65001 ^>nul
echo cd /d "%%~dp0"
echo if exist ".venv\.fallback" ^(
echo     python -m app
echo     goto :eof
echo ^)
echo if exist ".venv\Scripts\python.exe" ^(
echo     .venv\Scripts\python.exe -c "import fastapi,uvicorn,PIL,cryptography" ^>nul 2^>nul
echo     if not errorlevel 1 ^(
echo         .venv\Scripts\python.exe -m app
echo         goto :eof
echo     ^)
echo ^)
echo python -m app
echo pause
) > start.bat
exit /b 0

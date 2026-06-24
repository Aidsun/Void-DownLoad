@echo off
rem ============================================================
rem Void Downloader - EXE 打包脚本
rem ============================================================
setlocal

cd /d "%~dp0"

echo.
echo === [1/4] 检查 PyInstaller ===
where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [!] 正在安装 PyInstaller...
    py -3 -m pip install --user -i https://pypi.tuna.tsinghua.edu.cn/simple pyinstaller
    if errorlevel 1 (
        echo [X] PyInstaller 安装失败
        exit /b 1
    )
)

echo.
echo === [2/4] 检查 Playwright Chromium ===
if not exist "%LOCALAPPDATA%\ms-playwright\chromium-1223\chrome-win64\chrome.exe" (
    echo [!] 未找到 Chromium, 尝试安装...
    py -3 -m playwright install chromium
    if errorlevel 1 (
        echo [X] Chromium 安装失败
        exit /b 1
    )
)

echo.
echo === [3/4] 清理旧产物 ===
if exist "build" rmdir /s /q "build"
if exist "dist\Void-DownLoad.exe" del /q "dist\Void-DownLoad.exe"

echo.
echo === [4/4] 开始打包 (单文件, 大约需 3-8 分钟) ===
pyinstaller Void-DownLoad.spec --clean --noconfirm

if errorlevel 1 (
    echo.
    echo [X] 打包失败, 查看上方日志
    exit /b 1
)

echo.
echo ============================================================
echo  打包完成! EXE 位置:
echo  %CD%\dist\Void-DownLoad.exe
echo ============================================================
echo.
dir "dist\Void-DownLoad.exe"
endlocal

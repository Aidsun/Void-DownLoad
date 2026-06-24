@echo off
rem ============================================================
rem 快抓 Void-DownLoad - EXE 打包脚本 (onedir 模式)
rem ============================================================
setlocal

cd /d "%~dp0"

echo.
echo === [1/3] 检查环境 ===
where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [!] 正在安装 PyInstaller...
    pip install pyinstaller
    if errorlevel 1 (
        echo [X] PyInstaller 安装失败
        exit /b 1
    )
)

echo.
echo === [2/3] 清理旧产物 ===
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

echo.
echo === [3/3] 开始打包 (onedir, 大约需 1-3 分钟) ===
pyinstaller Void-DownLoad.spec --clean --noconfirm

if errorlevel 1 (
    echo.
    echo [X] 打包失败, 查看上方日志
    exit /b 1
)

echo.
echo ============================================================
echo  打包完成! 分发目录:
echo  %CD%\dist\Void-DownLoad\
echo ============================================================
echo.
dir "dist\Void-DownLoad\Void-DownLoad.exe"
endlocal

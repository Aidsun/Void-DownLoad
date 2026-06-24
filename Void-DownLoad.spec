# -*- mode: python ; coding: utf-8 -*-
"""
Void-DownLoad PyInstaller spec
================================
打包成单文件 EXE, 内置:
- Python 运行时
- PySide6 + Qt6
- playwright Python 模块
- Chromium 浏览器 (从 %LOCALAPPDATA%\\ms-playwright 自动复制)
"""
import os
import shutil
import sys
from pathlib import Path

# ---- 1. 准备 chromium 资源到 bundle/ 目录 ----
PROJECT_ROOT = Path(SPECPATH).resolve()
BUNDLE_DIR = PROJECT_ROOT / "bundle"
BUNDLE_DIR.mkdir(exist_ok=True)

# 找 chromium
CHROMIUM_SRC = None
ms_playwright = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
if ms_playwright.exists():
    for d in ms_playwright.iterdir():
        if d.name.startswith("chromium-") and d.is_dir():
            for sub in (d / "chrome-win64" / "chrome.exe", d / "chrome-win" / "chrome.exe"):
                if sub.exists():
                    CHROMIUM_SRC = sub
                    break
            if CHROMIUM_SRC:
                break

if CHROMIUM_SRC:
    print(f"[spec] chromium found: {CHROMIUM_SRC}")
    chromium_dir = CHROMIUM_SRC.parent
    bundle_chromium = BUNDLE_DIR / "chromium"
    src_chrome = chromium_dir / "chrome.exe"
    # 增量: 如果 bundle 里的 chrome.exe 大小一致就跳过复制 (避免每次都重拷 412MB)
    need_copy = True
    if bundle_chromium.exists():
        dst_chrome = bundle_chromium / "chrome.exe"
        if dst_chrome.exists() and dst_chrome.stat().st_size == src_chrome.stat().st_size:
            print(f"[spec] bundle/chromium/ already up-to-date, skip copy")
            need_copy = False
    if need_copy:
        size_mb = sum(f.stat().st_size for f in chromium_dir.rglob('*') if f.is_file()) / 1e6
        print(f"[spec] copying chromium tree ({size_mb:.1f} MB) ...")
        if bundle_chromium.exists():
            shutil.rmtree(bundle_chromium, ignore_errors=True)
        shutil.copytree(chromium_dir, bundle_chromium)
        print(f"[spec] chromium copied to {bundle_chromium}")
else:
    print("[spec] WARNING: chromium not found in %LOCALAPPDATA%\\ms-playwright")
    print("[spec]          EXE will require user to run 'playwright install chromium' first")

# ---- 2. PyInstaller 配置 ----
a = Analysis(
    ['Void-DownLoad.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        ('src/style.qss', 'src'),
        ('bundle/chromium', 'bundle/chromium'),  # chromium 目录 (整包进 exe)
    ],
    hiddenimports=[
        'playwright.async_api',
        'playwright.sync_api',
        'playwright._impl._driver',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'test', 'unittest', 'pydoc', 'doctest',
        'matplotlib', 'numpy', 'pandas', 'scipy',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Void-DownLoad',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # 不用 UPX, 防止部分杀软误报
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # GUI 不要控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,           # 可加 .ico, 暂略
)

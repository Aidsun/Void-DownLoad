# -*- mode: python ; coding: utf-8 -*-
"""
快抓 — Void-DownLoad PyInstaller spec
======================================
打包成单文件 EXE, 内置 Python + PySide6 + Playwright。
浏览器优先复用系统 Chrome/Edge, 无需额外下载。
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(SPECPATH).resolve()

# ---- 2. PyInstaller 配置 ----
a = Analysis(
    ['Void-DownLoad.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        ('src/style.qss', 'src'),
        # 🚫 chromium 不再打包 — 改用系统 Chrome/Edge
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

# --onedir 模式: 免解压, 启动毫秒级
#   产物在 dist/Void-DownLoad/ 目录, 打包成 zip 分发即可
exe = EXE(
    pyz,
    a.scripts,
    [],   # 二进制放 COLLECT
    [],   # zipfiles 放 COLLECT
    [],   # datas 放 COLLECT
    name='Void-DownLoad',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
    version='./version.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Void-DownLoad',
)

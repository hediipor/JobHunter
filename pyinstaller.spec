# -*- mode: python ; coding: utf-8 -*-
# Bundles the FastAPI backend (backend/launcher.py) + the Next.js static
# export (frontend/out) into one onefile Windows .exe.
# Paths are anchored on SPECPATH (this file's own directory = repo root)
# so it builds the same whether invoked from the repo root or from backend/.
import os
from PyInstaller.utils.hooks import collect_all

ROOT = SPECPATH

datas = [(os.path.join(ROOT, "frontend", "out"), "frontend_out")]
binaries = []
hiddenimports = []
for pkg in ("apscheduler", "reportlab", "bs4"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [os.path.join(ROOT, "backend", "launcher.py")],
    pathex=[os.path.join(ROOT, "backend")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="JobHunterAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

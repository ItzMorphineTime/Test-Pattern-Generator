# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — builds a single-file Windows executable.

Build from the repo root with:
    pyinstaller packaging/projgen.spec --clean --noconfirm
Output: dist/ProjectionTestPatternGenerator.exe
"""

import os

from PyInstaller.utils.hooks import collect_all

# SPECPATH is injected by PyInstaller and points at this file's directory.
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "src")

datas, binaries, hiddenimports = [], [], []

# PyAV ships the FFmpeg shared libraries inside its package; collect them all so
# every codec (x264/x265/vp9/av1/prores/ffv1) is available in the frozen app.
for pkg in ("av", "imageio_ffmpeg"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# PySide6 is handled by PyInstaller's built-in hook; trim heavyweight, unused Qt
# modules to keep the single file smaller.
excludes = [
    "tkinter",
    "matplotlib",
    "pytest",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtQuick",
    "PySide6.QtQml",
    "PySide6.Qt3DCore",
    "PySide6.QtCharts",
    "PySide6.QtMultimedia",
    "PySide6.QtNetwork",
    "PySide6.QtPdf",
]

a = Analysis(
    [os.path.join(SPECPATH, "projgen_entry.py")],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ProjectionTestPatternGenerator",
    icon=os.path.join(SPECPATH, "icon.ico") if os.path.exists(
        os.path.join(SPECPATH, "icon.ico")) else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # GUI app: no console window
    disable_windowed_traceback=False,
    target_arch=None,
    runtime_tmpdir=None,
)

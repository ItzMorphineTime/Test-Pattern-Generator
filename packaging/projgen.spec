# -*- mode: python ; coding: utf-8 -*-
"""Cross-platform PyInstaller spec — builds a single-file executable.

Build from the repo root with:
    pyinstaller packaging/projgen.spec --clean --noconfirm

Output:
    Windows: dist/ProjectionTestPatternGenerator.exe
    macOS:   dist/ProjectionTestPatternGenerator            (single-file binary)
             dist/ProjectionTestPatternGenerator.app        (app bundle)
"""

import os
import sys

from PyInstaller.utils.hooks import collect_all

IS_MAC = sys.platform == "darwin"

# SPECPATH is injected by PyInstaller and points at this file's directory.
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "src")

ASSETS = os.path.join(SRC, "projgen", "assets")
# The icon embedded into the executable: .icns on macOS, .ico on Windows. (The
# window/taskbar icon is loaded at runtime from the bundled assets.)
EXE_ICON = os.path.join(ASSETS, "icon.icns" if IS_MAC else "icon.ico")

datas, binaries, hiddenimports = [], [], []

# Bundle every asset: the icons, the brand wordmark, the Montserrat fonts (also
# used for burned-in text), and the stylesheet's arrow images.
datas.append((ASSETS, "projgen/assets"))

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
    icon=EXE_ICON if os.path.exists(EXE_ICON) else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # GUI app: no console window
    disable_windowed_traceback=False,
    target_arch=None,       # build for the host arch (Intel or Apple Silicon)
    runtime_tmpdir=None,
)

# On macOS also wrap the single-file binary in a proper .app bundle, which is
# what users expect to double-click. The onefile binary above still works too.
if IS_MAC:
    app = BUNDLE(
        exe,
        name="ProjectionTestPatternGenerator.app",
        icon=EXE_ICON if os.path.exists(EXE_ICON) else None,
        bundle_identifier="com.projgen.testpattern",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": "0.1.0",
        },
    )

"""Locate bundled resources both from source and inside a PyInstaller build."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_path(*parts: str) -> Path:
    """Absolute path to a file under the package's ``assets`` dir.

    When frozen by PyInstaller the data is unpacked under ``sys._MEIPASS`` using
    the same ``projgen/assets`` layout; from source it resolves next to this file.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base is not None:
        return Path(base) / "projgen" / "assets" / Path(*parts)
    return Path(__file__).resolve().parent / "assets" / Path(*parts)


def icon_path() -> str:
    """Path to the application icon (empty string if missing)."""
    path = resource_path("icon.ico")
    return str(path) if path.exists() else ""

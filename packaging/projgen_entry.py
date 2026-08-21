"""Frozen-app entry point used by PyInstaller.

Kept tiny and import-light so it works identically as a script and when frozen.
"""

from __future__ import annotations

import multiprocessing

from projgen.__main__ import main

if __name__ == "__main__":
    multiprocessing.freeze_support()  # safe no-op for our single-process app
    raise SystemExit(main())

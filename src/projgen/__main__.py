"""Entry point: launch the GUI when run with no arguments, else the CLI."""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) > 1:
        from .cli import main as cli_main
        return cli_main()
    from .ui.app import run as gui_run
    return gui_run()


if __name__ == "__main__":
    raise SystemExit(main())

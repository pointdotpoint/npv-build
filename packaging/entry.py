"""Unified frozen entry point: dispatch to CLI when args are present, else GUI.

A single PyInstaller executable serves both `npv-build` (CLI) and the GUI:
- launched with command-line arguments  -> CLI (npv_build.cli.main)
- launched with no arguments (double-click) -> GUI (npv_build.gui.main)
"""

import sys


def run() -> None:
    # argv[0] is the exe; real args start at [1]
    if len(sys.argv) > 1:
        from npv_build.cli import main as cli_main

        sys.exit(cli_main())
    from npv_build.gui import main as gui_main

    gui_main()


if __name__ == "__main__":
    run()

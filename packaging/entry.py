"""Unified frozen entry point: dispatch to CLI when args are present, else GUI.

A single PyInstaller executable serves both `npv-build` (CLI) and the GUI:
- launched with command-line arguments  -> CLI (npv_build.cli.main)
- launched with no arguments (double-click) -> GUI (npv_build.webui_shell.main)
"""

import sys


def run() -> None:
    # argv[0] is the exe; real args start at [1]
    args = sys.argv[1:]
    if args == ["--gui"]:
        from npv_build.webui_shell import main as gui_main

        gui_main()
        return
    if args:
        from npv_build.cli import main as cli_main

        sys.exit(cli_main())
    from npv_build.webui_shell import main as gui_main

    gui_main()


if __name__ == "__main__":
    run()

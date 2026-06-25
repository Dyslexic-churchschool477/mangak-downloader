"""
``python -m mangak`` — Dual entry point for CLI and GUI.

Usage:
    python -m mangak          → CLI (default)
    python -m mangak gui      → GUI
    python -m mangak --help   → CLI help
    python -m mangak --version → show version
"""

import sys
import runpy
from pathlib import Path

from mangak import __version__


def _print_version() -> None:
    print(f"mangak v{__version__}")


def main() -> None:
    """Route ``python -m mangak`` to CLI (default) or GUI (with ``gui`` arg)."""
    # Strip the module execution arg (``-m mangak`` produces ``__main__.py`` path as argv[0])
    args = [a for a in sys.argv[1:] if a not in ("-c",)]

    # --version / -v should work for both routes
    if "--version" in args or "-v" in args:
        _print_version()
        return

    # Launch GUI when first non-flag argument is "gui"
    gui_args = {"gui", "g", "--gui", "-g"}
    if args and args[0] in gui_args:
        # Strip the gui marker so any remaining args are passed through
        sys.argv = [sys.argv[0]] + args[1:]
        try:
            from mangak.gui.app import main as gui_main
            gui_main()
        except ImportError as exc:
            print(f"Error: GUI dependencies not available ({exc})")
            print("Try: pip install mangak-downloader[gui]  or install PyQt6")
            sys.exit(1)
        return

    # Default: launch CLI
    # Run the Typer app from cli.app which handles its own argv
    try:
        from mangak.cli.app import cli_entry
        cli_entry()
    except ImportError as exc:
        print(f"Error: CLI dependencies not available ({exc})")
        print("Try: pip install mangak-downloader[cli]  or install typer and rich")
        sys.exit(1)


if __name__ == "__main__":
    main()

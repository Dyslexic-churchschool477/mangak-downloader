"""Main Typer application for the MangaK CLI.

Registers all subcommands: info, search, download, history, settings, interactive.
"""

from __future__ import annotations

from typing import Optional

import typer

from mangak import __version__
from mangak.cli.commands import (
    download_cmd,
    history_cmd,
    info_cmd,
    search_cmd,
    settings_cmd,
)
from mangak.cli.interactive import interactive_shell

app = typer.Typer(
    name="mangak",
    help="📥 MangaK Downloader — Download manga from mangak.io",
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=False,
)


def _version_callback(show_version: bool) -> None:
    if show_version:
        typer.echo(f"mangak v{__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """MangaK Downloader — Download manga from [bold cyan]mangak.io[/bold cyan].

    Use any of the commands below to get started.
    """
    pass


# ─── info ──────────────────────────────────────────────────────────────


@app.command(
    name="info",
    help="Show detailed info about a manga by slug.",
    rich_help_panel="Commands",
)
def info(
    slug: str = typer.Argument(
        ...,
        help="Manga slug (e.g. 'nano-machine' or 'solo-leveling')",
    ),
    json_flag: bool = typer.Option(
        False,
        "--json",
        help="Output raw JSON instead of Rich formatting.",
    ),
) -> None:
    """Fetch and display detailed information about a manga.

    Shows rating, stats, genres, tags, authors, summary, and latest chapters.
    """
    info_cmd(slug=slug, json_flag=json_flag)


# ─── search ────────────────────────────────────────────────────────────


@app.command(
    name="search",
    help="Search for manga by title or keyword.",
    rich_help_panel="Commands",
)
def search(
    query: str = typer.Argument(
        ...,
        help="Search query (e.g. 'solo leveling' or 'nano machine')",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of results to show.",
    ),
    json_flag: bool = typer.Option(
        False,
        "--json",
        help="Output raw JSON instead of Rich table.",
    ),
) -> None:
    """Search mangak.io for manga matching your query."""
    search_cmd(query=query, limit=limit, json_flag=json_flag)


# ─── download ──────────────────────────────────────────────────────────


@app.command(
    name="download",
    help="Download manga chapters.",
    rich_help_panel="Commands",
)
def download(
    slug: str = typer.Argument(
        ...,
        help="Manga slug (e.g. 'nano-machine')",
    ),
    chapters: Optional[str] = typer.Option(
        None,
        "--chapters",
        "-c",
        help="Chapter range (e.g. '1-10,15,20-25'). Default: all chapters.",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory override.",
    ),
    fmt: str = typer.Option(
        "cbz",
        "--format",
        "-f",
        help="Export format: cbz, pdf, zip, or folder.",
    ),
    concurrent: Optional[int] = typer.Option(
        None,
        "--concurrent",
        "-n",
        help="Concurrent downloads override.",
    ),
    delete_images: bool = typer.Option(
        False,
        "--delete-images",
        "-d",
        help="Delete images after export.",
    ),
) -> None:
    """Download chapters from a manga.

    Supports range selectors like --chapters "1-10,15,20-25" and
    multiple export formats (cbz, pdf, zip, folder).
    """
    download_cmd(
        slug=slug,
        chapters=chapters,
        output=output,
        fmt=fmt,
        concurrent=concurrent,
        delete_images=delete_images,
    )


# ─── history ───────────────────────────────────────────────────────────


@app.command(
    name="history",
    help="Show or clear download history.",
    rich_help_panel="Commands",
)
def history(
    clear: bool = typer.Option(
        False,
        "--clear",
        help="Clear all download history.",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        "-l",
        help="Maximum number of history entries to show.",
    ),
) -> None:
    """Display your download history or clear it."""
    history_cmd(clear=clear, limit=limit)


# ─── settings ──────────────────────────────────────────────────────────


@app.command(
    name="settings",
    help="Show or modify application settings.",
    rich_help_panel="Commands",
)
def settings(
    set_key: Optional[str] = typer.Option(
        None,
        "--set",
        help="Set a setting: --set \"key=value\"",
    ),
) -> None:
    """Display current settings or modify a specific one.

    Example:

        mangak settings --set "download_dir=manga"
        mangak settings --set "concurrent_downloads=6"
    """
    settings_cmd(set_key=set_key)


# ─── interactive ───────────────────────────────────────────────────────


@app.command(
    name="interactive",
    help="Launch the Rich interactive shell.",
    rich_help_panel="Commands",
)
def interactive() -> None:
    """Launch an interactive, menu-driven shell with arrow-key navigation."""
    interactive_shell()


# ─── Entry point ────────────────────────────────────────────────────────


def cli_entry() -> None:
    """Run the Typer app — used by pyproject.toml scripts."""
    app()


if __name__ == "__main__":
    app()

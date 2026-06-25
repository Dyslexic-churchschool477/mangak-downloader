"""
Rich interactive shell for the MangaK Downloader.

Menu-driven interface for searching, downloading (with chapter list display),
history, and settings.
"""

from __future__ import annotations

import asyncio
import re
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from mangak.core import (
    DownloadDB,
    MangaKClient,
    Settings,
)
from mangak.cli.commands.download import _run_download
from mangak.cli.display import (
    build_history_table,
    build_manga_panel,
    build_search_table,
    build_settings_table,
)


def _extract_slug(text: str) -> str:
    """Extract manga slug from a URL or plain slug."""
    text = text.strip()
    if not text:
        return ""
    m = re.search(r"mangak\.io/([a-zA-Z0-9_-]+)", text)
    if m:
        return m.group(1)
    return text.split("?")[0].rstrip("/").split("/")[-1]


async def _fetch_and_show_chapters(slug: str, console: Console) -> list:
    """Fetch manga info + chapter list and display with indices."""
    async with MangaKClient() as client:
        try:
            manga = await client.get_manga_info(slug)
        except Exception as exc:
            console.print(f"[red]❌ Failed to fetch manga: {exc}[/red]")
            return []

        console.print(f"\n[bold cyan]📚 {manga.name}[/bold cyan]")
        console.print(f"  [dim]Author: {manga.authors[0].name if manga.authors else '—'}  •  Status: {manga.status}[/dim]\n")

        try:
            chapter_list = await client.get_chapter_list(manga.id, manga.cv)
        except Exception:
            console.print("[red]❌ Failed to fetch chapter list[/red]")
            return []

        if not chapter_list:
            console.print("[yellow]No chapters found.[/yellow]")
            return []

        chapter_list.sort(key=lambda c: c.chapter_number)

        table = Table(title="📖 Chapter List", border_style="purple")
        table.add_column("#", style="bold cyan", width=5)
        table.add_column("Chapter", style="white")
        table.add_column("Name", style="dim")
        table.add_column("Date", style="dim", width=12)

        for i, ch in enumerate(chapter_list, 1):
            date_str = ch.updated_at[:10] if hasattr(ch, 'updated_at') and ch.updated_at else ""
            table.add_row(str(i), ch.slug, ch.name[:50], date_str)

        console.print(table)
        console.print()
        return chapter_list


def interactive_shell() -> None:
    console = Console()
    console.print()
    console.print(Panel(
        "[bold purple]MangaK Downloader — Interactive Shell[/bold purple]\n\n"
        "[dim]Type 'q' to quit or 'm' to return to menu at any prompt.[/dim]",
        border_style="purple",
    ))
    console.print()
    while True:
        choice = _show_main_menu(console)
        if choice == "q" or choice is None:
            break
        _handle_choice(choice, console)
    console.print("[bold green]👋 Goodbye![/bold green]")


def _show_main_menu(console: Console) -> Optional[str]:
    console.print()
    menu = Table(title="📋 Main Menu", title_style="bold cyan", border_style="blue", show_header=False, box=None)
    menu.add_column("Option", style="bold white", width=4)
    menu.add_column("Description", style="white")
    menu.add_row("1", "🔍  Search for manga")
    menu.add_row("2", "📥  Download a manga")
    menu.add_row("3", "📜  View download history")
    menu.add_row("4", "⚙️   Settings")
    menu.add_row("5", "❓  About")
    menu.add_row("q", "[dim]Quit[/dim]")
    console.print(menu)
    console.print()
    return Prompt.ask("[bold]Select an option[/bold]", choices=["1", "2", "3", "4", "5", "q"], default="1")


def _handle_choice(choice: str, console: Console) -> None:
    if choice == "1": _interactive_search(console)
    elif choice == "2": _interactive_download(console)
    elif choice == "3": _interactive_history(console)
    elif choice == "4": _interactive_settings(console)
    elif choice == "5": _interactive_about(console)


# ── Search ──

def _interactive_search(console: Console) -> None:
    console.print()
    query = Prompt.ask("[bold cyan]🔍 Search[/bold cyan]", default="")
    if not query or query.lower() == "q":
        return
    results = asyncio.run(_async_search(query))
    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return
    console.print(build_search_table(results))
    console.print()
    sel = Prompt.ask("[bold]Select result number (or 'b' to go back)[/bold]", default="1")
    if sel.lower() in ("b", "q", "m"):
        return
    try:
        idx = int(sel) - 1
        if idx < 0 or idx >= len(results):
            console.print("[red]Invalid selection.[/red]")
            return
    except ValueError:
        console.print("[red]Invalid selection.[/red]")
        return
    selected = results[idx]
    console.print(f"\n[bold]Fetching details for: {selected.name}[/bold]\n")
    manga = asyncio.run(_async_get_info(selected.slug))
    if manga:
        console.print(build_manga_panel(manga))
    else:
        t = Table(title=f"📚 {selected.name}", border_style="purple")
        t.add_column("Field", style="bold", width=15)
        t.add_column("Value", style="white")
        t.add_row("Slug", selected.slug)
        t.add_row("Rating", f"{selected.rating:.1f} ★")
        t.add_row("Status", str(selected.status).title())
        console.print(t)
    console.print()
    if Confirm.ask("[bold]Download this manga?[/bold]", default=False):
        _run_download_flow(console, selected.slug)


# ── Download ──

def _interactive_download(console: Console) -> None:
    console.print()
    raw = Prompt.ask("[bold cyan]📥 Enter manga slug or URL[/bold cyan]")
    if not raw or raw.lower() == "q":
        return
    slug = _extract_slug(raw)
    if not slug:
        console.print("[red]Could not extract slug from input.[/red]")
        return
    _run_download_flow(console, slug)


def _run_download_flow(console: Console, slug: str) -> None:
    settings = Settings()
    chapter_list = asyncio.run(_fetch_and_show_chapters(slug, console))
    if not chapter_list:
        return

    range_input = Prompt.ask(
        "[bold]Chapters to download[/bold] (e.g. '1-10,15' or press Enter for all)",
        default="",
    )
    fmt = Prompt.ask("[bold]Export format[/bold]", choices=["cbz", "pdf", "zip", "folder"],
                     default=settings.get("export_format", "cbz"))
    concurrent = IntPrompt.ask("[bold]Concurrent downloads[/bold]",
                               default=settings.get("concurrent_downloads", 4))
    delete_images = Confirm.ask("[bold]Delete images after export?[/bold]",
                                default=settings.get("delete_images_after_export", True))

    console.print(f"\n[cyan]Starting download: {slug}...[/cyan]\n")
    asyncio.run(_run_download(slug=slug,
                               chapters_str=range_input if range_input.strip() else None,
                               output_dir=None, export_format=fmt,
                               concurrency=concurrent, delete_after=delete_images))
    console.print()
    console.print("[bold green]✅ Download complete![/bold green]")


# ── History ──

def _interactive_history(console: Console) -> None:
    db = DownloadDB()
    while True:
        records = db.get_history(limit=50)
        if not records:
            console.print("[yellow]📜 No download history found.[/yellow]")
            return
        console.print(build_history_table(records))
        console.print()
        stats = db.get_stats()
        console.print(f"[dim]Total: {stats.get('total_downloads', 0)} downloads | Unique: {stats.get('unique_manga', 0)}[/dim]")
        console.print()
        action = Prompt.ask("[bold]Action[/bold]", choices=["c", "b", "q"], default="b")
        if action == "q": break
        elif action == "c":
            if Confirm.ask("[bold red]Clear ALL download history?[/bold red]", default=False):
                db.clear_history()
                console.print("[green]✅ Cleared.[/green]")
        elif action == "b": break


# ── Settings ──

def _interactive_settings(console: Console) -> None:
    settings = Settings()
    while True:
        all_settings = settings.all()
        console.print(build_settings_table(all_settings))
        console.print()
        console.print("[dim]Options:  [bold]e[/bold] Edit  [bold]r[/bold] Reset  [bold]b[/bold] Back  [bold]q[/bold] Quit[/dim]")
        console.print()
        action = Prompt.ask("[bold]Select option[/bold]", choices=["e", "r", "b", "q"], default="b")
        if action == "q": exit(0)
        elif action == "b": break
        elif action == "r":
            if Confirm.ask("[bold red]Reset ALL settings to defaults?[/bold red]", default=False):
                settings.reset()
                console.print("[green]✅ Reset to defaults.[/green]")
        elif action == "e":
            key = Prompt.ask("[bold]Setting key[/bold]")
            if key.lower() in ("q", "b"): continue
            if key not in all_settings:
                console.print(f"[red]Unknown setting: '{key}'[/red]")
                continue
            current_val = all_settings[key]
            if isinstance(current_val, bool):
                val = Prompt.ask(f"[bold]Value for '{key}'[/bold] (true/false)",
                                 default="true" if current_val else "false").lower() in ("true", "1", "yes")
            elif isinstance(current_val, int):
                val = IntPrompt.ask(f"[bold]Value for '{key}'[/bold]", default=current_val)
            elif isinstance(current_val, float):
                val = float(Prompt.ask(f"[bold]Value for '{key}'[/bold]", default=str(current_val)))
            elif isinstance(current_val, list):
                v = Prompt.ask(f"[bold]Value for '{key}'[/bold] (comma-separated)", default="")
                val = [x.strip() for x in v.split(",") if x.strip()] if v else []
            else:
                val = Prompt.ask(f"[bold]Value for '{key}'[/bold]", default=str(current_val) if current_val else "")
            try:
                settings.set(key, val)
                console.print(f"[green]✅ Set '{key}' = '{val}'[/green]")
            except Exception as exc:
                console.print(f"[red]❌ {exc}[/red]")


# ── About ──

def _interactive_about(console: Console) -> None:
    from mangak import __version__
    console.print(Panel(
        "[bold purple]MangaK Downloader[/bold purple]\n\n"
        f"[bold]Version:[/bold] {__version__}\n"
        "[bold]Description:[/bold] A manga downloader for mangak.io\n\n"
        "[bold]Features:[/bold]\n"
        "  • Search and browse manga\n"
        "  • Download with chapter list and index selection\n"
        "  • Export to CBZ, PDF, ZIP, or folder\n"
        "  • Download history tracking\n"
        "  • Rich interactive shell",
        title="ℹ️  About", border_style="purple",
    ))
    console.print()
    Prompt.ask("[dim]Press Enter to continue[/dim]", default="")


# ── Async helpers ──

async def _async_search(query: str):
    try:
        async with MangaKClient() as client:
            return await client.search(query)
    except Exception:
        return []

async def _async_get_info(slug: str):
    try:
        async with MangaKClient() as client:
            return await client.get_manga_info(slug)
    except Exception:
        return None

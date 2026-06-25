"""mangak history — Show or clear download history."""

from __future__ import annotations

import typer
from rich.console import Console

from mangak.core import DownloadDB, Settings
from mangak.cli.display import build_history_table


def history_cmd(clear: bool = False, limit: int = 50) -> None:
    """Show or clear download history."""
    db = DownloadDB()
    console = Console()

    if clear:
        deleted = db.clear_history()
        console.print(f"[green]✅ Cleared {deleted} download record(s).[/green]")
        return

    records = db.get_history(limit=limit)
    if not records:
        console.print("[yellow]📜 No download history found.[/yellow]")
        console.print("[dim]Try: mangak download <slug>[/dim]")
        return

    table = build_history_table(records)
    console.print(table)

    # Stats footer
    stats = db.get_stats()
    console.print()
    console.print(
        f"[dim]Total: {stats.get('total_downloads', 0)} downloads | "
        f"Unique manga: {stats.get('unique_manga', 0)} | "
        f"Latest: {str(stats.get('latest_download', 'N/A'))[:16]}[/dim]"
    )

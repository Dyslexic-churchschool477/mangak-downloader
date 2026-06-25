"""Shared Rich formatting helpers for the MangaK CLI."""

from __future__ import annotations

from typing import Any, Optional

from rich.console import Group
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

from mangak.core import Colors
from mangak.core.models import Manga, SearchResult


def rating_stars(rating: float, max_stars: int = 5) -> str:
    """Convert a float rating (0-5/10) into a star string.
    
    Assumes rating is out of 5 (mangak.io) or normalised.
    Full star = ★, half star = ⯨, empty = ☆.
    """
    full = int(rating)
    half = 1 if rating - full >= 0.25 else 0
    empty = max_stars - full - half
    return "★" * full + "⯨" * half + "☆" * empty


def status_badge(status: str) -> Text:
    """Return a coloured status badge for a manga."""
    s = status.lower()
    if s in ("ongoing", "активна", "активный"):
        return Text(f" {status} ", style="bold green on #003300")
    elif s in ("completed", "завершена", "завершенный"):
        return Text(f" {status} ", style="bold blue on #000033")
    elif s in ("hiatus", "приостановлена"):
        return Text(f" {status} ", style="bold yellow on #332200")
    elif s in ("cancelled", "отменена"):
        return Text(f" {status} ", style="bold red on #330000")
    return Text(f" {status} ", style="bold white on #333333")


def adult_badge(is_adult: bool) -> Optional[Text]:
    """Return an adult-content badge if applicable."""
    if is_adult:
        return Text(" 18+ ", style="bold red on #330000")
    return None


def genre_tags(genres: list[Any]) -> str:
    """Format genres/tags as a comma-separated string."""
    names = []
    for g in genres:
        if hasattr(g, "name"):
            names.append(str(g.name))
        else:
            names.append(str(g))
    return ", ".join(names)


def format_file_size(kb: Optional[int]) -> str:
    """Format KB to human-readable size."""
    if kb is None:
        return "—"
    if kb < 1024:
        return f"{kb} KB"
    mb = kb / 1024
    if mb < 1024:
        return f"{mb:.1f} MB"
    gb = mb / 1024
    return f"{gb:.2f} GB"


def build_manga_panel(manga: Manga) -> Panel:
    """Build a detailed Rich Panel for a Manga object."""
    lines: list[Any] = []

    # Title line
    title = Text()
    title.append(f"{manga.name}", style="bold white")
    if manga.alt_name:
        title.append(f"\n{manga.alt_name}", style="italic dim")
    lines.append(title)

    # Badges
    badges: list[Text] = []
    badges.append(status_badge(manga.status))
    if manga.is_adult:
        badges.append(adult_badge(manga.is_adult))
    if manga.is_hot:
        badges.append(Text(" HOT ", style="bold white on red"))
    if manga.is_new:
        badges.append(Text(" NEW ", style="bold white on blue"))
    if badges:
        badge_group = Text()
        for b in badges:
            badge_group.append(b)
            badge_group.append(" ")
        lines.append(Text())
        lines.append(badge_group)

    # Rating
    lines.append(Text())
    star_str = rating_stars(manga.rating)
    lines.append(Text(f"Rating: {manga.rating:.1f}/5 {star_str}", style="yellow"))

    # Stats
    lines.append(Text())
    stats_text = Text()
    stats_text.append(f"📊 Chapters: {manga.stats.chapters_count}", style="cyan")
    stats_text.append("  ")
    stats_text.append(f"👁️ Views: {manga.display_views}", style="green")
    stats_text.append("\n")
    stats_text.append(f"🔖 Bookmarks: {manga.display_bookmarks}", style="magenta")
    stats_text.append("  ")
    stats_text.append(f"💬 Comments: {manga.stats.comments_count}", style="blue")
    lines.append(stats_text)

    # Genres
    if manga.genres:
        lines.append(Text())
        lines.append(Text(f"🏷️ Genres: {genre_tags(manga.genres)}", style="bold yellow"))

    # Tags
    if manga.tags:
        lines.append(Text(f"🔖 Tags: {genre_tags(manga.tags)}", style="dim"))

    # Authors
    if manga.authors:
        author_names = [a.name for a in manga.authors]
        lines.append(Text(f"✍️  Authors: {', '.join(author_names)}", style="italic"))

    # Summary
    if manga.summary:
        lines.append(Text())
        lines.append(Text("📝 Summary", style="bold underline"))
        lines.append(Text(manga.summary, style="white"))

    # Latest chapters
    if manga.latest_chapters:
        lines.append(Text())
        lines.append(Text("📖 Latest Chapters", style="bold underline"))
        for i, ch in enumerate(manga.latest_chapters[:5]):
            lines.append(
                Text(f"  {ch.name} — {ch.date[:10]}", style="dim")
            )

    group = Group(*lines)
    panel = Panel(
        group,
        title=f"[bold purple]📚 {manga.slug}[/bold purple]",
        border_style="purple",
        padding=(1, 2),
        width=None,
    )
    return panel


def build_search_table(
    results: list[SearchResult], limit: Optional[int] = None
) -> Table:
    """Build a Rich Table from a list of SearchResult objects."""
    table = Table(
        title=f"🔍 Search Results ({len(results)} found)",
        title_style="bold cyan",
        header_style="bold magenta",
        border_style="blue",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="bold white", no_wrap=False)
    table.add_column("Type", style="yellow", width=10)
    table.add_column("Rating", style="green", width=8)
    table.add_column("Status", style="cyan", width=12)
    table.add_column("Genres", style="dim", width=40)

    displayed = results[:limit] if limit else results

    for idx, r in enumerate(displayed, 1):
        rating_str = f"{r.rating:.1f}" if r.rating else "—"
        stars = ""
        if r.rating:
            stars = " " + rating_stars(r.rating)
        genre_str = genre_tags(r.genres) if r.genres else ""
        status_str = str(r.status).title() if r.status else "—"
        table.add_row(
            str(idx),
            r.name,
            "Manga",
            f"{rating_str}{stars}",
            status_str,
            genre_str[:60],
        )

    return table


def build_history_table(records: list[Any]) -> Table:
    """Build a Rich Table from DownloadDB history records."""
    table = Table(
        title="📜 Download History",
        title_style="bold cyan",
        header_style="bold green",
        border_style="blue",
    )
    table.add_column("ID", style="dim", width=5)
    table.add_column("Manga", style="bold white", no_wrap=False)
    table.add_column("Chapter", style="cyan", no_wrap=False)
    table.add_column("Format", style="yellow", width=8)
    table.add_column("Pages", style="green", width=6)
    table.add_column("Size", style="magenta", width=10)
    table.add_column("Date", style="dim", width=16)

    for rec in records:
        table.add_row(
            str(rec.get("id", "")),
            rec.get("manga_name", ""),
            rec.get("chapter_name", ""),
            rec.get("format", ""),
            str(rec.get("pages_count", "")),
            format_file_size(rec.get("file_size_kb")),
            str(rec.get("downloaded_at", ""))[:16],
        )

    return table


def build_settings_table(settings: dict[str, Any]) -> Table:
    """Build a Rich Table from Settings.all()."""
    table = Table(
        title="⚙️  Settings",
        title_style="bold cyan",
        header_style="bold yellow",
        border_style="blue",
    )
    table.add_column("Key", style="bold white", width=30)
    table.add_column("Value", style="green", width=50)

    for key, value in settings.items():
        val_str = str(value) if value is not None else ""
        if isinstance(value, bool):
            val_str = "✅ true" if value else "❌ false"
        elif isinstance(value, list):
            val_str = ", ".join(str(v) for v in value) if value else "(empty)"
        table.add_row(key, val_str)

    return table


def make_progress_bars() -> Progress:
    """Create a Rich Progress instance configured for download display."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        expand=True,
    )

"""mangak info <slug> — Display detailed info about a manga."""

from __future__ import annotations

import asyncio
import json

import typer
from rich import print_json

from mangak.core import MangaKClient, MangaNotFoundError
from mangak.cli.display import build_manga_panel


def info_cmd(slug: str, json_flag: bool = False) -> None:
    """Fetch and display detailed information about a manga."""
    manga = asyncio.run(_fetch_manga_info(slug))
    if not manga:
        typer.echo(f"❌ Manga not found: {slug}", err=True)
        raise typer.Exit(code=1)

    if json_flag:
        print_json(data=manga.model_dump(mode="json"))
    else:
        panel = build_manga_panel(manga)
        from rich.console import Console

        console = Console()
        console.print(panel)


async def _fetch_manga_info(slug: str):
    """Async helper to fetch manga info from the API."""
    try:
        async with MangaKClient() as client:
            manga = await client.get_manga_info(slug)
            return manga
    except MangaNotFoundError:
        return None
    except Exception as exc:
        typer.echo(f"❌ Error fetching manga info: {exc}", err=True)
        return None

"""mangak search <query> — Search for manga on mangak.io."""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich import print_json
from rich.console import Console

from mangak.core import MangaKClient
from mangak.cli.display import build_search_table


def search_cmd(
    query: str,
    limit: Optional[int] = None,
    json_flag: bool = False,
) -> None:
    """Search for manga by title or keyword."""
    results = asyncio.run(_run_search(query))
    if not results:
        typer.echo(f"🔍 No results found for: '{query}'")
        return

    if json_flag:
        data = [r.model_dump(mode="json") for r in results]
        print_json(data=data)
    else:
        console = Console()
        table = build_search_table(results, limit=limit)
        console.print(table)


async def _run_search(query: str):
    """Async helper to search mangak.io."""
    try:
        async with MangaKClient() as client:
            results = await client.search(query)
            return results
    except Exception as exc:
        typer.echo(f"❌ Search failed: {exc}", err=True)
        return []

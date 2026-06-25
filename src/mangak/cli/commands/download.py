"""mangak download <slug> — Download manga chapters."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.live import Live
from rich.progress import (
    BarColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from mangak.core import (
    DownloadDB,
    MangaKClient,
    Settings,
    export_cbz,
    export_folder,
    export_pdf,
    export_zip,
)
from mangak.core.models import DownloadTask, DownloadStatus


def download_cmd(
    slug: str,
    chapters: Optional[str] = None,
    output: Optional[str] = None,
    fmt: str = "cbz",
    concurrent: Optional[int] = None,
    delete_images: bool = False,
) -> None:
    """Download manga chapters from mangak.io."""
    asyncio.run(
        _run_download(
            slug=slug,
            chapters_str=chapters,
            output_dir=output,
            export_format=fmt,
            concurrency=concurrent,
            delete_after=delete_images,
        )
    )


async def _run_download(
    slug: str,
    chapters_str: Optional[str] = None,
    output_dir: Optional[str] = None,
    export_format: str = "cbz",
    concurrency: Optional[int] = None,
    delete_after: bool = False,
) -> None:
    settings = Settings()
    console = Console()

    if output_dir:
        base_dir = Path(output_dir)
    else:
        base_dir = Path(settings.get("download_dir", "downloads"))
    base_dir.mkdir(parents=True, exist_ok=True)

    c = concurrency if concurrency is not None else settings.get("concurrent_downloads", 4)

    console.print(f"[bold cyan]📥 Downloading: [/bold cyan][white]{slug}[/white]\n")

    async with MangaKClient() as client:
        # Fetch manga info
        try:
            manga = await client.get_manga_info(slug)
        except Exception as exc:
            console.print(f"[red]❌ Failed to fetch manga: {exc}[/red]")
            raise typer.Exit(code=1)

        console.print(f"  [green]✓[/green] {manga.name}\n")

        # Fetch chapter list
        try:
            chapter_list = await client.get_chapter_list(manga.id, manga.cv)
        except Exception as exc:
            console.print(f"[red]❌ Failed to fetch chapter list: {exc}[/red]")
            raise typer.Exit(code=1)

        if not chapter_list:
            console.print("[yellow]⚠️  No chapters found.[/yellow]")
            return

        chapter_list.sort(key=lambda c: c.chapter_number)
        selected = _parse_chapter_range(chapters_str, len(chapter_list))
        if not selected:
            selected = list(range(len(chapter_list)))

        chapters_to_download = [chapter_list[i] for i in selected]
        if not chapters_to_download:
            console.print("[yellow]⚠️  No chapters match the given range.[/yellow]")
            return

        console.print(f"  [dim]Downloading {len(chapters_to_download)} chapter(s) — {c} at a time[/dim]\n")

        # Pre-fetch all chapter data so we know page counts for progress bars
        chapter_data_map: dict[str, tuple] = {}  # slug -> (DownloadTask, total_pages)
        console.print("[dim]Preparing chapters...[/dim]")
        for ch in chapters_to_download:
            try:
                cd = await client.get_chapter(slug, ch.slug)
                if cd.images:
                    task = DownloadTask(
                        manga_slug=slug, manga_name=manga.name,
                        chapter_slug=ch.slug, chapter_name=ch.name,
                        chapter_id=ch.id,
                        images=[str(u) for u in cd.images],
                        format=export_format, output_dir=str(base_dir),
                        delete_after=delete_after,
                    )
                    chapter_data_map[ch.slug] = task
                else:
                    console.print(f"  [yellow]⚠[/yellow] {ch.name}: No images")
            except Exception as exc:
                console.print(f"  [red]✗[/red] {ch.name}: {exc}")

        if not chapter_data_map:
            console.print("[red]No chapters could be prepared.[/red]")
            return

        # Build per-chapter progress bars
        progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("•"),
            TextColumn("{task.completed}/{task.total} pages"),
            TextColumn("•"),
            TimeElapsedColumn(),
            expand=True,
        )

        chapter_task_ids: dict[str, TaskID] = {}
        tasks_list = list(chapter_data_map.values())
        for dt in tasks_list:
            tid = progress.add_task(
                f"[cyan]{dt.chapter_name}[/cyan]",
                total=dt.pages_total,
            )
            chapter_task_ids[dt.chapter_slug] = tid

        sem = asyncio.Semaphore(c)
        db = DownloadDB()
        errors: list[str] = []
        completed = 0
        total = len(tasks_list)

        async def _download_one(task: DownloadTask) -> None:
            nonlocal completed
            async with sem:
                tid = chapter_task_ids[task.chapter_slug]

                # Progress callback
                def on_page(chapter_slug: str, done: int, total_p: int) -> None:
                    progress.update(chapter_task_ids[chapter_slug], completed=done, total=total_p)

                await _execute_task(client, task, on_page)
                progress.update(tid, completed=task.pages_total, description=f"[green]✓ {task.chapter_name}[/green]")

                # Export
                images_dir = base_dir / slug / task.chapter_slug
                if images_dir.exists() and any(images_dir.iterdir()):
                    try:
                        export_path = _export_chapter(
                            images_dir=images_dir, output_dir=base_dir,
                            manga_slug=slug, chapter_slug=task.chapter_slug,
                            export_format=export_format, delete_after=delete_after,
                        )
                    except Exception:
                        export_path = images_dir
                else:
                    export_path = images_dir

                # Record in DB
                try:
                    total_size = _get_dir_size(images_dir) if images_dir.exists() else 0
                    db.record_download(
                        manga_slug=slug, manga_name=manga.name,
                        chapter_slug=task.chapter_slug, chapter_name=task.chapter_name,
                        format=export_format, pages_count=task.pages_completed,
                        file_path=str(export_path), file_size_kb=total_size,
                    )
                except Exception:
                    pass

                completed += 1

        with Live(progress, console=console, refresh_per_second=8):
            download_tasks = [_download_one(dt) for dt in tasks_list]
            await asyncio.gather(*download_tasks)

        console.print()
        console.print(f"[bold green]✅ Downloaded {completed}/{total} chapters![/bold green]")


def _parse_chapter_range(
    range_str: Optional[str], total: int
) -> list[int]:
    if not range_str or range_str.strip() == "":
        return list(range(total))
    indices: set[int] = set()
    parts = [p.strip() for p in range_str.split(",")]
    for part in parts:
        if not part:
            continue
        if "-" in part:
            try:
                s, e = part.split("-", 1)
                start, end = int(s.strip()), int(e.strip())
                start, end = max(1, start), min(total, end)
                for i in range(start, end + 1):
                    indices.add(i - 1)
            except (ValueError, TypeError):
                continue
        else:
            try:
                num = int(part)
                if 1 <= num <= total:
                    indices.add(num - 1)
            except (ValueError, TypeError):
                continue
    return sorted(indices)


async def _execute_task(
    client: MangaKClient,
    task: DownloadTask,
    on_page_progress=None,
) -> None:
    images_dir = Path(task.output_dir) / task.manga_slug / task.chapter_slug
    images_dir.mkdir(parents=True, exist_ok=True)

    task.status = DownloadStatus.DOWNLOADING
    task.pages_total = len(task.images)
    task.pages_completed = 0

    delay = 0.25

    for idx, image_url in enumerate(task.images):
        fname = f"{idx + 1:03d}.webp"
        dest = images_dir / fname

        if dest.exists() and dest.stat().st_size > 1024:
            task.pages_completed += 1
            if on_page_progress:
                on_page_progress(task.chapter_slug, task.pages_completed, task.pages_total)
            continue

        if delay > 0:
            await asyncio.sleep(delay)

        try:
            await client.download_image(image_url, dest, use_rotation=False)
            task.pages_completed += 1
        except Exception:
            continue

        task.progress = task.pages_completed / task.pages_total if task.pages_total > 0 else 0.0
        if on_page_progress:
            on_page_progress(task.chapter_slug, task.pages_completed, task.pages_total)

    if task.pages_completed > 0:
        task.status = DownloadStatus.COMPLETED
    else:
        task.status = DownloadStatus.FAILED


def _export_chapter(
    images_dir: Path,
    output_dir: Path,
    manga_slug: str,
    chapter_slug: str,
    export_format: str,
    delete_after: bool = False,
) -> Path:
    fmt = export_format.lower()
    if fmt == "folder":
        return export_folder(images_dir, output_dir, delete_after=delete_after)
    export_name = f"{manga_slug}-{chapter_slug}"
    archive_ext = {"cbz": ".cbz", "zip": ".zip", "pdf": ".pdf"}.get(fmt, ".cbz")
    output_path = output_dir / f"{export_name}{archive_ext}"
    if fmt == "cbz":
        return export_cbz(images_dir, output_path, delete_after=delete_after)
    elif fmt == "zip":
        return export_zip(images_dir, output_path, delete_after=delete_after)
    elif fmt == "pdf":
        return export_pdf(images_dir, output_path, delete_after=delete_after)
    else:
        return export_folder(images_dir, output_dir, delete_after=delete_after)


def _get_dir_size(path: Path) -> int:
    total_bytes = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            total_bytes += entry.stat().st_size
    return total_bytes // 1024

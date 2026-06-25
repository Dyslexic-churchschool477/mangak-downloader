"""
Async download engine with queue management, concurrency control,
progress callbacks, resume support, and rate limiting.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Callable, Optional

from mangak.core.client import MangaKClient, _rotate_cdn_url
from mangak.core.config import Settings
from mangak.core.exceptions import DownloadError
from mangak.core.models import DownloadStatus, DownloadTask

# Callback signatures
OnPageCallback = Callable[[str, str, int, int], None]  # (manga, chapter, page, total)
OnChapterCallback = Callable[[str, str, int], None]  # (manga, chapter, total_pages)
OnErrorCallback = Callable[[str, str, Exception], None]  # (manga, chapter, error)


class DownloadQueue:
    """
    Async download queue for manga chapters.

    Manages a list of ``DownloadTask`` objects, executes them with
    configurable concurrency, rate limiting, subdomain rotation, and
    resume support.

    Usage::

        queue = DownloadQueue()
        await queue.add_task(task)
        await queue.run()
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        on_page_download: Optional[OnPageCallback] = None,
        on_chapter_complete: Optional[OnChapterCallback] = None,
        on_error: Optional[OnErrorCallback] = None,
        client: Optional[MangaKClient] = None,
    ) -> None:
        self._settings = settings or Settings()
        self._client = client

        # Callbacks
        self.on_page_download = on_page_download
        self.on_chapter_complete = on_chapter_complete
        self.on_error = on_error

        # Task queue
        self._tasks: list[DownloadTask] = []
        self._active_count: int = 0
        self._paused: bool = False
        self._cancelled: bool = False
        self._sem: Optional[asyncio.Semaphore] = None

        # Client lifetime management
        self._owns_client = client is None

    # ── Public API ──────────────────────────────

    def add_task(self, task: DownloadTask) -> None:
        """Add a single download task to the queue."""
        task.status = DownloadStatus.QUEUED
        self._tasks.append(task)

    def add_tasks(self, tasks: list[DownloadTask]) -> None:
        """Add multiple download tasks to the queue."""
        for t in tasks:
            self.add_task(t)

    @property
    def tasks(self) -> list[DownloadTask]:
        """Return a copy of the current task list."""
        return list(self._tasks)

    @property
    def pending_count(self) -> int:
        """Number of tasks not yet completed or failed."""
        return sum(
            1
            for t in self._tasks
            if t.status in (DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING)
        )

    def pause(self) -> None:
        """Pause the download queue (in-flight downloads finish)."""
        self._paused = True

    def resume(self) -> None:
        """Resume a paused download queue."""
        self._paused = False

    def cancel(self) -> None:
        """Cancel all pending and in-flight downloads."""
        self._cancelled = True
        for task in self._tasks:
            if task.status in (
                DownloadStatus.QUEUED,
                DownloadStatus.DOWNLOADING,
                DownloadStatus.PAUSED,
            ):
                task.status = DownloadStatus.CANCELLED

    def clear_completed(self) -> None:
        """Remove completed and cancelled tasks from the queue."""
        self._tasks = [
            t
            for t in self._tasks
            if t.status
            not in (DownloadStatus.COMPLETED, DownloadStatus.CANCELLED)
        ]

    async def run(self) -> None:
        """
        Execute all queued tasks.

        Creates a client if one was not provided and manages its lifecycle.
        Blocks until all tasks are processed (or paused/cancelled).
        """
        if self._client is None:
            self._client = MangaKClient()
            self._owns_client = True

        owned = self._owns_client
        if owned:
            await self._client.__aenter__()

        try:
            await self._process_queue()
        finally:
            if owned and self._client:
                await self._client.__aexit__()

    async def run_async(
        self, client: MangaKClient
    ) -> None:
        """
        Execute the queue with an externally-managed client.

        Use this when the caller already has an open ``MangaKClient``
        session (e.g. within a larger async context).
        """
        self._client = client
        self._owns_client = False
        await self._process_queue()

    # ── Internal ────────────────────────────────

    async def _process_queue(self) -> None:
        """Core loop: process tasks with concurrency control."""
        concurrency = self._settings.get("concurrent_downloads", 4)
        self._sem = asyncio.Semaphore(concurrency)

        async def _worker(task: DownloadTask) -> None:
            async with self._sem:
                await self._execute_task(task)

        # Launch all tasks concurrently — semaphore limits how many run at once
        pending = [t for t in self._tasks if t.status == DownloadStatus.QUEUED]
        if not pending:
            return

        tasks = [_worker(t) for t in pending]
        await asyncio.gather(*tasks)

    def _next_queued(self) -> Optional[DownloadTask]:
        """Return the first task with QUEUED status, or None."""
        for task in self._tasks:
            if task.status == DownloadStatus.QUEUED:
                return task
        return None

    async def _execute_task(self, task: DownloadTask) -> None:
        """Download all pages for a single chapter task."""
        if self._client is None:
            return

        task.status = DownloadStatus.DOWNLOADING
        task.pages_total = len(task.images)
        task.pages_completed = 0
        task.progress = 0.0

        # Signal start so UI moves item from queued to active immediately
        if self.on_page_download:
            self.on_page_download(
                task.manga_slug,
                task.chapter_slug,
                0,
                task.pages_total,
            )

        output_path = Path(task.output_dir)
        images_dir = (
            output_path / task.manga_slug / task.chapter_slug
        )

        # Rate-limit delay
        delay = self._settings.get("rate_limit_delay", 0.25)
        use_rotation = self._settings.get("subdomain_rotation", True)

        try:
            for idx, image_url in enumerate(task.images):
                if self._cancelled:
                    task.status = DownloadStatus.CANCELLED
                    return

                while self._paused and not self._cancelled:
                    task.status = DownloadStatus.PAUSED
                    await asyncio.sleep(0.5)

                if self._cancelled:
                    task.status = DownloadStatus.CANCELLED
                    return

                fname = f"{idx + 1:03d}.webp"
                dest = images_dir / fname

                # Resume support: skip if file exists and is > 1 KB
                if dest.exists() and dest.stat().st_size > 1024:
                    task.pages_completed += 1
                    if self.on_page_download:
                        self.on_page_download(
                            task.manga_slug,
                            task.chapter_slug,
                            task.pages_completed,
                            task.pages_total,
                        )
                    continue

                # Rate limit
                if delay > 0:
                    await asyncio.sleep(delay)

                try:
                    target_url = (
                        _rotate_cdn_url(image_url)
                        if use_rotation
                        else image_url
                    )
                    await self._client.download_image(
                        target_url, dest, use_rotation=False
                    )
                    task.pages_completed += 1
                except DownloadError as exc:
                    if self.on_error:
                        self.on_error(
                            task.manga_slug, task.chapter_slug, exc
                        )
                    # Continue to next image on failure
                    continue

                # Progress callback
                if self.on_page_download:
                    self.on_page_download(
                        task.manga_slug,
                        task.chapter_slug,
                        task.pages_completed,
                        task.pages_total,
                    )

                # Update progress
                if task.pages_total > 0:
                    task.progress = task.pages_completed / task.pages_total

            # Mark complete
            if task.status != DownloadStatus.CANCELLED:
                if task.pages_completed > 0:
                    task.status = DownloadStatus.COMPLETED
                else:
                    task.status = DownloadStatus.FAILED
                task.progress = 1.0 if task.status == DownloadStatus.COMPLETED else 0.0

                if self.on_chapter_complete:
                    self.on_chapter_complete(
                        task.manga_slug,
                        task.chapter_slug,
                        task.pages_completed,
                    )

        except Exception as exc:
            task.status = DownloadStatus.FAILED
            if self.on_error:
                self.on_error(task.manga_slug, task.chapter_slug, exc)

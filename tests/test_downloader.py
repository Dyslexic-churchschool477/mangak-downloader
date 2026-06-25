"""Tests for ``DownloadQueue`` — the async download engine.

All image downloads are mocked via patching ``MangaKClient.download_image``.
Real filesystem operations (mkdir, write_bytes) are exercised against
``tmp_path`` so we can verify resume behaviour, output paths, etc.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from mangak.core.downloader import DownloadQueue
from mangak.core.exceptions import DownloadError
from mangak.core.models import DownloadStatus, DownloadTask


# =========================================================================
#  Fixtures
# =========================================================================


@pytest.fixture
def sample_task() -> DownloadTask:
    return DownloadTask(
        manga_slug="nano-machine",
        manga_name="Nano Machine",
        chapter_slug="chapter-50",
        chapter_name="Chapter 50",
        chapter_id="ch-50",
        images=[
            "https://rx.qvzra.org/nano-machine/chapter-50/001.webp",
            "https://rx.qvzra.org/nano-machine/chapter-50/002.webp",
            "https://rx.qvzra.org/nano-machine/chapter-50/003.webp",
        ],
        format="cbz",
        output_dir=str(Path("/tmp/downloads")),
        delete_after=False,
    )


@pytest.fixture
def sample_tasks(sample_task) -> list[DownloadTask]:
    t2 = sample_task.model_copy()
    t2.chapter_slug = "chapter-51"
    t2.chapter_name = "Chapter 51"
    t2.chapter_id = "ch-51"
    t2.images = ["https://rx.qvzra.org/nano-machine/chapter-51/001.webp"]
    return [sample_task, t2]


# =========================================================================
#  Queue management (synchronous operations)
# =========================================================================


class TestQueueManagement:
    def test_add_task(self, sample_task):
        q = DownloadQueue()
        assert len(q.tasks) == 0
        q.add_task(sample_task)
        assert len(q.tasks) == 1
        assert sample_task.status == DownloadStatus.QUEUED

    def test_add_tasks(self, sample_tasks):
        q = DownloadQueue()
        q.add_tasks(sample_tasks)
        assert len(q.tasks) == 2
        assert all(t.status == DownloadStatus.QUEUED for t in q.tasks)

    def test_tasks_returns_copy(self, sample_task):
        q = DownloadQueue()
        q.add_task(sample_task)
        tasks = q.tasks
        tasks.clear()
        assert len(q.tasks) == 1  # original unaffected

    def test_pending_count(self, sample_tasks):
        q = DownloadQueue()
        q.add_tasks(sample_tasks)
        assert q.pending_count == 2
        q.tasks[0].status = DownloadStatus.COMPLETED
        assert q.pending_count == 1
        q.tasks[1].status = DownloadStatus.FAILED
        assert q.pending_count == 0

    def test_clear_completed(self, sample_tasks):
        q = DownloadQueue()
        q.add_tasks(sample_tasks)
        q.tasks[0].status = DownloadStatus.COMPLETED
        q.tasks[1].status = DownloadStatus.CANCELLED
        q.clear_completed()
        assert len(q.tasks) == 0

    def test_clear_completed_keeps_active(self, sample_tasks):
        q = DownloadQueue()
        q.add_tasks(sample_tasks)
        q.tasks[0].status = DownloadStatus.COMPLETED
        q.tasks[1].status = DownloadStatus.QUEUED
        q.clear_completed()
        assert len(q.tasks) == 1
        assert q.tasks[0].chapter_slug == "chapter-51"

    def test_pause_and_resume(self):
        q = DownloadQueue()
        assert not q._paused
        q.pause()
        assert q._paused
        q.resume()
        assert not q._paused

    def test_cancel_sets_status(self, sample_tasks):
        q = DownloadQueue()
        q.add_tasks(sample_tasks)
        q.tasks[0].status = DownloadStatus.DOWNLOADING
        q.cancel()
        assert q._cancelled
        assert q.tasks[0].status == DownloadStatus.CANCELLED
        assert q.tasks[1].status == DownloadStatus.CANCELLED

    def test_cancel_does_not_touch_completed(self, sample_tasks):
        q = DownloadQueue()
        q.add_tasks(sample_tasks)
        q.tasks[0].status = DownloadStatus.COMPLETED
        q.cancel()
        assert q.tasks[0].status == DownloadStatus.COMPLETED  # unchanged
        assert q.tasks[1].status == DownloadStatus.CANCELLED


# =========================================================================
#  Execution (async — mocked images)
# =========================================================================


@pytest.mark.asyncio
class TestExecution:
    """All tests patch ``MangaKClient.download_image`` so no real network calls happen."""

    async def test_single_task_success(self, tmp_path, sample_task):
        sample_task.output_dir = str(tmp_path)
        q = DownloadQueue()

        mock_client = AsyncMock()
        mock_client.download_image = AsyncMock(
            side_effect=lambda url, path, use_rotation=True: (
                path.parent.mkdir(parents=True, exist_ok=True) or path.write_bytes(b"page-data") or True
            )
        )

        q.add_task(sample_task)
        await q.run_async(mock_client)

        assert sample_task.status == DownloadStatus.COMPLETED
        assert sample_task.pages_completed == 3
        assert sample_task.progress == 1.0
        assert mock_client.download_image.await_count == 3

        # Verify files were created
        img_dir = tmp_path / "nano-machine" / "chapter-50"
        assert img_dir.exists()
        for i in range(3):
            assert (img_dir / f"{i + 1:03d}.webp").exists()

    async def test_resume_skips_existing_large_files(self, tmp_path, sample_task):
        """Files > 1 KB already present should be skipped."""
        sample_task.output_dir = str(tmp_path)
        img_dir = tmp_path / "nano-machine" / "chapter-50"
        img_dir.mkdir(parents=True)

        # Create first page as > 1 KB file
        f001 = img_dir / "001.webp"
        f001.write_bytes(b"x" * 2000)  # > 1024 bytes

        q = DownloadQueue()
        mock_client = AsyncMock()
        mock_client.download_image = AsyncMock(return_value=True)

        q.add_task(sample_task)
        await q.run_async(mock_client)

        # 3 pages total, 1 skipped (existing), 2 downloaded
        assert sample_task.status == DownloadStatus.COMPLETED
        assert sample_task.pages_completed == 3
        # download_image should have been called 2 times (pages 2 and 3)
        assert mock_client.download_image.await_count == 2

    async def test_resume_does_not_skip_small_files(self, tmp_path, sample_task):
        """Files <= 1 KB should be re-downloaded."""
        sample_task.output_dir = str(tmp_path)
        img_dir = tmp_path / "nano-machine" / "chapter-50"
        img_dir.mkdir(parents=True)

        f001 = img_dir / "001.webp"
        f001.write_bytes(b"small")  # 5 bytes, <= 1024

        q = DownloadQueue()
        mock_client = AsyncMock()
        mock_client.download_image = AsyncMock(return_value=True)

        q.add_task(sample_task)
        await q.run_async(mock_client)

        # All 3 pages should have been downloaded (small file re-downloaded)
        assert mock_client.download_image.await_count == 3

    async def test_all_images_fail(self, tmp_path, sample_task):
        """When every download fails, task ends with FAILED status."""
        sample_task.output_dir = str(tmp_path)

        q = DownloadQueue()
        mock_client = AsyncMock()
        mock_client.download_image = AsyncMock(
            side_effect=DownloadError("Network error")
        )

        q.add_task(sample_task)
        await q.run_async(mock_client)

        assert sample_task.status == DownloadStatus.FAILED
        assert sample_task.pages_completed == 0
        assert sample_task.progress == 0.0

    async def test_partial_failure(self, tmp_path, sample_task):
        """Some images fail, but some succeed — task still completes."""
        sample_task.output_dir = str(tmp_path)

        call_count = 0

        async def _mock_dl(url, path, use_rotation=True):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # second download fails
                raise DownloadError("Network error")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fake-image-data")
            return True

        q = DownloadQueue()
        mock_client = AsyncMock()
        mock_client.download_image = _mock_dl

        q.add_task(sample_task)
        await q.run_async(mock_client)

        # 2 out of 3 succeeded (image 1 and 3)
        assert sample_task.status == DownloadStatus.COMPLETED
        assert sample_task.pages_completed == 2

    async def test_cancel_during_execution(self, tmp_path, sample_task):
        """Cancel should stop processing remaining images and mark task as CANCELLED."""
        sample_task.output_dir = str(tmp_path)
        dl_count = 0

        async def _mock_dl(url, path, use_rotation=True):
            nonlocal dl_count
            dl_count += 1
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"data")
            return True

        q = DownloadQueue()

        # Patch _execute_task to cancel partway through
        original_execute = q._execute_task

        async def _execute_and_cancel(task):
            # Run the first part, then cancel
            if not q._cancelled:
                q.cancel()
            await original_execute(task)

        q._execute_task = _execute_and_cancel
        mock_client = AsyncMock()
        mock_client.download_image = _mock_dl

        q.add_task(sample_task)
        await q.run_async(mock_client)

        assert sample_task.status == DownloadStatus.CANCELLED

    async def test_multiple_tasks(self, tmp_path, sample_tasks):
        """Queue executes all tasks in order."""
        for t in sample_tasks:
            t.output_dir = str(tmp_path)

        q = DownloadQueue()
        mock_client = AsyncMock()
        mock_client.download_image = AsyncMock(return_value=True)

        q.add_tasks(sample_tasks)
        await q.run_async(mock_client)

        for t in sample_tasks:
            assert t.status == DownloadStatus.COMPLETED
            assert t.pages_completed == len(t.images)

    async def test_callback_on_page_download(self, tmp_path, sample_task):
        """on_page_download callback fires after each page."""
        sample_task.output_dir = str(tmp_path)
        calls: list[tuple] = []

        def on_page(manga, chapter, page, total):
            calls.append((manga, chapter, page, total))

        q = DownloadQueue(on_page_download=on_page)
        mock_client = AsyncMock()
        mock_client.download_image = AsyncMock(return_value=True)

        q.add_task(sample_task)
        await q.run_async(mock_client)

        assert len(calls) == 3
        assert calls[0] == ("nano-machine", "chapter-50", 1, 3)
        assert calls[1] == ("nano-machine", "chapter-50", 2, 3)
        assert calls[2] == ("nano-machine", "chapter-50", 3, 3)

    async def test_callback_on_chapter_complete(self, tmp_path, sample_task):
        """on_chapter_complete callback fires after task finishes."""
        sample_task.output_dir = str(tmp_path)
        calls: list[tuple] = []

        def on_complete(manga, chapter, total_pages):
            calls.append((manga, chapter, total_pages))

        q = DownloadQueue(on_chapter_complete=on_complete)
        mock_client = AsyncMock()
        mock_client.download_image = AsyncMock(return_value=True)

        q.add_task(sample_task)
        await q.run_async(mock_client)

        assert len(calls) == 1
        assert calls[0] == ("nano-machine", "chapter-50", 3)

    async def test_callback_on_error(self, tmp_path, sample_task):
        """on_error callback fires when a download fails."""
        sample_task.output_dir = str(tmp_path)
        calls: list[tuple] = []

        def on_err(manga, chapter, exc):
            calls.append((manga, chapter, str(exc)))

        q = DownloadQueue(on_error=on_err)
        mock_client = AsyncMock()
        mock_client.download_image = AsyncMock(
            side_effect=DownloadError("DL failed")
        )

        q.add_task(sample_task)
        await q.run_async(mock_client)

        # Error callback fires for each image that fails
        assert len(calls) == 3
        for manga, chapter, msg in calls:
            assert manga == "nano-machine"
            assert chapter == "chapter-50"
            assert "DL failed" in msg

    async def test_concurrency_semaphore_used(self, tmp_path, sample_task):
        """Verify that the concurrency semaphore is created with the right value."""
        sample_task.output_dir = str(tmp_path)
        q = DownloadQueue()

        mock_client = AsyncMock()
        mock_client.download_image = AsyncMock(return_value=True)

        q.add_task(sample_task)
        await q.run_async(mock_client)

        # _sem should have been created with default concurrency (4)
        assert q._sem is not None
        # Semaphore value defaults to concurrent_downloads (4 from Settings)
        assert q._sem._value == 4

    async def test_empty_queue(self):
        """Running an empty queue should complete immediately."""
        q = DownloadQueue()
        mock_client = AsyncMock()
        await q.run_async(mock_client)
        # Should not raise, no tasks processed
        assert len(q.tasks) == 0


# =========================================================================
#  Queue with real settings path (tmp_path for config)
# =========================================================================


@pytest.mark.asyncio
async def test_queue_owns_client_lifecycle(tmp_path, sample_task):
    """When no client is provided, queue creates and cleans up its own."""
    sample_task.output_dir = str(tmp_path)

    q = DownloadQueue()
    q.add_task(sample_task)

    # Patch MangaKClient entirely so run() uses our mock
    with patch("mangak.core.downloader.MangaKClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_instance.download_image = AsyncMock(return_value=True)
        MockClient.return_value = mock_instance

        await q.run()

        assert sample_task.status == DownloadStatus.COMPLETED
        mock_instance.download_image.assert_called()
        mock_instance.__aenter__.assert_awaited_once()
        mock_instance.__aexit__.assert_awaited_once()

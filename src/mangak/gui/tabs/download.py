"""
MangaK Downloader — "⬇ Download" Tab

Manages active, queued, paused, and completed downloads. Shows per-item
progress bars, pause/resume/cancel controls, and batch operations.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import (
    QObject,
    QThread,
    QTimer,
    pyqtSignal,
    pyqtSlot,
    Qt,
)
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mangak.core import (
    DownloadTask,
    DownloadStatus,
    DownloadQueue,
    DownloadDB,
    Settings,
    MangaKClient,
    export_folder,
    export_cbz,
    export_zip,
    export_pdf,
)
from mangak.core.themes import Colors
from mangak.gui.widgets.glass_panel import GlassPanel
from mangak.gui.widgets.progress_ring import ProgressRing
from mangak.gui.widgets.toast import ToastManager


# ──────────────────────────────────────────────
#  Worker: process queue in background
# ──────────────────────────────────────────────


class _QueueWorker(QObject):
    """Runs DownloadQueue in a background thread."""

    task_progress = pyqtSignal(str, str, int, int)  # manga_slug, chapter_slug, completed, total
    task_completed = pyqtSignal(str, str, int)       # manga_slug, chapter_slug, total_pages
    task_error = pyqtSignal(str, str, str)           # manga_slug, chapter_slug, error_msg
    task_paused = pyqtSignal(str, str)
    task_cancelled = pyqtSignal(str, str)
    finished = pyqtSignal()

    def __init__(self, tasks: list[DownloadTask], parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._tasks = tasks
        self._queue: Optional[DownloadQueue] = None
        self._paused_tasks: list[DownloadTask] = []
        self._cancelled = False

    @pyqtSlot()
    def run(self) -> None:
        import asyncio

        async def _worker_main() -> None:
            # Step 1: fetch chapter images for each task (with delay + retry)
            self.task_progress.emit("", "", 0, len(self._tasks))
            async with MangaKClient() as client:
                for i, task in enumerate(self._tasks):
                    if self._cancelled:
                        return
                    if task.images and len(task.images) > 0:
                        continue

                    # Retry up to 3 times with backoff
                    for attempt in range(3):
                        if self._cancelled:
                            return
                        try:
                            chapter = await client.get_chapter(task.manga_slug, task.chapter_slug)
                            task.images = [str(u) for u in chapter.images]
                            task.pages_total = len(task.images)
                            break  # success
                        except Exception as exc:
                            if attempt < 2:
                                await asyncio.sleep(1.0 * (attempt + 1))
                                continue
                            self.task_error.emit(
                                task.manga_slug, task.chapter_slug,
                                f"Failed to fetch chapter images: {exc}"
                            )

                    # Small delay between chapter fetches to avoid rate limiting
                    await asyncio.sleep(0.5)
                    self.task_progress.emit("", "", i + 1, len(self._tasks))

            # Step 2: run download queue with progress
            pending = [t for t in self._tasks if t.images]
            if not pending:
                self.finished.emit()
                return

            self._queue = DownloadQueue(
                settings=Settings(),
                on_page_download=self._on_page,
                on_error=self._on_error,
            )
            self._queue.add_tasks(pending)

            try:
                await self._queue.run()
            except Exception:
                pass
            finally:
                # Step 3: export completed tasks to configured format, then signal completion
                for task in pending:
                    if task.status in (DownloadStatus.DOWNLOADING, DownloadStatus.COMPLETED) and task.images:
                        try:
                            images_dir = Path(task.output_dir) / task.manga_slug / task.chapter_slug
                            if images_dir.exists():
                                task.status = DownloadStatus.EXPORTING
                                self.task_progress.emit(task.manga_slug, task.chapter_slug, task.pages_completed, task.pages_total)
                                # Yield so Qt processes the EXPORTING signal and shows "Converting..." in UI
                                await asyncio.sleep(0.05)
                                fmt = task.format
                                if fmt == "folder":
                                    export_folder(images_dir, images_dir.parent, delete_after=task.delete_after)
                                elif fmt == "cbz":
                                    out = Path(task.output_dir) / f"{task.manga_slug}-{task.chapter_slug}.cbz"
                                    export_cbz(images_dir, out, delete_after=task.delete_after)
                                elif fmt == "zip":
                                    out = Path(task.output_dir) / f"{task.manga_slug}-{task.chapter_slug}.zip"
                                    export_zip(images_dir, out, delete_after=task.delete_after)
                                elif fmt == "pdf":
                                    out = Path(task.output_dir) / f"{task.manga_slug}-{task.chapter_slug}.pdf"
                                    export_pdf(images_dir, out, delete_after=task.delete_after)
                                task.status = DownloadStatus.COMPLETED
                                self.task_completed.emit(task.manga_slug, task.chapter_slug, task.pages_completed)
                        except Exception:
                            task.status = DownloadStatus.FAILED
                self.finished.emit()

        asyncio.run(_worker_main())

    def pause(self) -> None:
        if self._queue:
            self._queue.pause()

    def resume(self) -> None:
        if self._queue:
            self._queue.resume()

    def cancel(self) -> None:
        if self._queue:
            self._queue.cancel()

    def _on_page(self, manga: str, chapter: str, completed: int, total: int) -> None:
        self.task_progress.emit(manga, chapter, completed, total)

    def _on_chapter_done(self, manga: str, chapter: str, pages: int) -> None:
        self.task_completed.emit(manga, chapter, pages)

    def _on_error(self, manga: str, chapter: str, exc: Exception) -> None:
        self.task_error.emit(manga, chapter, str(exc))


# ──────────────────────────────────────────────
#  Single download item widget
# ──────────────────────────────────────────────


class _DownloadItem(QFrame):
    """Represents one download task in the active/queued list."""

    pause_requested = pyqtSignal(str, str)    # manga_slug, chapter_slug
    resume_requested = pyqtSignal(str, str)
    cancel_requested = pyqtSignal(str, str)

    def __init__(self, task: DownloadTask, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._task = task
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("downloadItem")
        self.setStyleSheet(f"""
            #downloadItem {{
                background: {Colors.BG_SURFACE};
                border: 1px solid {Colors.BORDER};
                border-radius: 10px;
                padding: 12px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        # Top row: name + status
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self._name_label = QLabel(f"{self._task.manga_name} — {self._task.chapter_name}")
        self._name_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 14px; font-weight: bold;")
        self._name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        top_row.addWidget(self._name_label)

        self._status_label = QLabel(self._task.status.value)
        self._status_label.setStyleSheet(f"""
            color: {Colors.ACCENT_SECONDARY};
            font-size: 12px;
            padding: 2px 8px;
            border-radius: 4px;
        """)
        top_row.addWidget(self._status_label)

        # Progress ring
        self._progress_ring = ProgressRing()
        self._progress_ring.setFixedSize(40, 40)
        top_row.addWidget(self._progress_ring)

        layout.addLayout(top_row)

        # Progress bar and details
        progress_row = QHBoxLayout()
        progress_row.setSpacing(12)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {Colors.BG_ELEVATED};
                border: none;
                border-radius: 4px;
                text-align: center;
                font-size: 0px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 {Colors.ACCENT_PRIMARY},
                    stop: 1 {Colors.ACCENT_SECONDARY}
                );
                border-radius: 4px;
            }}
        """)
        progress_row.addWidget(self._progress_bar, 1)

        self._pages_label = QLabel("0 / 0 pages")
        self._pages_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 11px;")
        progress_row.addWidget(self._pages_label)

        layout.addLayout(progress_row)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.setContentsMargins(0, 4, 0, 0)

        self._pause_btn = QPushButton("⏸ Pause")
        self._pause_btn.setFixedHeight(30)
        self._pause_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.WARNING}33;
                color: {Colors.WARNING};
                border: none;
                border-radius: 6px;
                padding: 0 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {Colors.WARNING}55;
            }}
        """)
        self._pause_btn.clicked.connect(lambda: self.pause_requested.emit(
            self._task.manga_slug, self._task.chapter_slug
        ))
        btn_row.addWidget(self._pause_btn)

        self._resume_btn = QPushButton("▶ Resume")
        self._resume_btn.setFixedHeight(30)
        self._resume_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.SUCCESS}33;
                color: {Colors.SUCCESS};
                border: none;
                border-radius: 6px;
                padding: 0 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {Colors.SUCCESS}55;
            }}
        """)
        self._resume_btn.clicked.connect(lambda: self.resume_requested.emit(
            self._task.manga_slug, self._task.chapter_slug
        ))
        self._resume_btn.setVisible(False)
        btn_row.addWidget(self._resume_btn)

        self._cancel_btn = QPushButton("✖ Cancel")
        self._cancel_btn.setFixedHeight(30)
        self._cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.DANGER}33;
                color: {Colors.DANGER};
                border: none;
                border-radius: 6px;
                padding: 0 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {Colors.DANGER}55;
            }}
        """)
        self._cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(
            self._task.manga_slug, self._task.chapter_slug
        ))
        btn_row.addWidget(self._cancel_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._update_ui()

    def _update_ui(self) -> None:
        pct = int(self._task.progress * 100)
        self._progress_bar.setValue(pct)
        self._progress_ring.set_value(self._task.progress)
        self._progress_ring.set_label(f"{pct}%")
        self._pages_label.setText(
            f"{self._task.pages_completed} / {self._task.pages_total} pages"
        )

        is_active = self._task.status == DownloadStatus.DOWNLOADING
        is_exporting = self._task.status == DownloadStatus.EXPORTING
        is_paused = self._task.status == DownloadStatus.PAUSED
        is_queued = self._task.status == DownloadStatus.QUEUED
        is_done = self._task.status in (
            DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED
        )

        if is_exporting:
            self._status_label.setText("Converting...")
            self._status_label.setStyleSheet(f"color: {Colors.ACCENT_SECONDARY}; font-size: 12px;")
            self._name_label.setText(f"{self._task.manga_name} — {self._task.chapter_name} (exporting)")
        else:
            self._name_label.setText(f"{self._task.manga_name} — {self._task.chapter_name}")
            self._status_label.setText(self._task.status.value)

        self._pause_btn.setVisible(is_active or is_queued)
        self._resume_btn.setVisible(is_paused)
        self._cancel_btn.setVisible(not is_done and not is_exporting)

        if is_active:
            self._status_label.setStyleSheet(f"color: {Colors.ACCENT_PRIMARY}; font-size: 12px;")
        elif is_paused:
            self._status_label.setStyleSheet(f"color: {Colors.WARNING}; font-size: 12px;")
        elif self._task.status == DownloadStatus.COMPLETED:
            self._status_label.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 12px;")
        elif self._task.status == DownloadStatus.FAILED:
            self._status_label.setStyleSheet(f"color: {Colors.DANGER}; font-size: 12px;")
        elif is_exporting:
            self._status_label.setStyleSheet(f"color: {Colors.ACCENT_SECONDARY}; font-size: 12px;")
        else:
            self._status_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 12px;")

    def update_task(self, task: DownloadTask) -> None:
        self._task = task
        self._update_ui()

    def task_slug(self) -> tuple[str, str]:
        return (self._task.manga_slug, self._task.chapter_slug)

    @property
    def task(self) -> DownloadTask:
        return self._task


# ──────────────────────────────────────────────
#  Completed item widget
# ──────────────────────────────────────────────


class _CompletedItem(QFrame):
    """Shows a completed download with format badge and open-folder button."""

    def __init__(
        self,
        manga_name: str,
        chapter_name: str,
        fmt: str,
        file_size: str,
        file_path: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._file_path = file_path
        self._setup_ui(manga_name, chapter_name, fmt, file_size)

    def _setup_ui(self, manga: str, chapter: str, fmt: str, size: str) -> None:
        self.setObjectName("completedItem")
        self.setStyleSheet(f"""
            #completedItem {{
                background: {Colors.BG_SURFACE};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 8px 12px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)

        icon_label = QLabel("✅")
        icon_label.setFixedWidth(20)
        layout.addWidget(icon_label)

        name_label = QLabel(f"{manga} — {chapter}")
        name_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px;")
        name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(name_label)

        fmt_badge = QLabel(fmt.upper())
        fmt_badge.setStyleSheet(f"""
            background: {Colors.ACCENT_PRIMARY}44;
            color: {Colors.ACCENT_PRIMARY};
            border: none;
            border-radius: 4px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: bold;
        """)
        fmt_badge.setFixedHeight(22)
        layout.addWidget(fmt_badge)

        size_label = QLabel(size)
        size_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(size_label)

        open_btn = QPushButton("📂 Open")
        open_btn.setFixedHeight(30)
        open_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Colors.ACCENT_PRIMARY};
                border: 1px solid {Colors.ACCENT_PRIMARY};
                border-radius: 6px;
                padding: 0 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {Colors.ACCENT_PRIMARY}33;
            }}
        """)
        open_btn.clicked.connect(self._on_open)
        layout.addWidget(open_btn)

    def _on_open(self) -> None:
        path = Path(self._file_path)
        if path.exists():
            os.startfile(str(path.parent) if path.is_file() else str(path))
        else:
            ToastManager.show_toast_cls("Error", "File not found", "error")


# ──────────────────────────────────────────────
#  Download Tab
# ──────────────────────────────────────────────


class DownloadTab(QWidget):
    """'⬇ Download' tab: manage active/queued/completed downloads."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._settings = Settings()
        self._db = DownloadDB()

        # Active items: dict keyed by (manga_slug, chapter_slug) -> _DownloadItem
        self._active_items: dict[tuple[str, str], _DownloadItem] = {}
        self._queued_items: dict[tuple[str, str], _DownloadItem] = {}
        self._task_map: dict[tuple[str, str], DownloadTask] = {}

        self._worker: Optional[_QueueWorker] = None
        self._worker_thread: Optional[QThread] = None

        self._setup_ui()
        self._refresh_completed()

    # ── UI Setup ───────────────────────────────

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"""
            DownloadTab {{
                background: {Colors.BG_BASE};
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # ── Title ──
        title = QLabel("⬇  Downloads")
        title_font = QFont("Segoe UI", 18, QFont.Weight.Bold)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        root.addWidget(title)

        # ── Active downloads ──
        active_header = QLabel("▶ Active")
        active_header.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 15px; font-weight: bold;")
        root.addWidget(active_header)

        self._active_panel = GlassPanel()
        self._active_layout = QVBoxLayout(self._active_panel)
        self._active_layout.setContentsMargins(12, 12, 12, 12)
        self._active_layout.setSpacing(8)

        self._active_empty = QLabel("No active downloads")
        self._active_empty.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 13px;")
        self._active_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._active_layout.addWidget(self._active_empty)

        root.addWidget(self._active_panel)

        # ── Queued downloads ──
        queued_header = QLabel("⏳ Queued")
        queued_header.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 15px; font-weight: bold;")
        root.addWidget(queued_header)

        self._queued_panel = GlassPanel()
        self._queued_layout = QVBoxLayout(self._queued_panel)
        self._queued_layout.setContentsMargins(12, 12, 12, 12)
        self._queued_layout.setSpacing(4)

        self._queued_empty = QLabel("No queued downloads")
        self._queued_empty.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 13px;")
        self._queued_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._queued_layout.addWidget(self._queued_empty)

        root.addWidget(self._queued_panel)

        # ── Completed downloads (scrollable) ──
        completed_header = QHBoxLayout()
        compl_label = QLabel("✅ Completed")
        compl_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 15px; font-weight: bold;")
        completed_header.addWidget(compl_label)
        completed_header.addStretch()

        self._clear_completed_btn = QPushButton("🗑 Clear Completed")
        self._clear_completed_btn.setFixedHeight(30)
        self._clear_completed_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Colors.DANGER};
                border: 1px solid {Colors.DANGER}66;
                border-radius: 6px;
                padding: 0 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {Colors.DANGER}22;
            }}
        """)
        self._clear_completed_btn.clicked.connect(self._on_clear_completed)
        completed_header.addWidget(self._clear_completed_btn)

        root.addLayout(completed_header)

        self._completed_scroll = QScrollArea()
        self._completed_scroll.setWidgetResizable(True)
        self._completed_scroll.setMaximumHeight(240)
        self._completed_scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{
                background: {Colors.BG_SURFACE};
                width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {Colors.BORDER}; border-radius: 4px;
            }}
        """)

        self._completed_container = QWidget()
        self._completed_container.setStyleSheet("background: transparent;")
        self._completed_list = QVBoxLayout(self._completed_container)
        self._completed_list.setContentsMargins(0, 0, 0, 0)
        self._completed_list.setSpacing(4)
        self._completed_list.addStretch()

        self._completed_scroll.setWidget(self._completed_container)
        root.addWidget(self._completed_scroll, 1)

        # ── Controls bar ──
        controls = GlassPanel()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(16, 10, 16, 10)
        controls_layout.setSpacing(12)

        self._pause_all_btn = QPushButton("⏸ Pause All")
        self._pause_all_btn.setFixedHeight(32)
        self._pause_all_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.WARNING}33;
                color: {Colors.WARNING};
                border: none;
                border-radius: 6px;
                padding: 0 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: {Colors.WARNING}55; }}
        """)
        self._pause_all_btn.clicked.connect(self._on_pause_all)
        controls_layout.addWidget(self._pause_all_btn)

        self._resume_all_btn = QPushButton("▶ Resume All")
        self._resume_all_btn.setFixedHeight(32)
        self._resume_all_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.SUCCESS}33;
                color: {Colors.SUCCESS};
                border: none;
                border-radius: 6px;
                padding: 0 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: {Colors.SUCCESS}55; }}
        """)
        self._resume_all_btn.clicked.connect(self._on_resume_all)
        controls_layout.addWidget(self._resume_all_btn)

        root.addWidget(controls)

        # ── Auto-refresh timer for completed list ──
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(3000)
        self._refresh_timer.timeout.connect(self._refresh_completed)
        self._refresh_timer.start()

    # ── Public API ─────────────────────────────

    def add_task(self, task: DownloadTask) -> None:
        """Add a download task and start the queue if not running."""
        key = (task.manga_slug, task.chapter_slug)
        self._task_map[key] = task

        # Create a queued item widget
        item = _DownloadItem(task)
        item.cancel_requested.connect(self._on_cancel_item)
        item.pause_requested.connect(self._on_pause_item)
        item.resume_requested.connect(self._on_resume_item)
        self._queued_items[key] = item
        self._queued_empty.setVisible(False)

        # Insert before stretch
        self._queued_layout.insertWidget(
            self._queued_layout.count() - 1, item
        )

        # Start the worker if not running (deferred so all tasks queue first)
        QTimer.singleShot(0, self._ensure_worker_running)

    def add_tasks(self, tasks: list[DownloadTask]) -> None:
        for t in tasks:
            self.add_task(t)

    def _ensure_worker_running(self) -> None:
        # Guard: if thread was deleted, reset references
        try:
            if self._worker_thread is not None:
                try:
                    if self._worker_thread.isRunning():
                        return
                except RuntimeError:
                    self._worker_thread = None
                    self._worker = None
        except RuntimeError:
            self._worker_thread = None
            self._worker = None

        pending = [
            t for t in self._task_map.values()
            if t.status in (DownloadStatus.QUEUED, DownloadStatus.PAUSED)
        ]
        if not pending:
            return

        self._worker = _QueueWorker(list(pending))
        self._worker_thread = QThread()
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.run)
        self._worker.task_progress.connect(self._on_task_progress)
        self._worker.task_completed.connect(self._on_task_completed)
        self._worker.task_error.connect(self._on_task_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._worker.deleteLater)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)

        self._worker_thread.start()

    # ── Slots ──────────────────────────────────

    @pyqtSlot(str, str, int, int)
    def _on_task_progress(self, manga: str, chapter: str, completed: int, total: int) -> None:
        key = (manga, chapter)
        task = self._task_map.get(key)
        if task is None:
            return

        # Don't override EXPORTING status
        if task.status == DownloadStatus.EXPORTING:
            # Just update the existing item's UI (name changes to show "exporting")
            item = self._active_items.get(key) or self._queued_items.get(key)
            if item:
                item.update_task(task)
            return

        task.status = DownloadStatus.DOWNLOADING
        task.pages_completed = completed
        task.pages_total = total
        task.progress = completed / total if total > 0 else 0.0

        # Move from queued to active
        if key in self._queued_items:
            item = self._queued_items.pop(key)
            self._queued_layout.removeWidget(item)
            self._active_items[key] = item
            self._active_layout.insertWidget(
                self._active_layout.count() - 1 if self._active_empty.isVisible() else self._active_layout.count() - 1,
                item
            )
            self._active_empty.setVisible(False)
            if not self._queued_items:
                self._queued_empty.setVisible(True)

        item = self._active_items.get(key) or self._queued_items.get(key)
        if item:
            item.update_task(task)

    @pyqtSlot(str, str, int)
    def _on_task_completed(self, manga: str, chapter: str, pages: int) -> None:
        key = (manga, chapter)
        task = self._task_map.get(key)
        if task is None:
            return

        task.status = DownloadStatus.COMPLETED
        task.progress = 1.0
        task.pages_completed = pages
        task.pages_total = pages

        # Remove from active/queued
        item = self._active_items.pop(key, None) or self._queued_items.pop(key, None)
        if item:
            self._active_layout.removeWidget(item)
            item.deleteLater()

        if not self._active_items:
            self._active_empty.setVisible(True)
        if not self._queued_items:
            self._queued_empty.setVisible(True)

        # Record in DB
        try:
            dl_dir = Path(self._settings.get("download_dir", "downloads"))
            output_path = dl_dir / manga / chapter
            file_size = 0
            if output_path.exists():
                file_size = sum(
                    f.stat().st_size for f in output_path.rglob("*") if f.is_file()
                )

            self._db.record_download(
                manga_slug=manga,
                manga_name=task.manga_name,
                chapter_slug=chapter,
                chapter_name=task.chapter_name,
                format=task.format,
                pages_count=pages,
                file_path=str(output_path),
                file_size_kb=file_size // 1024,
            )
        except Exception:
            pass

        self._refresh_completed()
        ToastManager.show_toast_cls("Complete", f"{task.manga_name} — {task.chapter_name}", "success")

    @pyqtSlot(str, str, str)
    def _on_task_error(self, manga: str, chapter: str, error_msg: str) -> None:
        key = (manga, chapter)
        task = self._task_map.get(key)
        if task:
            task.status = DownloadStatus.FAILED

        item = self._active_items.pop(key, None) or self._queued_items.pop(key, None)
        if item:
            self._active_layout.removeWidget(item)
            item.deleteLater()

        if not self._active_items:
            self._active_empty.setVisible(True)
        if not self._queued_items:
            self._queued_empty.setVisible(True)

        ToastManager.show_toast_cls("Download Error", error_msg, "error")

    def _on_worker_finished(self) -> None:
        # Check for remaining queued tasks
        remaining = [
            t for t in self._task_map.values()
            if t.status in (DownloadStatus.QUEUED, DownloadStatus.PAUSED)
        ]
        if remaining:
            self._ensure_worker_running()

    def _on_pause_item(self, manga: str, chapter: str) -> None:
        key = (manga, chapter)
        task = self._task_map.get(key)
        if task:
            task.status = DownloadStatus.PAUSED
        item = self._active_items.get(key) or self._queued_items.get(key)
        if item:
            item.update_task(task)  # type: ignore[arg-type]
        if self._worker:
            self._worker.pause()

    def _on_resume_item(self, manga: str, chapter: str) -> None:
        key = (manga, chapter)
        task = self._task_map.get(key)
        if task:
            task.status = DownloadStatus.QUEUED
        item = self._active_items.get(key) or self._queued_items.get(key)
        if item:
            item.update_task(task)  # type: ignore[arg-type]
        if self._worker:
            self._worker.resume()
        self._ensure_worker_running()

    def _on_cancel_item(self, manga: str, chapter: str) -> None:
        key = (manga, chapter)
        task = self._task_map.get(key)
        if task:
            task.status = DownloadStatus.CANCELLED

        item = self._active_items.pop(key, None) or self._queued_items.pop(key, None)
        if item:
            layout = self._active_layout if key in self._active_items else self._queued_layout
            layout.removeWidget(item)
            item.deleteLater()

        if not self._active_items:
            self._active_empty.setVisible(True)
        if not self._queued_items:
            self._queued_empty.setVisible(True)

        if self._worker:
            self._worker.cancel()

    def _on_pause_all(self) -> None:
        if self._worker:
            self._worker.pause()
        for key, item in list(self._active_items.items()) + list(self._queued_items.items()):
            task = self._task_map.get(key)
            if task and task.status in (DownloadStatus.DOWNLOADING, DownloadStatus.QUEUED):
                task.status = DownloadStatus.PAUSED
                item.update_task(task)

    def _on_resume_all(self) -> None:
        if self._worker:
            self._worker.resume()
        for key, item in list(self._active_items.items()) + list(self._queued_items.items()):
            task = self._task_map.get(key)
            if task and task.status == DownloadStatus.PAUSED:
                task.status = DownloadStatus.QUEUED
                item.update_task(task)
        self._ensure_worker_running()

    def _on_clear_completed(self) -> None:
        self._clear_completed_list()
        ToastManager.show_toast_cls("Cleared", "Completed downloads cleared", "info")

    # ── Completed list management ──────────────

    def _refresh_completed(self) -> None:
        try:
            records = self._db.get_history(limit=50)
        except Exception:
            return

        # Only clear/rebuild if count changed
        self._clear_completed_list()
        for rec in records:
            size_str = (
                f"{rec.get('file_size_kb', 0)} KB"
                if rec.get('file_size_kb')
                else "—"
            )
            item = _CompletedItem(
                manga_name=rec.get("manga_name", ""),
                chapter_name=rec.get("chapter_name", ""),
                fmt=rec.get("format", ""),
                file_size=size_str,
                file_path=rec.get("file_path", ""),
            )
            self._completed_list.insertWidget(
                self._completed_list.count() - 1, item
            )

    def _clear_completed_list(self) -> None:
        while self._completed_list.count() > 0:
            item = self._completed_list.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._completed_list.addStretch()
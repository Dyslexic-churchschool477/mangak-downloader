"""
MangaK Downloader — "🔍 Search" Tab

Search manga by name with genre filters and card grid results.
Search only triggers on button click or Enter key — no auto-debounce.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import (
    QObject,
    QThread,
    pyqtSignal,
    pyqtSlot,
    Qt,
)
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mangak.core import MangaKClient, SearchResult
from mangak.core.themes import Colors
from mangak.gui.widgets.glass_panel import GlassPanel
from mangak.gui.widgets.manga_card import MangaCard
from mangak.gui.widgets.toast import ToastManager


class _SearchWorker(QObject):
    """Performs search in a background thread."""

    finished = pyqtSignal(list, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, query: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._query = query

    @pyqtSlot()
    def run(self) -> None:
        import asyncio
        try:
            async def _search() -> list[SearchResult]:
                async with MangaKClient() as client:
                    return await client.search(self._query)
            results = asyncio.run(_search())
            self.finished.emit(results, self._query)
        except Exception as exc:
            self.error_occurred.emit(str(exc))


class _GenreChip(QPushButton):
    """Toggle button styled as a genre chip."""

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setFixedHeight(30)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_SURFACE}; color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER}; border-radius: 15px;
                padding: 0 14px; font-size: 12px;
            }}
            QPushButton:hover {{
                background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
            }}
            QPushButton:checked {{
                background: {Colors.ACCENT_PRIMARY}44; color: {Colors.ACCENT_PRIMARY};
                border-color: {Colors.ACCENT_PRIMARY};
            }}
        """)


class MangaByNameTab(QWidget):
    """'🔍 Search' tab — search on button click / Enter only."""

    manga_selected = pyqtSignal(str)

    GENRES = ["All", "Action", "Fantasy", "Romance", "Comedy", "Sci-Fi", "Drama",
              "Horror", "Thriller", "Mystery", "Slice of Life", "Adventure",
              "Martial Arts", "Harem", "Isekai", "Shounen", "Seinen", "Shoujo"]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_results: list[SearchResult] = []
        self._all_results: list[SearchResult] = []
        self._current_query = ""
        self._page = 0
        self._page_size = 20
        self._worker: Optional[_SearchWorker] = None
        self._worker_thread: Optional[QThread] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"MangaByNameTab {{ background: {Colors.BG_BASE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # Title
        title = QLabel("🔍  Search Manga")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        root.addWidget(title)

        # Search bar (button click or Enter only — no debounce)
        search_panel = GlassPanel()
        search_layout = QHBoxLayout(search_panel)
        search_layout.setContentsMargins(16, 12, 16, 12)
        search_layout.setSpacing(12)
        search_layout.addWidget(QLabel("🔍"))

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search manga by name…")
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {Colors.BG_SURFACE}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER}; border-radius: 8px;
                padding: 8px 14px; font-size: 14px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT_PRIMARY}; }}
        """)
        self._search_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self._search_input, 1)

        self._search_btn = QPushButton("Search")
        self._search_btn.setFixedHeight(36)
        self._search_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ACCENT_PRIMARY}; color: white;
                border: none; border-radius: 8px; padding: 0 20px;
                font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {Colors.ACCENT_PRIMARY}CC; }}
            QPushButton:pressed {{ background: {Colors.ACCENT_PRIMARY}AA; }}
            QPushButton:disabled {{ background: {Colors.BORDER}; color: {Colors.TEXT_SECONDARY}; }}
        """)
        self._search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(self._search_btn)
        root.addWidget(search_panel)

        # Genre filters
        genre_panel = GlassPanel()
        genre_layout = QVBoxLayout(genre_panel)
        genre_layout.setContentsMargins(12, 8, 12, 8)
        genre_layout.setSpacing(6)
        genre_label = QLabel("Genres")
        genre_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold;")
        genre_layout.addWidget(genre_label)

        self._genre_group = QButtonGroup(self)
        self._genre_group.setExclusive(True)
        scroll_genre = QScrollArea()
        scroll_genre.setWidgetResizable(True)
        scroll_genre.setFixedHeight(46)
        scroll_genre.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        genre_inner = QWidget()
        genre_inner.setStyleSheet("background: transparent;")
        genre_flow = QHBoxLayout(genre_inner)
        genre_flow.setContentsMargins(0, 0, 0, 0)
        genre_flow.setSpacing(6)

        for i, g in enumerate(self.GENRES):
            chip = _GenreChip(g)
            chip.setChecked(i == 0)
            self._genre_group.addButton(chip, i)
            chip.toggled.connect(self._on_genre_changed)
            genre_flow.addWidget(chip)
        genre_flow.addStretch()
        scroll_genre.setWidget(genre_inner)
        genre_layout.addWidget(scroll_genre)
        root.addWidget(genre_panel)

        # Results header
        results_header = QHBoxLayout()
        results_header.setSpacing(12)
        self._results_count = QLabel("Results: —")
        self._results_count.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 13px;")
        results_header.addWidget(self._results_count)
        results_header.addStretch()
        self._sort_combo = QComboBox()
        self._sort_combo.addItems(["Relevance", "Rating", "Name", "Newest"])
        self._sort_combo.setStyleSheet(f"""
            QComboBox {{
                background: {Colors.BG_SURFACE}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER}; border-radius: 6px;
                padding: 4px 10px; font-size: 12px;
            }}
            QComboBox::drop-down {{ border: none; }}
        """)
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        results_header.addWidget(QLabel("Sort:"))
        results_header.addWidget(self._sort_combo)
        root.addLayout(results_header)

        # Loading
        self._loading_label = QLabel("")
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 14px;")
        self._loading_label.setVisible(False)
        root.addWidget(self._loading_label)

        # Card grid using QVBoxLayout with horizontal rows
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setStyleSheet(f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{
                background: {Colors.BG_SURFACE}; width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{ background: {Colors.BORDER}; border-radius: 4px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self._card_container = QWidget()
        self._card_container.setStyleSheet("background: transparent;")
        self._card_grid = QVBoxLayout(self._card_container)
        self._card_grid.setContentsMargins(0, 0, 0, 0)
        self._card_grid.setSpacing(12)
        self._scroll_area.setWidget(self._card_container)
        root.addWidget(self._scroll_area, 1)

        # Load More
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)
        self._load_more_btn = QPushButton("Load More")
        self._load_more_btn.setFixedHeight(36)
        self._load_more_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_SURFACE}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER}; border-radius: 8px;
                padding: 0 20px; font-size: 13px;
            }}
            QPushButton:hover {{ background: {Colors.BG_ELEVATED}; }}
            QPushButton:disabled {{ color: {Colors.TEXT_SECONDARY}; }}
        """)
        self._load_more_btn.clicked.connect(self._on_load_more)
        self._load_more_btn.setVisible(False)
        bottom_row.addWidget(self._load_more_btn)
        bottom_row.addStretch()
        root.addLayout(bottom_row)

    # ── Slots ──────────────────────────────────

    def _on_search(self) -> None:
        query = self._search_input.text().strip()
        if not query:
            self._clear_results()
            return

        self._current_query = query
        self._page = 0
        self._loading_label.setText("🔍 Searching…")
        self._loading_label.setVisible(True)
        self._search_btn.setEnabled(False)
        self._clear_card_grid()

        # Kill previous worker thread before creating a new one
        self._cleanup_worker()

        self._worker = _SearchWorker(query)
        self._worker_thread = QThread(self)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_search_results)
        self._worker.error_occurred.connect(self._on_search_error)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.error_occurred.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._worker.deleteLater)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.start()

    def _cleanup_worker(self) -> None:
        """Safely kill the previous worker thread if still running."""
        if self._worker_thread is not None:
            try:
                if self._worker_thread.isRunning():
                    self._worker_thread.quit()
                    self._worker_thread.wait(1000)
            except RuntimeError:
                pass
            self._worker_thread = None
            self._worker = None

    def _on_genre_changed(self) -> None:
        self._filter_and_display()

    def _on_sort_changed(self) -> None:
        self._filter_and_display()

    @pyqtSlot(list, str)
    def _on_search_results(self, results: list[SearchResult], query: str) -> None:
        self._loading_label.setVisible(False)
        self._search_btn.setEnabled(True)
        if query != self._current_query:
            return
        self._all_results = results
        self._results_count.setText(f"Results: {len(results)} found")
        self._load_more_btn.setVisible(len(results) > self._page_size)
        self._filter_and_display()

    @pyqtSlot(str)
    def _on_search_error(self, error_msg: str) -> None:
        self._loading_label.setVisible(False)
        self._search_btn.setEnabled(True)
        ToastManager.show_toast_cls("Search Error", error_msg, "error")

    def _filter_and_display(self) -> None:
        selected_id = self._genre_group.checkedId()
        selected_genre = self.GENRES[selected_id] if selected_id >= 0 else "All"
        filtered = self._all_results
        if selected_genre != "All":
            filtered = [r for r in filtered if any(g.name.lower() == selected_genre.lower() for g in r.genres)]

        sort_mode = self._sort_combo.currentText()
        if sort_mode == "Rating":
            filtered.sort(key=lambda r: r.rating, reverse=True)
        elif sort_mode == "Name":
            filtered.sort(key=lambda r: r.name.lower())

        self._current_results = filtered
        self._page = 0
        self._results_count.setText(f"Results: {len(filtered)} found")
        self._load_more_btn.setVisible(len(filtered) > self._page_size)
        self._render_page()

    def _render_page(self) -> None:
        if self._page == 0:
            self._clear_card_grid()

        start = self._page * self._page_size
        end = min(start + self._page_size, len(self._current_results))
        page_results = self._current_results[start:end]

        if not page_results and self._page == 0:
            no = QLabel("No results found. Try a different search term.")
            no.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 14px;")
            no.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._card_grid.addWidget(no)
            self._card_grid.addStretch()
            return

        items_per_row = 4
        current_row = None
        for i, result in enumerate(page_results):
            col_idx = i % items_per_row
            if col_idx == 0:
                current_row = QHBoxLayout()
                current_row.setSpacing(12)
                self._card_grid.addLayout(current_row)

            card = MangaCard()
            card.set_data(
                slug=result.slug, title=result.name,
                cover_url=str(result.cover) if result.cover else "",
                status=result.status, rating=result.rating,
            )
            card.clicked_with_slug.connect(self._on_card_clicked)
            if current_row is not None:
                current_row.addWidget(card)

    def _on_card_clicked(self, slug: str) -> None:
        self.manga_selected.emit(slug)
        ToastManager.show_toast_cls("Selected", f"Loading {slug}…", "info")

    def _on_load_more(self) -> None:
        self._page += 1
        self._render_page()
        self._load_more_btn.setVisible((self._page + 1) * self._page_size < len(self._current_results))

    def _clear_results(self) -> None:
        self._all_results = []
        self._current_results = []
        self._current_query = ""
        self._results_count.setText("Results: —")
        self._clear_card_grid()
        self._load_more_btn.setVisible(False)

    def _clear_card_grid(self) -> None:
        while self._card_grid.count():
            item = self._card_grid.takeAt(0)
            if item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        # Stop any running loader thread before deleting
                        if isinstance(child.widget(), MangaCard):
                            child.widget().stop_loader()
                        child.widget().deleteLater()
            if item.widget():
                if isinstance(item.widget(), MangaCard):
                    item.widget().stop_loader()
                item.widget().deleteLater()

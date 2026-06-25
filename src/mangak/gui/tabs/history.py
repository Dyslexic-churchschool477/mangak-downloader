"""
MangaK Downloader — "📜 History" Tab

Searchable download history table with pagination and stats.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import (
    QTimer,
    Qt,
)
from PyQt6.QtGui import QColor, QFont, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mangak.core import DownloadDB
from mangak.core.exceptions import MangaKError
from mangak.core.themes import Colors
from mangak.gui.widgets.glass_panel import GlassPanel
from mangak.gui.widgets.toast import ToastManager


# ──────────────────────────────────────────────
#  Table style constants
# ──────────────────────────────────────────────

_TABLE_STYLE = f"""
    QTableWidget {{
        background: {Colors.BG_SURFACE};
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid {Colors.BORDER};
        border-radius: 8px;
        gridline-color: {Colors.BORDER};
        font-size: 13px;
        selection-background-color: {Colors.ACCENT_PRIMARY}33;
        selection-color: {Colors.TEXT_PRIMARY};
    }}
    QTableWidget::item {{
        padding: 6px 10px;
        border-bottom: 1px solid {Colors.BORDER}44;
    }}
    QTableWidget::item:selected {{
        background: {Colors.ACCENT_PRIMARY}33;
    }}
    QHeaderView::section {{
        background: {Colors.BG_ELEVATED};
        color: {Colors.TEXT_SECONDARY};
        border: none;
        border-bottom: 1px solid {Colors.BORDER};
        padding: 8px 10px;
        font-size: 12px;
        font-weight: bold;
    }}
    QScrollBar:vertical {{
        background: {Colors.BG_SURFACE};
        width: 8px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: {Colors.BORDER};
        border-radius: 4px;
    }}
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0;
    }}
"""


# ──────────────────────────────────────────────
#  History Tab
# ──────────────────────────────────────────────


class HistoryTab(QWidget):
    """'📜 History' tab: searchable download history with stats and pagination."""

    PAGE_SIZE = 25

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._db = DownloadDB()
        self._current_page: int = 0
        self._total_records: int = 0
        self._total_pages: int = 0
        self._current_search: str = ""
        self._setup_ui()
        self._refresh()

    # ── UI Setup ───────────────────────────────

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"""
            HistoryTab {{
                background: {Colors.BG_BASE};
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # ── Title ──
        title = QLabel("📜  Download History")
        title_font = QFont("Segoe UI", 18, QFont.Weight.Bold)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        root.addWidget(title)

        # ── Search bar ──
        search_panel = GlassPanel()
        search_layout = QHBoxLayout(search_panel)
        search_layout.setContentsMargins(16, 10, 16, 10)
        search_layout.setSpacing(12)

        search_layout.addWidget(QLabel("🔍"))

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search downloads by manga name, slug, or chapter…")
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {Colors.BG_SURFACE};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border-color: {Colors.ACCENT_PRIMARY};
            }}
        """)
        self._search_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self._search_input, 1)

        self._search_btn = QPushButton("Search")
        self._search_btn.setFixedHeight(36)
        self._search_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ACCENT_PRIMARY};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 0 20px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {Colors.ACCENT_PRIMARY}CC;
            }}
            QPushButton:pressed {{
                background: {Colors.ACCENT_PRIMARY}AA;
            }}
        """)
        self._search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(self._search_btn)

        self._clear_search_btn = QPushButton("×")
        self._clear_search_btn.setFixedSize(36, 36)
        self._clear_search_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        self._clear_search_btn.clicked.connect(self._on_clear_search)
        search_layout.addWidget(self._clear_search_btn)

        root.addWidget(search_panel)

        # ── Stats header ──
        stats_panel = GlassPanel()
        stats_layout = QHBoxLayout(stats_panel)
        stats_layout.setContentsMargins(20, 10, 20, 10)
        stats_layout.setSpacing(24)

        self._total_label = QLabel("📊 Total: — downloads")
        self._total_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px;")
        stats_layout.addWidget(self._total_label)

        self._unique_label = QLabel("|  — unique manga")
        self._unique_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 13px;")
        stats_layout.addWidget(self._unique_label)

        stats_layout.addStretch()
        root.addWidget(stats_panel)

        # ── Table ──
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            "#", "Manga", "Chapter", "Format", "Size", "Date"
        ])
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(_TABLE_STYLE)
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self._table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table.setColumnWidth(0, 50)  # #
        self._table.setColumnWidth(1, 200)  # Manga
        self._table.setColumnWidth(2, 150)  # Chapter
        self._table.setColumnWidth(3, 80)   # Format
        self._table.setColumnWidth(4, 100)  # Size
        # Date stretches

        root.addWidget(self._table, 1)

        # ── Bottom bar ──
        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        self._clear_all_btn = QPushButton("🗑 Clear All History")
        self._clear_all_btn.setFixedHeight(34)
        self._clear_all_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Colors.DANGER};
                border: 1px solid {Colors.DANGER}66;
                border-radius: 8px;
                padding: 0 16px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {Colors.DANGER}22;
            }}
        """)
        self._clear_all_btn.clicked.connect(self._on_clear_all)
        bottom.addWidget(self._clear_all_btn)

        bottom.addStretch()

        self._page_info = QLabel("Page 1 of 1")
        self._page_info.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 13px;")
        bottom.addWidget(self._page_info)

        self._prev_btn = QPushButton("← Prev")
        self._prev_btn.setFixedHeight(34)
        self._prev_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_SURFACE};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 0 14px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {Colors.BG_ELEVATED};
            }}
            QPushButton:disabled {{
                color: {Colors.TEXT_SECONDARY};
                border-color: {Colors.BORDER}66;
            }}
        """)
        self._prev_btn.clicked.connect(self._on_prev_page)
        bottom.addWidget(self._prev_btn)

        self._next_btn = QPushButton("Next →")
        self._next_btn.setFixedHeight(34)
        self._next_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_SURFACE};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 0 14px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {Colors.BG_ELEVATED};
            }}
            QPushButton:disabled {{
                color: {Colors.TEXT_SECONDARY};
                border-color: {Colors.BORDER}66;
            }}
        """)
        self._next_btn.clicked.connect(self._on_next_page)
        bottom.addWidget(self._next_btn)

        # Refresh button
        self._refresh_btn = QPushButton("🔄")
        self._refresh_btn.setFixedSize(34, 34)
        self._refresh_btn.setToolTip("Refresh history")
        self._refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background: {Colors.BG_ELEVATED};
            }}
        """)
        self._refresh_btn.clicked.connect(self._refresh)
        bottom.addWidget(self._refresh_btn)

        root.addLayout(bottom)

        # ── Auto-refresh timer (subtle, not intrusive) ──
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5000)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start()

    # ── Data loading ───────────────────────────

    def _refresh(self) -> None:
        """Load stats and current page data."""
        try:
            stats = self._db.get_stats()
        except MangaKError:
            return

        self._total_records = stats.get("total_downloads", 0)
        unique = stats.get("unique_manga", 0)
        self._total_pages = max(1, (self._total_records + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

        self._total_label.setText(f"📊 Total: {self._total_records} downloads")
        self._unique_label.setText(f"|  {unique} unique manga")

        # Enforce page bounds
        if self._current_page >= self._total_pages:
            self._current_page = self._total_pages - 1
        if self._current_page < 0:
            self._current_page = 0

        self._load_page()

    def _load_page(self) -> None:
        """Load records for the current page into the table."""
        offset = self._current_page * self.PAGE_SIZE

        try:
            if self._current_search:
                records = self._db.search_history(
                    self._current_search,
                    limit=self.PAGE_SIZE,
                    offset=offset,
                )
            else:
                records = self._db.get_history(
                    limit=self.PAGE_SIZE,
                    offset=offset,
                )
        except MangaKError as exc:
            ToastManager.show_toast_cls("Error", str(exc), "error")
            return

        self._table.setRowCount(len(records))

        for row, rec in enumerate(records):
            # # (id)
            id_item = QTableWidgetItem(str(rec.get("id", "")))
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            id_item.setForeground(QColor(Colors.TEXT_SECONDARY))
            self._table.setItem(row, 0, id_item)

            # Manga
            manga_item = QTableWidgetItem(rec.get("manga_name", ""))
            manga_item.setForeground(QColor(Colors.TEXT_PRIMARY))
            self._table.setItem(row, 1, manga_item)

            # Chapter
            ch_item = QTableWidgetItem(rec.get("chapter_name", ""))
            ch_item.setForeground(QColor(Colors.TEXT_PRIMARY))
            self._table.setItem(row, 2, ch_item)

            # Format
            fmt = rec.get("format", "")
            fmt_item = QTableWidgetItem(fmt.upper())
            fmt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if fmt in ("cbz", "zip"):
                fmt_item.setForeground(QColor(Colors.ACCENT_PRIMARY))
            elif fmt == "pdf":
                fmt_item.setForeground(QColor(Colors.DANGER))
            else:
                fmt_item.setForeground(QColor(Colors.TEXT_SECONDARY))
            self._table.setItem(row, 3, fmt_item)

            # Size
            kb = rec.get("file_size_kb")
            if kb:
                if kb >= 1024:
                    size_str = f"{kb / 1024:.1f} MB"
                else:
                    size_str = f"{kb} KB"
            else:
                size_str = "—"
            size_item = QTableWidgetItem(size_str)
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            size_item.setForeground(QColor(Colors.TEXT_SECONDARY))
            self._table.setItem(row, 4, size_item)

            # Date
            date_raw = rec.get("downloaded_at", "")
            date_str = str(date_raw)[:19] if date_raw else "—"
            date_item = QTableWidgetItem(date_str)
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            date_item.setForeground(QColor(Colors.TEXT_SECONDARY))
            self._table.setItem(row, 5, date_item)

        self._update_nav_buttons()

    def _update_nav_buttons(self) -> None:
        self._prev_btn.setEnabled(self._current_page > 0)
        self._next_btn.setEnabled(self._current_page < self._total_pages - 1)
        self._page_info.setText(
            f"Page {self._current_page + 1} of {self._total_pages}"
        )

    # ── Slots ──────────────────────────────────

    def _on_search(self) -> None:
        query = self._search_input.text().strip()
        self._current_search = query
        self._current_page = 0
        self._refresh()

    def _on_clear_search(self) -> None:
        self._search_input.clear()
        self._current_search = ""
        self._current_page = 0
        self._refresh()

    def _on_prev_page(self) -> None:
        if self._current_page > 0:
            self._current_page -= 1
            self._load_page()

    def _on_next_page(self) -> None:
        if self._current_page < self._total_pages - 1:
            self._current_page += 1
            self._load_page()

    def _on_clear_all(self) -> None:
        """Clear all history with confirmation dialog."""
        from PyQt6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "Clear All History",
            "Are you sure you want to delete all download history?\n\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                count = self._db.clear_history()
                ToastManager.show_toast_cls(
                    "History Cleared",
                    f"{count} record(s) deleted.",
                    "info",
                )
                self._current_page = 0
                self._refresh()
            except MangaKError as exc:
                ToastManager.show_toast_cls("Error", str(exc), "error")

    # ── Visibility handling ──

    def showEvent(self, event) -> None:
        """Refresh when tab becomes visible."""
        super().showEvent(event)
        self._refresh()
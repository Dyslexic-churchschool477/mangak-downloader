"""MangaK Downloader — MainWindow with 5-tab QTabWidget, theme engine, and status bar."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut, QAction
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QSizePolicy,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mangak.core.config import Settings
from mangak.core.models import DownloadTask
from mangak.gui.themes import ThemeEngine
from mangak.gui.widgets.toast import ToastManager
from mangak.gui.tabs.manga_url import MangaByUrlTab
from mangak.gui.tabs.manga_name import MangaByNameTab
from mangak.gui.tabs.download import DownloadTab
from mangak.gui.tabs.history import HistoryTab
from mangak.gui.tabs.settings import SettingsTab


# ====================================================================
#  Main application window
# ====================================================================

class MainWindow(QMainWindow):
    """5-tab manga downloader GUI with dark theme and status bar."""

    MIN_W = 1000
    MIN_H = 700
    DEFAULT_W = 1280
    DEFAULT_H = 800

    TAB_NAMES = [
        ("🔗", "URL"),
        ("🔍", "Search"),
        ("⬇️", "Download"),
        ("📜", "History"),
        ("⚙️", "Settings"),
    ]

    def __init__(
        self,
        settings: Optional[Settings] = None,
        theme_engine: Optional[ThemeEngine] = None,
    ) -> None:
        super().__init__()
        self._settings = settings or Settings()
        self._theme_engine = theme_engine or ThemeEngine()

        # Window properties
        self.setObjectName("MainWindow")
        self.setWindowTitle("MangaK Downloader")
        self.setMinimumSize(self.MIN_W, self.MIN_H)
        self.resize(self.DEFAULT_W, self.DEFAULT_H)

        # Toast overlay manager
        self.toast_manager = ToastManager(self)

        # ── Central widget ──────────────────────────────────────────────
        central = QWidget(self)
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Tab widget ──────────────────────────────────────────────────
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("MainTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(False)
        self.tabs.setTabBarAutoHide(False)

        # Create tab instances
        self.url_tab = MangaByUrlTab(self)
        self.search_tab = MangaByNameTab(self)
        self.download_tab = DownloadTab(self)
        self.history_tab = HistoryTab(self)
        self.settings_tab = SettingsTab(self)

        # Add tabs
        self.tabs.addTab(self.url_tab, "  🔗  URL  ")
        self.tabs.addTab(self.search_tab, "  🔍  Search  ")
        self.tabs.addTab(self.download_tab, "  ⬇️  Download  ")
        self.tabs.addTab(self.history_tab, "  📜  History  ")
        self.tabs.addTab(self.settings_tab, "  ⚙️  Settings  ")

        layout.addWidget(self.tabs)

        # ── Status bar ──────────────────────────────────────────────────
        status = QStatusBar(self)
        status.setObjectName("AppStatusBar")
        status.showMessage("Ready")
        self.setStatusBar(status)

        # ── Theme ───────────────────────────────────────────────────────
        self._apply_theme()

        # ── Geometry restore ────────────────────────────────────────────
        self._restore_geometry()

        # ── Connect signals ─────────────────────────────────────────────
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Connect search tab → navigate to URL tab on manga click
        self.search_tab.manga_selected.connect(self._on_search_manga_clicked)

        # Connect URL tab download signal → switch to download tab
        self.url_tab.download_started.connect(self._on_download_started)

    # ── Public helpers ─────────────────────────────────────────────────

    def switch_tab(self, index: int) -> None:
        """Switch to the tab at *index*."""
        if 0 <= index < self.tabs.count():
            self.tabs.setCurrentIndex(index)

    def show_status(self, message: str, timeout: int = 5000) -> None:
        """Display a temporary message in the status bar."""
        sb = self.statusBar()
        sb.showMessage(message, timeout)

    def apply_theme(self) -> None:
        """Re-apply the current theme."""
        self._apply_theme()

    # ── Internal slots ─────────────────────────────────────────────────

    def _on_tab_changed(self, index: int) -> None:
        """Called when the active tab changes."""
        self.show_status(f"Tab: {self.TAB_NAMES[index][1]}")

    def _on_search_manga_clicked(self, slug: str) -> None:
        """Navigate to URL tab and load the selected manga slug."""
        self.url_tab.load_slug(slug)
        self.switch_tab(0)

    def _on_download_started(self, task: DownloadTask) -> None:
        """Route download task to download tab and switch to it."""
        self.download_tab.add_task(task)
        self.switch_tab(2)

    # ── Theme ──────────────────────────────────────────────────────────

    def _apply_theme(self) -> None:
        """Load the dark QSS file and apply it via the theme engine."""
        gui_dir = Path(__file__).resolve().parent
        resources_dir = gui_dir / "resources"

        json_path = str(resources_dir / "dark.json")
        qss_path = str(resources_dir / "dark.qss")

        try:
            self._theme_engine.load_json(json_path)
            qss = self._theme_engine.resolve_file(qss_path)
            self._theme_engine.apply(qss)
        except Exception:
            pass

    # ── Geometry persistence ───────────────────────────────────────────

    def _restore_geometry(self) -> None:
        """Restore saved window geometry from settings, if available."""
        geom = self._settings.get("window_geometry")
        if geom is not None and isinstance(geom, (list, str)):
            try:
                from PyQt6.QtCore import QByteArray
                if isinstance(geom, list):
                    data = QByteArray(bytes(geom))
                else:
                    data = QByteArray(geom.encode("latin-1"))
                self.restoreGeometry(data)
            except Exception:
                pass

    def closeEvent(self, event) -> None:
        """Save window geometry before closing."""
        try:
            geom = self.saveGeometry()
            self._settings.set("window_geometry", list(geom))
        except Exception:
            pass
        super().closeEvent(event)


# ====================================================================
#  Launcher convenience
# ====================================================================


def run_gui(
    settings: Optional[Settings] = None,
    theme_engine: Optional[ThemeEngine] = None,
) -> None:
    """Create and show the main window inside a QApplication event loop."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app.setApplicationName("MangaK Downloader")

    window = MainWindow(settings=settings, theme_engine=theme_engine)
    window.show()
    sys.exit(app.exec())


def main() -> None:
    """Entry point for the mangak-gui script."""
    run_gui()

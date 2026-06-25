"""MangaK Downloader — Modern PyQt6 GUI."""

from mangak.gui.themes import ThemeEngine
from mangak.gui.app import MainWindow, run_gui, main
from mangak.gui.tabs.manga_url import MangaByUrlTab
from mangak.gui.tabs.manga_name import MangaByNameTab
from mangak.gui.tabs.download import DownloadTab
from mangak.gui.tabs.history import HistoryTab
from mangak.gui.tabs.settings import SettingsTab

__all__ = [
    "ThemeEngine",
    "MainWindow",
    "run_gui",
    "main",
    "MangaByUrlTab",
    "MangaByNameTab",
    "DownloadTab",
    "HistoryTab",
    "SettingsTab",
]

"""Tab widgets for the MangaK Downloader GUI."""

from mangak.gui.tabs.manga_url import MangaByUrlTab
from mangak.gui.tabs.manga_name import MangaByNameTab
from mangak.gui.tabs.download import DownloadTab
from mangak.gui.tabs.history import HistoryTab
from mangak.gui.tabs.settings import SettingsTab

__all__ = [
    "MangaByUrlTab",
    "MangaByNameTab",
    "DownloadTab",
    "HistoryTab",
    "SettingsTab",
]

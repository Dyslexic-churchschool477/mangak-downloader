"""
MangaK Core Library — shared between CLI and GUI interfaces.

All public classes are exported here for convenient imports:
    from mangak.core import Manga, MangaKClient, Settings, ...
"""

from mangak.core.exceptions import (
    MangaKError,
    MangaNotFoundError,
    ChapterNotFoundError,
    DownloadError,
    ExportError,
    ConfigError,
)

from mangak.core.models import (
    Manga,
    SearchResult,
    ChapterListItem,
    Chapter,
    Tag,
    Author,
    AltName,
    MangaStats,
    ChapterRef,
    DownloadTask,
    DownloadStatus,
)

from mangak.core.client import MangaKClient

from mangak.core.config import Settings

from mangak.core.downloader import DownloadQueue

from mangak.core.export import (
    export_folder,
    export_cbz,
    export_zip,
    export_pdf,
)

from mangak.core.db import DownloadDB

from mangak.core.themes import Colors

__all__ = [
    # Exceptions
    "MangaKError",
    "MangaNotFoundError",
    "ChapterNotFoundError",
    "DownloadError",
    "ExportError",
    "ConfigError",
    # Models
    "Manga",
    "SearchResult",
    "ChapterListItem",
    "Chapter",
    "Tag",
    "Author",
    "AltName",
    "MangaStats",
    "ChapterRef",
    "DownloadTask",
    "DownloadStatus",
    # Client
    "MangaKClient",
    # Config
    "Settings",
    # Downloader
    "DownloadQueue",
    # Export
    "export_folder",
    "export_cbz",
    "export_zip",
    "export_pdf",
    # DB
    "DownloadDB",
    # Themes
    "Colors",
]

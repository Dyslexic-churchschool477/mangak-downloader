"""
Custom exception hierarchy for the MangaK Downloader.

All custom exceptions inherit from MangaKError, which itself inherits from Exception.
"""


class MangaKError(Exception):
    """Base exception for all MangaK Downloader errors."""


class MangaNotFoundError(MangaKError):
    """Raised when a manga slug does not resolve to a valid manga page."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(f"Manga not found: '{slug}'")


class ChapterNotFoundError(MangaKError):
    """Raised when a chapter slug does not resolve to a valid chapter page."""

    def __init__(self, manga_slug: str, chapter_slug: str) -> None:
        self.manga_slug = manga_slug
        self.chapter_slug = chapter_slug
        super().__init__(f"Chapter not found: '{manga_slug}/{chapter_slug}'")


class DownloadError(MangaKError):
    """Raised when an image or chapter download fails."""


class ExportError(MangaKError):
    """Raised when exporting downloaded images to a format fails."""


class ConfigError(MangaKError):
    """Raised when the settings file is missing, corrupt, or fails to validate."""

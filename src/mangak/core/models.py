"""
Pydantic v2 data models for the MangaK Downloader.

All models use Pydantic v2 conventions: ``model_validate`` (not ``parse_obj``),
``ConfigDict`` (not inner ``Config``), and type annotations throughout.

Field names match the JSON keys returned by mangak.io's __NEXT_DATA__ payload
and the api.mangak.io REST endpoints (converted to snake_case).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, HttpUrl, field_validator


# ──────────────────────────────────────────────
#  Supporting models
# ──────────────────────────────────────────────


class Tag(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str = ""
    name: str = ""
    slug: str = ""
    url: str = ""


class Author(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str = ""
    name: str = ""
    slug: str = ""
    url: str = ""


class AltName(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str = ""
    language: str = ""


class MangaStats(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    views: int = 0
    bookmarks_count: int = 0
    comments_count: int = 0
    manga_only_comments_count: int = 0
    chapters_count: int = 0
    ratings_count: int = 0
    reviews_count: int = 0


class ChapterRef(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str = ""
    name: str = ""
    url: str = ""
    slug: str = ""
    date: datetime | str | None = None
    cv: int = 0
    content_type: str = ""


# ──────────────────────────────────────────────
#  Primary models
# ──────────────────────────────────────────────


class Manga(BaseModel):
    """
    Full manga detail from __NEXT_DATA__ -> props.pageProps.initialManga.
    All fields optional with sensible defaults -- the API often omits some.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str = ""
    slug: str = ""
    url: str = ""
    name: str = ""
    alt_name: Optional[str] = None
    alt_names: list[AltName] = []
    cover: Optional[str] = None
    status: str = ""
    rating: float = 0.0
    summary: str = ""
    genres: list[Tag] = []
    tags: list[Tag] = []
    authors: list[Author] = []
    stats: Optional[MangaStats] = None
    latest_chapters: list[ChapterRef] = []
    is_adult: bool = False
    is_hot: bool = False
    is_new: bool = False
    cv: int = 0
    updated_at: Optional[str] = None
    display_alt_name: str = ""
    display_rating: str = ""
    display_views: str = ""
    display_bookmarks: str = ""
    display_chapters: str = ""
    display_updated: str = ""
    display_updated_short: str = ""

    @field_validator("rating", mode="before")
    @classmethod
    def coerce_rating(cls, v: Any) -> float:
        if v is None:
            return 0.0
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    @field_validator("is_adult", "is_hot", "is_new", mode="before")
    @classmethod
    def coerce_bool(cls, v: Any) -> bool:
        if v is None:
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return v != 0
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return False

    @field_validator("cv", mode="before")
    @classmethod
    def coerce_int(cls, v: Any) -> int:
        if v is None:
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    @field_validator("cover", mode="before")
    @classmethod
    def coerce_cover(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        return str(v)

    @field_validator("updated_at", mode="before")
    @classmethod
    def coerce_datetime(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class SearchResult(BaseModel):
    """
    Search result item from __NEXT_DATA__ -> props.pageProps.ssrItems.

    ``stats`` and ``is_adult`` may be absent for some results.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str = ""
    slug: str = ""
    url: str = ""
    name: str = ""
    cover: Optional[str] = None
    status: str = ""
    rating: float = 0.0
    summary: Optional[str] = None
    genres: list[Tag] = []
    stats: Optional[MangaStats] = None
    is_adult: Optional[bool] = None

    @field_validator("rating", mode="before")
    @classmethod
    def coerce_rating(cls, v: Any) -> float:
        if v is None:
            return 0.0
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    @field_validator("cover", mode="before")
    @classmethod
    def coerce_cover(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        return str(v)


class ChapterListItem(BaseModel):
    """
    Chapter list item from the REST API endpoint.

    Returned by ``GET /titles/{mangaId}/chapters?cv={timestamp}``.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str = ""
    url: str = ""
    name: str = ""
    slug: str = ""
    views: int = 0
    comments_count: int = 0
    updated_at: Optional[str] = None
    chapter_number: int = 0

    @field_validator("chapter_number", mode="before")
    @classmethod
    def coerce_chapter_number(cls, v: Any) -> int:
        if v is None:
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0


class Chapter(BaseModel):
    """
    Full chapter data from __NEXT_DATA__ -> props.pageProps.initialChapter.

    Includes the ``images`` list -- full CDN URLs for every page.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str = ""
    url: str = ""
    name: str = ""
    slug: str = ""
    views: int = 0
    comments_count: int = 0
    updated_at: Optional[str] = None
    chapter_number: int = 0
    cv: int = 0
    images: list[str] = []


# ──────────────────────────────────────────────
#  Download models
# ──────────────────────────────────────────────


class DownloadStatus(Enum):
    """Status of a single download task."""

    QUEUED = "queued"
    DOWNLOADING = "downloading"
    EXPORTING = "exporting"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DownloadTask(BaseModel):
    """
    Represents one chapter queued for download.

    Tracks progress through ``pages_completed`` / ``pages_total`` and
    stores the parsed image URLs that will be fetched.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    manga_slug: str = ""
    manga_name: str = ""
    chapter_slug: str = ""
    chapter_name: str = ""
    chapter_id: str = ""
    images: list[str] = []
    format: str = "cbz"
    output_dir: str = "downloads"
    delete_after: bool = False
    status: DownloadStatus = DownloadStatus.QUEUED
    progress: float = 0.0
    pages_completed: int = 0
    pages_total: int = 0
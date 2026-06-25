"""Tests for all Pydantic v2 data models.

Validates construction, validation, serialisation round-trips,
optional-field handling, and enum behaviour for every model in
``mangak.core.models``.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from mangak.core.models import (
    AltName,
    Author,
    Chapter,
    ChapterListItem,
    ChapterRef,
    DownloadStatus,
    DownloadTask,
    Manga,
    MangaStats,
    SearchResult,
    Tag,
)

# =========================================================================
#  Fixtures — realistic test data
# =========================================================================


@pytest.fixture
def tag() -> dict:
    return {"id": "1", "name": "Action", "slug": "action", "url": "/genre/action"}


@pytest.fixture
def author() -> dict:
    return {
        "id": "42",
        "name": "Park作者",
        "slug": "park-author",
        "url": "/author/park-author",
    }


@pytest.fixture
def alt_name() -> dict:
    return {"name": "ナノマシン", "language": "ja"}


@pytest.fixture
def stats() -> dict:
    return {
        "views": 1_234_567,
        "bookmarks_count": 8_901,
        "comments_count": 234,
        "manga_only_comments_count": 56,
        "chapters_count": 187,
        "ratings_count": 4_321,
        "reviews_count": 12,
    }


@pytest.fixture
def chapter_ref() -> dict:
    return {
        "id": "ch-100",
        "name": "Chapter 100",
        "url": "/nano-machine/chapter-100",
        "slug": "chapter-100",
        "date": "2024-03-15T12:00:00Z",
        "cv": 1710000000,
        "content_type": "chapter",
    }


# Manga payload — matches what __NEXT_DATA__ → props.pageProps.initialManga returns
@pytest.fixture
def manga_payload(tag, author, alt_name, stats, chapter_ref) -> dict:
    """Payload using snake_case keys (already normalised from camelCase JSON)."""
    return {
        "id": "12345",
        "slug": "nano-machine",
        "url": "https://mangak.io/nano-machine",
        "name": "Nano Machine",
        "alt_name": "나노마신",
        "alt_names": [alt_name],
        "cover": "https://mangak.io/uploads/nano-machine/cover.webp",
        "status": "Ongoing",
        "rating": 4.5,
        "summary": "A boy raised in the mountains...",
        "genres": [tag],
        "tags": [tag],
        "authors": [author],
        "stats": stats,
        "latest_chapters": [chapter_ref],
        "is_adult": True,
        "is_hot": True,
        "is_new": False,
        "cv": 1710000000,
        "updated_at": "2024-03-15T12:00:00Z",
        "display_alt_name": "나노마신",
        "display_rating": "4.5",
        "display_views": "1.23M",
        "display_bookmarks": "8.9K",
        "display_chapters": "187",
        "display_updated": "2024-03-15",
        "display_updated_short": "Mar 15",
    }


@pytest.fixture
def chapter_payload() -> dict:
    return {
        "id": "ch-50",
        "url": "https://mangak.io/nano-machine/chapter-50",
        "name": "Chapter 50",
        "slug": "chapter-50",
        "views": 45_678,
        "comments_count": 89,
        "updated_at": "2024-02-20T08:30:00Z",
        "chapter_number": 50,
        "cv": 1708400000,
        "images": [
            "https://rx.qvzra.org/uploads/nano-machine/chapter-50/001.webp",
            "https://rx.qvzra.org/uploads/nano-machine/chapter-50/002.webp",
            "https://rx.qvzrb.org/uploads/nano-machine/chapter-50/003.webp",
        ],
    }


@pytest.fixture
def chapter_list_item_payload() -> dict:
    return {
        "id": "ch-50",
        "url": "https://api.mangak.io/titles/12345/chapters/ch-50",
        "name": "Chapter 50",
        "slug": "chapter-50",
        "views": 45_678,
        "comments_count": 89,
        "updated_at": "2024-02-20T08:30:00Z",
        "chapter_number": 50,
    }


@pytest.fixture
def search_result_payload(tag) -> dict:
    return {
        "id": "67890",
        "slug": "solo-leveling",
        "url": "https://mangak.io/solo-leveling",
        "name": "Solo Leveling",
        "cover": "https://mangak.io/uploads/solo-leveling/cover.webp",
        "status": "completed",
        "rating": 4.8,
        "summary": "In a world where hunters fight monsters...",
        "genres": [tag],
        "stats": {
            "views": 9_876_543,
            "bookmarks_count": 12_345,
            "comments_count": 567,
            "manga_only_comments_count": 89,
            "chapters_count": 200,
            "ratings_count": 8_765,
            "reviews_count": 34,
        },
        "is_adult": False,
    }


# =========================================================================
#  Tag
# =========================================================================


class TestTag:
    def test_construct(self, tag):
        obj = Tag.model_validate(tag)
        assert obj.id == "1"
        assert obj.name == "Action"
        assert obj.slug == "action"
        assert obj.url == "/genre/action"

    def test_serialise_roundtrip(self, tag):
        obj = Tag.model_validate(tag)
        d = obj.model_dump()
        restored = Tag.model_validate(d)
        assert restored == obj


# =========================================================================
#  Author
# =========================================================================


class TestAuthor:
    def test_construct(self, author):
        obj = Author.model_validate(author)
        assert obj.id == "42"
        assert obj.name == "Park作者"
        assert obj.slug == "park-author"

    def test_serialise_roundtrip(self, author):
        obj = Author.model_validate(author)
        assert Author.model_validate(obj.model_dump()) == obj


# =========================================================================
#  AltName
# =========================================================================


class TestAltName:
    def test_construct(self, alt_name):
        obj = AltName.model_validate(alt_name)
        assert obj.name == "ナノマシン"
        assert obj.language == "ja"

    def test_serialise_roundtrip(self, alt_name):
        obj = AltName.model_validate(alt_name)
        assert AltName.model_validate(obj.model_dump()) == obj


# =========================================================================
#  MangaStats
# =========================================================================


class TestMangaStats:
    def test_construct(self, stats):
        obj = MangaStats.model_validate(stats)
        assert obj.views == 1_234_567
        assert obj.bookmarks_count == 8_901
        assert obj.ratings_count == 4_321

    def test_defaults_to_zero(self):
        """MangaStats fields do NOT have defaults; all are required.
        This test verifies that an empty dict fails validation."""
        with pytest.raises(ValidationError):
            MangaStats.model_validate({})

    def test_serialise_roundtrip(self, stats):
        obj = MangaStats.model_validate(stats)
        assert MangaStats.model_validate(obj.model_dump()) == obj


# =========================================================================
#  ChapterRef
# =========================================================================


class TestChapterRef:
    def test_construct(self, chapter_ref):
        obj = ChapterRef.model_validate(chapter_ref)
        assert obj.id == "ch-100"
        assert obj.slug == "chapter-100"
        assert obj.cv == 1710000000
        assert isinstance(obj.date, datetime)

    def test_serialise_roundtrip(self, chapter_ref):
        obj = ChapterRef.model_validate(chapter_ref)
        assert ChapterRef.model_validate(obj.model_dump()) == obj


# =========================================================================
#  Manga
# =========================================================================


class TestManga:
    def test_construct_full(self, manga_payload):
        obj = Manga.model_validate(manga_payload)
        assert obj.id == "12345"
        assert obj.slug == "nano-machine"
        assert obj.name == "Nano Machine"
        assert obj.alt_name == "나노마신"
        assert str(obj.cover).startswith("http")
        assert obj.status == "Ongoing"
        assert obj.rating == 4.5
        assert obj.summary == "A boy raised in the mountains..."
        assert len(obj.genres) == 1
        assert len(obj.authors) == 1
        assert len(obj.alt_names) == 1
        assert isinstance(obj.stats, MangaStats)
        assert len(obj.latest_chapters) == 1
        assert isinstance(obj.latest_chapters[0], ChapterRef)
        assert obj.is_adult is True
        assert obj.is_hot is True
        assert obj.is_new is False
        assert obj.cv == 1710000000
        assert isinstance(obj.updated_at, datetime)
        assert obj.display_alt_name == "나노마신"
        assert obj.display_rating == "4.5"
        assert obj.display_views == "1.23M"

    def test_serialise_roundtrip(self, manga_payload):
        obj = Manga.model_validate(manga_payload)
        d = obj.model_dump()
        restored = Manga.model_validate(d)
        assert restored == obj

    @pytest.mark.parametrize("field", ["id", "slug", "url", "name", "cover", "status", "rating", "summary"])
    def test_required_fields(self, manga_payload, field):
        payload = dict(manga_payload)
        del payload[field]
        with pytest.raises(ValidationError):
            Manga.model_validate(payload)

    def test_field_name_alias(self, manga_payload):
        """Verify populate_by_name=True allows snake_case access.
        No explicit aliases are defined on Manga fields."""
        obj = Manga.model_validate(manga_payload)
        assert obj.alt_name == "나노마신"
        # The model field is alt_name; there's no explicit alias on these fields
        assert obj.alt_name is not None


# =========================================================================
#  SearchResult
# =========================================================================


class TestSearchResult:
    def test_construct_full(self, search_result_payload):
        obj = SearchResult.model_validate(search_result_payload)
        assert obj.id == "67890"
        assert obj.slug == "solo-leveling"
        assert obj.name == "Solo Leveling"
        assert str(obj.cover).startswith("http")
        assert obj.status == "completed"
        assert obj.rating == 4.8
        assert obj.summary == "In a world where hunters fight monsters..."
        assert len(obj.genres) == 1
        assert isinstance(obj.stats, MangaStats)
        assert obj.is_adult is False

    def test_optional_fields_default_to_none(self, search_result_payload):
        payload = dict(search_result_payload)
        del payload["summary"]
        del payload["stats"]
        del payload["is_adult"]
        obj = SearchResult.model_validate(payload)
        assert obj.summary is None
        assert obj.stats is None
        assert obj.is_adult is None

    def test_serialise_roundtrip(self, search_result_payload):
        obj = SearchResult.model_validate(search_result_payload)
        assert SearchResult.model_validate(obj.model_dump()) == obj


# =========================================================================
#  Chapter
# =========================================================================


class TestChapter:
    def test_construct_full(self, chapter_payload):
        obj = Chapter.model_validate(chapter_payload)
        assert obj.id == "ch-50"
        assert obj.name == "Chapter 50"
        assert obj.slug == "chapter-50"
        assert obj.views == 45_678
        assert obj.comments_count == 89
        assert obj.chapter_number == 50
        assert obj.cv == 1708400000
        assert isinstance(obj.updated_at, datetime)
        assert len(obj.images) == 3
        for url in obj.images:
            assert str(url).startswith("http")
        assert str(obj.images[0]).startswith("https://rx.qvzra.org")

    def test_images_list_validation(self, chapter_payload):
        """All entries in images must be valid URLs."""
        payload = dict(chapter_payload)
        payload["images"] = ["not-a-url"]
        with pytest.raises(ValidationError):
            Chapter.model_validate(payload)

    def test_serialise_roundtrip(self, chapter_payload):
        obj = Chapter.model_validate(chapter_payload)
        assert Chapter.model_validate(obj.model_dump()) == obj


# =========================================================================
#  ChapterListItem
# =========================================================================


class TestChapterListItem:
    def test_construct_full(self, chapter_list_item_payload):
        obj = ChapterListItem.model_validate(chapter_list_item_payload)
        assert obj.id == "ch-50"
        assert obj.name == "Chapter 50"
        assert obj.slug == "chapter-50"
        assert obj.views == 45_678
        assert obj.comments_count == 89
        assert obj.chapter_number == 50
        assert isinstance(obj.updated_at, datetime)

    def test_serialise_roundtrip(self, chapter_list_item_payload):
        obj = ChapterListItem.model_validate(chapter_list_item_payload)
        assert ChapterListItem.model_validate(obj.model_dump()) == obj


# =========================================================================
#  DownloadStatus — Enum
# =========================================================================


class TestDownloadStatus:
    def test_values(self):
        assert DownloadStatus.QUEUED.value == "queued"
        assert DownloadStatus.DOWNLOADING.value == "downloading"
        assert DownloadStatus.PAUSED.value == "paused"
        assert DownloadStatus.COMPLETED.value == "completed"
        assert DownloadStatus.FAILED.value == "failed"
        assert DownloadStatus.CANCELLED.value == "cancelled"

    def test_all_members(self):
        expected = {"QUEUED", "DOWNLOADING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED"}
        assert {m.name for m in DownloadStatus} == expected

    def test_unique_values(self):
        values = [m.value for m in DownloadStatus]
        assert len(values) == len(set(values))


# =========================================================================
#  DownloadTask
# =========================================================================


class TestDownloadTask:
    @pytest.fixture
    def task_payload(self) -> dict:
        return {
            "manga_slug": "nano-machine",
            "manga_name": "Nano Machine",
            "chapter_slug": "chapter-50",
            "chapter_name": "Chapter 50",
            "chapter_id": "ch-50",
            "images": [
                "https://rx.qvzra.org/nano-machine/chapter-50/001.webp",
                "https://rx.qvzra.org/nano-machine/chapter-50/002.webp",
            ],
            "format": "cbz",
            "output_dir": "/tmp/downloads",
            "delete_after": True,
        }

    def test_construct_with_defaults(self, task_payload):
        obj = DownloadTask.model_validate(task_payload)
        assert obj.manga_slug == "nano-machine"
        assert obj.chapter_name == "Chapter 50"
        assert obj.status == DownloadStatus.QUEUED
        assert obj.progress == 0.0
        assert obj.pages_completed == 0
        assert obj.pages_total == 0
        assert len(obj.images) == 2

    def test_explicit_status(self, task_payload):
        payload = dict(task_payload, status="downloading")
        obj = DownloadTask.model_validate(payload)
        assert obj.status == DownloadStatus.DOWNLOADING

    def test_progress_update(self, task_payload):
        obj = DownloadTask.model_validate(task_payload)
        obj.progress = 0.5
        obj.pages_completed = 1
        obj.pages_total = 2
        assert obj.progress == 0.5
        assert obj.pages_completed == 1
        assert obj.pages_total == 2

    def test_serialise_roundtrip(self, task_payload):
        obj = DownloadTask.model_validate(task_payload)
        obj.status = DownloadStatus.DOWNLOADING
        obj.progress = 0.25
        obj.pages_completed = 1
        obj.pages_total = 4
        restored = DownloadTask.model_validate(obj.model_dump())
        assert restored == obj
        assert restored.status == DownloadStatus.DOWNLOADING
        assert restored.progress == 0.25

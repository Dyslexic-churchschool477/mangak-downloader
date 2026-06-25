"""Tests for ``MangaKClient`` — the async HTTP client for mangak.io.

Every network operation is mocked so no real HTTP calls are made.
Uses ``unittest.mock`` to replace ``_fetch_html`` and ``_fetch_json``
on the client, and to intercept ``download_image``.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from mangak.core.client import MangaKClient, _extract_next_data, _rotate_cdn_url
from mangak.core.exceptions import (
    ChapterNotFoundError,
    DownloadError,
    MangaNotFoundError,
)
from mangak.core.models import Chapter, ChapterListItem, Manga, MangaStats, SearchResult

# =========================================================================
#  Test data — realistic HTML / JSON snippets
# =========================================================================

MANGA_NEXT_DATA = {
    "props": {
        "pageProps": {
            "initialManga": {
                "id": "12345",
                "slug": "nano-machine",
                "url": "https://mangak.io/nano-machine",
                "name": "Nano Machine",
                "altName": "나노마신",
                "altNames": [{"name": "ナノマシン", "language": "ja"}],
                "cover": "https://mangak.io/uploads/nano-machine/cover.webp",
                "status": "Ongoing",
                "rating": 4.5,
                "summary": "A boy raised in the mountains...",
                "genres": [{"id": "1", "name": "Action", "slug": "action", "url": "/genre/action"}],
                "tags": [],
                "authors": [{"id": "42", "name": "Park作者", "slug": "park-author", "url": "/author/park-author"}],
                "stats": {"views": 1_234_567, "bookmarks_count": 8_901, "comments_count": 234, "manga_only_comments_count": 56, "chapters_count": 187, "ratings_count": 4_321, "reviews_count": 12},
                "latestChapters": [{"id": "ch-100", "name": "Chapter 100", "url": "/nano-machine/chapter-100", "slug": "chapter-100", "date": "2024-03-15T12:00:00Z", "cv": 1710000000, "content_type": "chapter"}],
                "isAdult": False,
                "isHot": True,
                "isNew": False,
                "cv": 1710000000,
                "updatedAt": "2024-03-15T12:00:00Z",
                "displayAltName": "나노마신",
                "displayRating": "4.5",
                "displayViews": "1.23M",
                "displayBookmarks": "8.9K",
                "displayChapters": "187",
                "displayUpdated": "2024-03-15",
                "displayUpdatedShort": "Mar 15",
            }
        }
    }
}

CHAPTER_NEXT_DATA = {
    "props": {
        "pageProps": {
            "initialChapter": {
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
                ],
            }
        }
    }
}

SEARCH_NEXT_DATA = {
    "props": {
        "pageProps": {
            "ssrItems": [
                {
                    "id": "67890",
                    "slug": "solo-leveling",
                    "url": "https://mangak.io/solo-leveling",
                    "name": "Solo Leveling",
                    "cover": "https://mangak.io/uploads/cover.webp",
                    "status": "completed",
                    "rating": 4.8,
                    "summary": "A hunter becomes a ruler...",
                    "genres": [{"id": "1", "name": "Action", "slug": "action", "url": "/genre/action"}],
                    "stats": None,
                    "isAdult": False,
                }
            ]
        }
    }
}

CHAPTER_LIST_JSON = {
    "success": True,
    "data": {
        "chapters": [
            {
                "id": "ch-50",
                "url": "https://api.mangak.io/titles/12345/chapters/ch-50",
                "name": "Chapter 50",
                "slug": "chapter-50",
                "views": 45_678,
                "comments_count": 89,
                "updated_at": "2024-02-20T08:30:00Z",
                "chapter_number": 50,
            }
        ]
    },
}

META_JSON = {
    "success": True,
    "data": {
        "views": 500_000,
        "bookmarks_count": 3_000,
        "comment_count": 100,
        "manga_only_comments_count": 20,
        "chapters_count": 50,
        "ratings_count": 2_000,
        "reviews_count": 5,
    },
}

RECOMMENDATIONS_JSON = {
    "success": True,
    "data": [
        {
            "id": "999",
            "slug": "second-life-rank",
            "url": "https://mangak.io/second-life-rank",
            "name": "Second Life Ranker",
            "cover": "https://mangak.io/uploads/cover.webp",
            "status": "ongoing",
            "rating": 4.3,
            "summary": "A boy seeks revenge...",
            "genres": [{"id": "2", "name": "Fantasy", "slug": "fantasy", "url": "/genre/fantasy"}],
            "stats": None,
            "isAdult": False,
        }
    ],
}

MANGA_HTML = (
    '<html><script id="__NEXT_DATA__" type="application/json">'
    + json.dumps(MANGA_NEXT_DATA)
    + '</script></html>'
)

CHAPTER_HTML = (
    '<html><script id="__NEXT_DATA__" type="application/json">'
    + json.dumps(CHAPTER_NEXT_DATA)
    + '</script></html>'
)

SEARCH_HTML = (
    '<html><script id="__NEXT_DATA__" type="application/json">'
    + json.dumps(SEARCH_NEXT_DATA)
    + '</script></html>'
)

BAD_HTML = "<html><body>No script data here</body></html>"
EMPTY_SEARCH_HTML = (
    '<html><script id="__NEXT_DATA__" type="application/json">'
    + json.dumps({"props": {"pageProps": {"ssrItems": []}}})
    + '</script></html>'
)


# =========================================================================
#  _extract_next_data
# =========================================================================


class TestExtractNextData:
    def test_extracts_page_props(self):
        result = _extract_next_data(MANGA_HTML)
        assert "initialManga" in result
        assert result["initialManga"]["slug"] == "nano-machine"

    def test_raises_on_bad_html(self):
        with pytest.raises(ValueError, match="__NEXT_DATA__ script tag not found"):
            _extract_next_data(BAD_HTML)

    def test_extracts_search_results(self):
        result = _extract_next_data(SEARCH_HTML)
        assert "ssrItems" in result
        assert len(result["ssrItems"]) == 1


# =========================================================================
#  _rotate_cdn_url
# =========================================================================


class TestRotateCdnUrl:
    def test_replaces_subdomain(self):
        url = "https://rx.qvzra.org/uploads/img.webp"
        rotated = _rotate_cdn_url(url)
        # Should have a different letter
        assert rotated.startswith("https://rx.qvzr")
        assert len(rotated) > len(url) - 2  # roughly same length
        assert "/uploads/img.webp" in rotated

    def test_returns_something_reasonable(self):
        url = "https://rx.qvzra.org/img.webp"
        for _ in range(5):
            rotated = _rotate_cdn_url(url)
            assert rotated != url  # rotation should change it at least sometimes
            assert "qvzr" in rotated


# =========================================================================
#  MangaKClient — mocked via patch.object
# =========================================================================


@pytest.mark.asyncio
class TestMangaKClient:
    """All tests use patch.object on _fetch_html / _fetch_json."""

    async def test_get_manga_info(self):
        with patch.object(MangaKClient, "_fetch_html", new_callable=AsyncMock) as mock:
            mock.return_value = MANGA_HTML
            async with MangaKClient() as client:
                manga = await client.get_manga_info("nano-machine")
                assert isinstance(manga, Manga)
                assert manga.slug == "nano-machine"
                assert manga.name == "Nano Machine"
                assert manga.rating == 4.5
                assert manga.is_adult is False
                assert manga.is_hot is True
                mock.assert_awaited_once()

    async def test_get_manga_info_not_found(self):
        """HTTP 404 should raise MangaNotFoundError."""
        with patch.object(MangaKClient, "_fetch_html", new_callable=AsyncMock) as mock:
            mock.side_effect = httpx.HTTPStatusError(
                "404 Not Found", request=httpx.Request("GET", "https://mangak.io/missing"), response=httpx.Response(404)
            )
            async with MangaKClient() as client:
                with pytest.raises(MangaNotFoundError, match="missing"):
                    await client.get_manga_info("missing")

    async def test_get_manga_info_no_initial_manga(self):
        """Missing initialManga key raises MangaNotFoundError."""
        bad_html = (
            '<html><script id="__NEXT_DATA__" type="application/json">'
            + json.dumps({"props": {"pageProps": {}}})
            + '</script></html>'
        )
        with patch.object(MangaKClient, "_fetch_html", new_callable=AsyncMock) as mock:
            mock.return_value = bad_html
            async with MangaKClient() as client:
                with pytest.raises(MangaNotFoundError, match="nano-machine"):
                    await client.get_manga_info("nano-machine")

    async def test_get_chapter(self):
        with patch.object(MangaKClient, "_fetch_html", new_callable=AsyncMock) as mock:
            mock.return_value = CHAPTER_HTML
            async with MangaKClient() as client:
                chapter = await client.get_chapter("nano-machine", "chapter-50")
                assert isinstance(chapter, Chapter)
                assert chapter.id == "ch-50"
                assert len(chapter.images) == 2
                mock.assert_awaited_once()

    async def test_get_chapter_not_found(self):
        with patch.object(MangaKClient, "_fetch_html", new_callable=AsyncMock) as mock:
            mock.side_effect = httpx.HTTPStatusError(
                "404", request=httpx.Request("GET", "https://mangak.io/m/ch"), response=httpx.Response(404)
            )
            async with MangaKClient() as client:
                with pytest.raises(ChapterNotFoundError, match="nano-machine/chapter-99"):
                    await client.get_chapter("nano-machine", "chapter-99")

    async def test_search(self):
        with patch.object(MangaKClient, "_fetch_html", new_callable=AsyncMock) as mock:
            mock.return_value = SEARCH_HTML
            async with MangaKClient() as client:
                results = await client.search("solo leveling")
                assert len(results) == 1
                assert isinstance(results[0], SearchResult)
                assert results[0].slug == "solo-leveling"
                assert results[0].rating == 4.8

    async def test_search_empty(self):
        with patch.object(MangaKClient, "_fetch_html", new_callable=AsyncMock) as mock:
            mock.return_value = EMPTY_SEARCH_HTML
            async with MangaKClient() as client:
                results = await client.search("nothing")
                assert results == []

    async def test_search_on_http_error_returns_empty(self):
        with patch.object(MangaKClient, "_fetch_html", new_callable=AsyncMock) as mock:
            mock.side_effect = httpx.HTTPStatusError(
                "500", request=httpx.Request("GET", "https://mangak.io/search?q=x"), response=httpx.Response(500)
            )
            async with MangaKClient() as client:
                results = await client.search("x")
                assert results == []

    async def test_get_chapter_list(self):
        with patch.object(MangaKClient, "_fetch_json", new_callable=AsyncMock) as mock:
            mock.return_value = CHAPTER_LIST_JSON
            async with MangaKClient() as client:
                items = await client.get_chapter_list("12345", 1710000000)
                assert len(items) == 1
                assert isinstance(items[0], ChapterListItem)
                assert items[0].slug == "chapter-50"

    async def test_get_chapter_list_empty_on_no_success(self):
        with patch.object(MangaKClient, "_fetch_json", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": False}
            async with MangaKClient() as client:
                items = await client.get_chapter_list("12345", 0)
                assert items == []

    async def test_get_meta(self):
        with patch.object(MangaKClient, "_fetch_json", new_callable=AsyncMock) as mock:
            mock.return_value = META_JSON
            async with MangaKClient() as client:
                stats = await client.get_meta("12345")
                assert isinstance(stats, MangaStats)
                assert stats.views == 500_000
                assert stats.bookmarks_count == 3_000
                assert stats.comments_count == 100  # mapped from comment_count

    async def test_get_meta_returns_none_on_http_error(self):
        with patch.object(MangaKClient, "_fetch_json", new_callable=AsyncMock) as mock:
            mock.side_effect = httpx.HTTPStatusError(
                "404", request=httpx.Request("GET", "url"), response=httpx.Response(404)
            )
            async with MangaKClient() as client:
                stats = await client.get_meta("missing")
                assert stats is None

    async def test_get_recommendations(self):
        with patch.object(MangaKClient, "_fetch_json", new_callable=AsyncMock) as mock:
            mock.return_value = RECOMMENDATIONS_JSON
            async with MangaKClient() as client:
                results = await client.get_recommendations("999")
                assert len(results) == 1
                assert isinstance(results[0], SearchResult)
                assert results[0].slug == "second-life-rank"

    async def test_get_recommendations_empty_on_no_success(self):
        with patch.object(MangaKClient, "_fetch_json", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": False}
            async with MangaKClient() as client:
                results = await client.get_recommendations("999")
                assert results == []

    def _make_response(self, status_code: int = 200, content: bytes = b"") -> httpx.Response:
        """Build an httpx.Response with a minimal internal request so raise_for_status works."""
        req = httpx.Request("GET", "https://example.com/dummy")
        return httpx.Response(status_code, content=content, request=req)

    async def test_download_image_writes_bytes(self, tmp_path):
        """Verify download_image writes content to the given path."""
        img_bytes = b"fake-webp-bytes"
        dest = tmp_path / "manga" / "ch1" / "001.webp"

        mock_response = self._make_response(200, img_bytes)
        mock_client_obj = AsyncMock(spec=httpx.AsyncClient)
        mock_client_obj.get.return_value = mock_response

        async with MangaKClient() as client:
            client._client = mock_client_obj  # inject mock
            result = await client.download_image(
                "https://rx.qvzra.org/img.webp", dest, use_rotation=False
            )
            assert result is True
            assert dest.exists()
            assert dest.read_bytes() == img_bytes

    async def test_download_image_creates_parent_dirs(self, tmp_path):
        """Parent directories should be created automatically."""
        dest = tmp_path / "does" / "not" / "exist" / "img.webp"
        mock_response = self._make_response(200, b"data")
        mock_client_obj = AsyncMock(spec=httpx.AsyncClient)
        mock_client_obj.get.return_value = mock_response

        async with MangaKClient() as client:
            client._client = mock_client_obj
            result = await client.download_image("https://rx.qvzra.org/img.webp", dest, use_rotation=False)
            assert result is True
            assert dest.exists()

    async def test_download_image_raises_on_http_error(self, tmp_path):
        dest = tmp_path / "fail.webp"
        mock_client_obj = AsyncMock(spec=httpx.AsyncClient)
        mock_client_obj.get.side_effect = httpx.HTTPStatusError(
            "403 Forbidden",
            request=httpx.Request("GET", "https://rx.qvzra.org/img.webp"),
            response=self._make_response(403),
        )

        async with MangaKClient() as client:
            client._client = mock_client_obj
            with pytest.raises(DownloadError, match="Failed to download"):
                await client.download_image("https://rx.qvzra.org/img.webp", dest, use_rotation=False)

    async def test_download_image_batch(self, tmp_path):
        """Verify batch download returns correct count."""
        img_bytes = b"fake-webp"
        base_dir = tmp_path / "manga" / "ch1"
        urls = [
            "https://rx.qvzra.org/001.webp",
            "https://rx.qvzra.org/002.webp",
            "https://rx.qvzra.org/003.webp",
        ]

        mock_response = self._make_response(200, img_bytes)
        mock_client_obj = AsyncMock(spec=httpx.AsyncClient)
        mock_client_obj.get.return_value = mock_response

        async with MangaKClient() as client:
            client._client = mock_client_obj
            completed = await client.download_image_batch(
                urls, base_dir, use_rotation=False, concurrency=2
            )
            assert completed == 3
            for i in range(3):
                f = base_dir / f"{i + 1:03d}.webp"
                assert f.exists(), f"{f} not created"
                assert f.read_bytes() == img_bytes

    async def test_download_image_batch_with_custom_filenames(self, tmp_path):
        img_bytes = b"page-data"
        base_dir = tmp_path / "custom"
        urls = ["https://rx.qvzra.org/a.webp", "https://rx.qvzra.org/b.webp"]
        filenames = ["page_01.webp", "page_02.webp"]

        mock_response = self._make_response(200, img_bytes)
        mock_client_obj = AsyncMock(spec=httpx.AsyncClient)
        mock_client_obj.get.return_value = mock_response

        async with MangaKClient() as client:
            client._client = mock_client_obj
            completed = await client.download_image_batch(
                urls, base_dir, filenames=filenames, use_rotation=False
            )
            assert completed == 2
            assert (base_dir / "page_01.webp").exists()
            assert (base_dir / "page_02.webp").exists()

    async def test_extract_next_data_public_method(self):
        with patch.object(MangaKClient, "_fetch_html", new_callable=AsyncMock) as mock:
            mock.return_value = MANGA_HTML
            async with MangaKClient() as client:
                props = await client.extract_next_data("https://mangak.io/nano-machine")
                assert "initialManga" in props
                mock.assert_awaited_once()

    async def test_extract_next_data_raises_on_bad_html(self):
        with patch.object(MangaKClient, "_fetch_html", new_callable=AsyncMock) as mock:
            mock.return_value = BAD_HTML
            async with MangaKClient() as client:
                with pytest.raises(ValueError, match="__NEXT_DATA__"):
                    await client.extract_next_data("https://mangak.io/bad")

    async def test_client_not_started_raises(self):
        """Using client outside 'async with' should raise RuntimeError."""
        client = MangaKClient()
        with pytest.raises(RuntimeError, match="Client not started"):
            await client._fetch_html("https://example.com")

    async def test_client_lifecycle_cleanup(self):
        """Ensure __aexit__ sets _client to None."""
        client = MangaKClient()
        await client.__aenter__()
        assert client._client is not None
        await client.__aexit__(None, None, None)
        assert client._client is None


# =========================================================================
#  Search — malformed results are skipped
# =========================================================================


@pytest.mark.asyncio
async def test_search_skips_malformed_entries():
    """A malformed item (missing required fields) is skipped silently."""
    bad_html = (
        '<html><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps({
            "props": {
                "pageProps": {
                    "ssrItems": [
                        {"id": "good", "slug": "good", "url": "/good", "name": "Good", "cover": "https://example.com/c.webp", "status": "ongoing", "rating": 1.0, "genres": []},
                        {"id": "bad", "name": "Bad"}  # missing required fields
                    ]
                }
            }
        })
        + '</script></html>'
    )
    with patch.object(MangaKClient, "_fetch_html", new_callable=AsyncMock) as mock:
        mock.return_value = bad_html
        async with MangaKClient() as client:
            results = await client.search("test")
            assert len(results) == 1
            assert results[0].slug == "good"

"""
Async httpx API client for mangak.io.

Handles all communication with:
  - mangak.io SSR pages (__NEXT_DATA__ extraction)
  - api.mangak.io REST endpoints
  - Image CDN (rx.qvzr*.org)

Every network call uses ``httpx.AsyncClient`` with proper headers,
subdomain rotation, and error handling.
"""

from __future__ import annotations

import asyncio
import itertools
import re
from pathlib import Path
from typing import Any, Optional

import httpx

from mangak.core.exceptions import (
    ChapterNotFoundError,
    DownloadError,
    MangaNotFoundError,
)
from mangak.core.models import (
    Chapter,
    ChapterListItem,
    Manga,
    MangaStats,
    SearchResult,
)

# ──────────────────────────────────────────────
#  Constants
# ──────────────────────────────────────────────

BASE_URL = "https://mangak.io"
API_BASE = "https://api.mangak.io"
CDN_SUBDOMAINS = list("abcdefghijk")  # a through k

_CDN_ROTATOR = itertools.cycle(CDN_SUBDOMAINS)

# User-Agent: Chrome 120 on Windows
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Default timeout
_TIMEOUT = httpx.Timeout(30.0, connect=15.0, read=30.0)

# ──────────────────────────────────────────────
#  Header builders
# ──────────────────────────────────────────────


def _html_headers() -> dict[str, str]:
    return {
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }


def _api_headers() -> dict[str, str]:
    return {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
        "Referer": f"{BASE_URL}/",
        "Accept-Language": "en-US,en;q=0.5",
    }


def _image_headers() -> dict[str, str]:
    return {
        "User-Agent": _USER_AGENT,
        "Referer": f"{BASE_URL}/",
        "Accept": "image/webp,image/*,*/*;q=0.8",
    }


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────


def _rotate_cdn_url(url: str) -> str:
    """Return the URL unchanged — CDN subdomain rotation disabled (causes DNS errors)."""
    return url


def _extract_next_data(html: str) -> dict[str, Any]:
    """Extract the ``props.pageProps`` dict from a mangak.io SSR page."""
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        raise ValueError("__NEXT_DATA__ script tag not found in HTML")
    import json

    data = json.loads(match.group(1))
    return data["props"]["pageProps"]


# ──────────────────────────────────────────────
#  Client
# ──────────────────────────────────────────────


class MangaKClient:
    """
    Async HTTP client wrapping all mangak.io endpoints.

    Usage::

        async with MangaKClient() as client:
            manga = await client.get_manga_info("nano-machine")
            ch = await client.get_chapter("nano-machine", "chapter-1")
            results = await client.search("solo leveling")
    """

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    # ── Context manager ─────────────────────────

    async def __aenter__(self) -> MangaKClient:
        self._client = httpx.AsyncClient(
            headers=_html_headers(),
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── Internal request helper ─────────────────

    async def _fetch_html(self, url: str) -> str:
        """Fetch an HTML page and return the decoded text."""
        if self._client is None:
            raise RuntimeError("Client not started; use 'async with'")
        resp = await self._client.get(url, headers=_html_headers())
        resp.raise_for_status()
        return resp.text

    async def _fetch_json(self, url: str) -> Any:
        """Fetch a JSON endpoint and return the parsed dict/list."""
        if self._client is None:
            raise RuntimeError("Client not started; use 'async with'")
        resp = await self._client.get(url, headers=_api_headers())
        resp.raise_for_status()
        return resp.json()

    # ── Public API ──────────────────────────────

    async def extract_next_data(self, url: str) -> dict[str, Any]:
        """Universal ``__NEXT_DATA__`` extractor for any mangak.io page."""
        html = await self._fetch_html(url)
        return _extract_next_data(html)

    async def get_manga_info(self, slug: str) -> Manga:
        """
        Fetch manga detail page and parse ``initialManga``.

        Raises ``MangaNotFoundError`` if the slug does not resolve.
        """
        url = f"{BASE_URL}/{slug}"
        try:
            page_props = await self.extract_next_data(url)
        except (httpx.HTTPStatusError, ValueError) as exc:
            raise MangaNotFoundError(slug) from exc

        raw = page_props.get("initialManga")
        if not raw:
            raise MangaNotFoundError(slug)

        # Field-name normalisation: JSON uses camelCase, model uses snake_case
        raw = _normalise_manga(raw)
        return Manga.model_validate(raw)

    async def get_chapter(self, slug: str, chapter_slug: str) -> Chapter:
        """
        Fetch chapter page and parse ``initialChapter`` with image URLs.

        Raises ``ChapterNotFoundError`` if the chapter slug does not resolve.
        """
        url = f"{BASE_URL}/{slug}/{chapter_slug}"
        try:
            page_props = await self.extract_next_data(url)
        except (httpx.HTTPStatusError, ValueError) as exc:
            raise ChapterNotFoundError(slug, chapter_slug) from exc

        raw = page_props.get("initialChapter")
        if not raw:
            raise ChapterNotFoundError(slug, chapter_slug)

        raw = _normalise_chapter(raw)
        return Chapter.model_validate(raw)

    async def search(self, query: str) -> list[SearchResult]:
        """
        Search via SSR page (``/search?q=...``) and return parsed results.

        Returns an empty list if no results are found.
        """
        from urllib.parse import quote

        url = f"{BASE_URL}/search?q={quote(query)}"
        try:
            page_props = await self.extract_next_data(url)
        except (httpx.HTTPStatusError, ValueError):
            return []

        raw_items = page_props.get("ssrItems", [])
        results: list[SearchResult] = []
        for item in raw_items:
            item = _normalise_search_result(item)
            try:
                results.append(SearchResult.model_validate(item))
            except Exception:
                continue  # skip malformed entries
        return results

    async def get_chapter_list(
        self, manga_id: str, cv: int
    ) -> list[ChapterListItem]:
        """
        Fetch full chapter list from the REST API.

        Requires the ``cv`` timestamp from ``initialManga.cv``.
        """
        url = f"{API_BASE}/titles/{manga_id}/chapters?cv={cv}"
        data = await self._fetch_json(url)

        if not data.get("success"):
            return []

        chapters_raw = data.get("data", {}).get("chapters", [])
        items: list[ChapterListItem] = []
        for ch in chapters_raw:
            ch = _normalise_chapter_list_item(ch)
            try:
                items.append(ChapterListItem.model_validate(ch))
            except Exception:
                continue
        return items

    async def get_meta(self, manga_id: str) -> Optional[MangaStats]:
        """
        Fetch meta/stats for a manga from the REST API.

        Returns ``None`` if the endpoint does not return a valid response.
        """
        url = f"{API_BASE}/meta/manga/{manga_id}"
        try:
            data = await self._fetch_json(url)
        except httpx.HTTPStatusError:
            return None

        if not data.get("success"):
            return None

        raw = data.get("data", {})
        # Map API fields to our model
        mapped = {
            "views": raw.get("views", 0),
            "bookmarks_count": raw.get("bookmarks_count", 0),
            "comments_count": raw.get("comment_count", 0),
            "manga_only_comments_count": raw.get("manga_only_comments_count", 0),
            "chapters_count": raw.get("chapters_count", 0),
            "ratings_count": raw.get("ratings_count", 0),
            "reviews_count": raw.get("reviews_count", 0),
        }
        return MangaStats.model_validate(mapped)

    async def get_recommendations(
        self, manga_id: str
    ) -> list[SearchResult]:
        """Fetch recommendations for a manga from the REST API."""
        url = f"{API_BASE}/recommendations/{manga_id}"
        try:
            data = await self._fetch_json(url)
        except httpx.HTTPStatusError:
            return []

        if not data.get("success"):
            return []

        raw_items = data.get("data", [])
        results: list[SearchResult] = []
        for item in raw_items:
            item = _normalise_search_result(item)
            try:
                results.append(SearchResult.model_validate(item))
            except Exception:
                continue
        return results

    async def download_image(
        self,
        url: str,
        path: Path,
        use_rotation: bool = True,
    ) -> bool:
        """
        Download a single image from the CDN to *path*.

        Returns ``True`` on success, ``False`` on failure.
        If ``use_rotation`` is true the CDN subdomain is rotated.
        """
        if self._client is None:
            raise RuntimeError("Client not started; use 'async with'")

        target_url = _rotate_cdn_url(url) if use_rotation else url

        try:
            resp = await self._client.get(
                target_url, headers=_image_headers(), timeout=_TIMEOUT
            )
            resp.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(resp.content)
            return True
        except (httpx.HTTPStatusError, OSError) as exc:
            raise DownloadError(f"Failed to download {url}: {exc}") from exc

    async def download_image_batch(
        self,
        urls: list[str],
        base_dir: Path,
        filenames: Optional[list[str]] = None,
        use_rotation: bool = True,
        concurrency: int = 4,
        progress_callback=None,
    ) -> int:
        """
        Download multiple images concurrently, returning the count of successful downloads.

        If *filenames* is given it must be the same length as *urls*; otherwise
        each file is named by its zero-padded index + ``.webp``.

        *progress_callback* is called as ``f(idx, total)`` after each download.
        """
        sem = asyncio.Semaphore(concurrency)
        completed = 0

        async def _dl(idx: int, url: str) -> bool:
            nonlocal completed
            fname = filenames[idx] if filenames else f"{idx + 1:03d}.webp"
            dest = base_dir / fname
            async with sem:
                try:
                    ok = await self.download_image(url, dest, use_rotation)
                    if ok:
                        completed += 1
                except DownloadError:
                    return False
                if progress_callback:
                    progress_callback(idx + 1, len(urls))
                return True

        tasks = [_dl(i, u) for i, u in enumerate(urls)]
        await asyncio.gather(*tasks, return_exceptions=True)
        return completed


# ──────────────────────────────────────────────
#  Field-name normalisers (camelCase → snake_case)
# ──────────────────────────────────────────────


def _normalise_manga(raw: dict[str, Any]) -> dict[str, Any]:
    """Map camelCase JSON keys to snake_case model fields for Manga."""
    mapping = {
        "altName": "alt_name",
        "altNames": "alt_names",
        "isAdult": "is_adult",
        "isHot": "is_hot",
        "isNew": "is_new",
        "updatedAt": "updated_at",
        "latestChapters": "latest_chapters",
        "displayAltName": "display_alt_name",
        "displayRating": "display_rating",
        "displayViews": "display_views",
        "displayBookmarks": "display_bookmarks",
        "displayChapters": "display_chapters",
        "displayUpdated": "display_updated",
        "displayUpdatedShort": "display_updated_short",
    }
    result = _apply_mapping(raw, mapping)

    # Normalise nested stats object
    stats = result.get("stats")
    if isinstance(stats, dict):
        stats_mapping = {
            "bookmarksCount": "bookmarks_count",
            "commentsCount": "comments_count",
            "mangaOnlyCommentsCount": "manga_only_comments_count",
            "chaptersCount": "chapters_count",
            "ratingsCount": "ratings_count",
            "reviewsCount": "reviews_count",
        }
        result["stats"] = _apply_mapping(stats, stats_mapping)

    return result


def _normalise_chapter(raw: dict[str, Any]) -> dict[str, Any]:
    """Map camelCase JSON keys to snake_case model fields for Chapter."""
    mapping = {
        "updated_at": "updated_at",  # already snake_case in API
        "comments_count": "comments_count",
        "chapter_number": "chapter_number",
    }
    return _apply_mapping(raw, mapping)


def _normalise_chapter_list_item(raw: dict[str, Any]) -> dict[str, Any]:
    """Map camelCase JSON keys to snake_case for ChapterListItem."""
    mapping = {
        "updated_at": "updated_at",
        "comments_count": "comments_count",
        "chapter_number": "chapter_number",
    }
    return _apply_mapping(raw, mapping)


def _normalise_search_result(raw: dict[str, Any]) -> dict[str, Any]:
    """Map camelCase JSON keys to snake_case for SearchResult."""
    mapping = {
        "isAdult": "is_adult",
        "isHot": "is_hot",
        "isNew": "is_new",
    }
    return _apply_mapping(raw, mapping)


def _apply_mapping(
    raw: dict[str, Any], mapping: dict[str, str]
) -> dict[str, Any]:
    """Apply a camelCase → snake_case mapping to a dict."""
    result: dict[str, Any] = {}
    for key, value in raw.items():
        mapped_key = mapping.get(key, key)
        result[mapped_key] = value
    return result

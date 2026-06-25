"""
JSON-based settings manager.

Reads and writes ``settings.json`` in the project root directory.
Provides typed accessors, defaults, reset, and validation on load/save.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from mangak.core.exceptions import ConfigError

# ──────────────────────────────────────────────
#  Default schema
# ──────────────────────────────────────────────

_DEFAULT_SETTINGS: dict[str, Any] = {
    "download_dir": "downloads",
    "export_format": "cbz",
    "concurrent_downloads": 4,
    "concurrent_image_downloads": 4,
    "rate_limit_delay": 0.25,
    "delete_images_after_export": True,
    "auto_open_folder": False,
    "theme": "dark",
    "window_geometry": None,
    "last_searches": [],
}

# Valid export formats
_VALID_FORMATS = {"folder", "cbz", "zip", "pdf"}

# Valid themes
_VALID_THEMES = {"dark"}

# Keys that must be integers
_INT_KEYS = {"concurrent_downloads", "concurrent_image_downloads"}

# Keys that must be floats
_FLOAT_KEYS = {"rate_limit_delay"}

# Keys that must be bools
_BOOL_KEYS = {"delete_images_after_export", "auto_open_folder"}


def _project_root() -> Path:
    """Return the project root directory (grandparent of ``src/mangak/core/``)."""
    return Path(__file__).resolve().parents[3]


# ──────────────────────────────────────────────
#  Settings manager
# ──────────────────────────────────────────────


class Settings:
    """
    JSON settings manager backed by ``settings.json`` in the project root.

    Usage::

        s = Settings()
        s.get("download_dir")          # "downloads"
        s.set("theme", "dark")         # saved immediately
        s.all()                        # full dict
        s.reset()                      # restore defaults
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        self._root = root or _project_root()
        self._path: Path = self._root / "settings.json"
        self._data: dict[str, Any] = dict(_DEFAULT_SETTINGS)
        self._load()

    # ── Public accessors ────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for *key*, or *default* if not present."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set *key* to *value* (with type validation) and persist immediately."""
        self._validate_value(key, value)
        self._data[key] = value
        self._save()

    def all(self) -> dict[str, Any]:
        """Return a shallow copy of the current settings dict."""
        return dict(self._data)

    def reset(self) -> None:
        """Restore all settings to defaults and persist."""
        self._data = dict(_DEFAULT_SETTINGS)
        self._save()

    # ── Persistence ─────────────────────────────

    def _load(self) -> None:
        """Load settings from ``settings.json``, merging with defaults."""
        if not self._path.exists():
            self._save()
            return

        try:
            text = self._path.read_text(encoding="utf-8")
            if not text.strip():
                self._save()
                return
            loaded = json.loads(text)
        except (json.JSONDecodeError, OSError) as exc:
            raise ConfigError(
                f"Failed to parse {self._path}: {exc}"
            ) from exc

        # Merge: start with defaults, overlay saved values
        merged = dict(_DEFAULT_SETTINGS)
        merged.update(loaded)
        self._data = merged

        # Validate the merged data
        self._validate_all()

        # Re-save to normalise any missing keys
        self._save()

    def _save(self) -> None:
        """Write current settings to ``settings.json``."""
        self._validate_all()
        try:
            self._path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            raise ConfigError(f"Failed to write {self._path}: {exc}") from exc

    # ── Validation ──────────────────────────────

    def _validate_all(self) -> None:
        """Validate every key in the current data dict."""
        for key, value in self._data.items():
            self._validate_value(key, value)

    def _validate_value(self, key: str, value: Any) -> None:
        """Raise ``ConfigError`` if *value* has the wrong type for *key*."""
        if key in _INT_KEYS and not isinstance(value, int):
            raise ConfigError(
                f"'{key}' must be an integer, got {type(value).__name__}"
            )
        if key in _FLOAT_KEYS and not isinstance(value, (int, float)):
            raise ConfigError(
                f"'{key}' must be a number, got {type(value).__name__}"
            )
        if key in _BOOL_KEYS and not isinstance(value, bool):
            raise ConfigError(
                f"'{key}' must be a boolean, got {type(value).__name__}"
            )
        if key == "export_format" and value not in _VALID_FORMATS:
            raise ConfigError(
                f"Invalid export format '{value}'. Choose from {sorted(_VALID_FORMATS)}"
            )
        if key == "theme" and value not in _VALID_THEMES:
            raise ConfigError(
                f"Invalid theme '{value}'. Choose from {sorted(_VALID_THEMES)}"
            )
        if key == "last_searches" and not isinstance(value, list):
            raise ConfigError(
                f"'last_searches' must be a list, got {type(value).__name__}"
            )

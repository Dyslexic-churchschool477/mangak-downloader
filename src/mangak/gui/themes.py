"""ThemeEngine — loads JSON color tokens, resolves {{token}} placeholders in QSS, applies to QApplication."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from PyQt6.QtWidgets import QApplication


class ThemeEngine:
    """Loads theme color tokens and resolves them into QSS stylesheets.

    Usage::

        engine = ThemeEngine()
        engine.load_json("resources/dark.json")
        qss = engine.resolve_file("resources/dark.qss")
        engine.apply(qss)
    """

    def __init__(self) -> None:
        self._tokens: dict[str, Any] = {}
        self._flat: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_json(self, path: str) -> dict[str, Any]:
        """Load colour tokens from a JSON file and flatten them.

        Returns the raw dictionary for inspection.
        """
        with open(path, encoding="utf-8") as fh:
            self._tokens = json.load(fh)
        self._flat = self._flatten(self._tokens)
        return self._tokens

    def load_dict(self, tokens: dict[str, Any]) -> None:
        """Load colour tokens from an already-parsed dictionary."""
        self._tokens = tokens
        self._flat = self._flatten(self._tokens)

    def get(self, key: str, default: str = "") -> str:
        """Look up a single token value by its dotted path, e.g. ``bg.base``."""
        return self._flat.get(key, default)

    def resolve(self, template: str) -> str:
        """Replace every ``{{token.name}}`` placeholder with its value.

        Unknown tokens are left as-is so missing definitions are visible.
        """
        def _replacer(m: re.Match[str]) -> str:
            key = m.group(1)
            return self._flat.get(key, m.group(0))
        return re.sub(r"\{\{(\w+(?:\.\w+)+)\}\}", _replacer, template)

    def resolve_file(self, qss_path: str) -> str:
        """Read a QSS file, resolve all placeholders, return the stylesheet."""
        with open(qss_path, encoding="utf-8") as fh:
            raw = fh.read()
        return self.resolve(raw)

    def apply(self, qss: str) -> None:
        """Set ``QApplication.instance().setStyleSheet(qss)``."""
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(qss)

    def apply_json(self, json_path: str, qss_path: str) -> None:
        """Convenience: load JSON, resolve QSS, apply in one call."""
        self.load_json(json_path)
        qss = self.resolve_file(qss_path)
        self.apply(qss)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _flatten(
        d: dict[str, Any],
        parent_key: str = "",
        sep: str = ".",
    ) -> dict[str, str]:
        """Recursively flatten a nested dict into dotted-key → str.

        Only leaf values that look like CSS colours are kept.
        """
        items: dict[str, str] = {}
        for k, v in d.items():
            full_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(ThemeEngine._flatten(v, full_key, sep))
            elif isinstance(v, str):
                items[full_key] = v
        return items

    def resource_path(self, *parts: str) -> str:
        """Return the absolute path to a resource file relative to the
        ``resources/`` directory alongside this module."""
        base = os.path.join(os.path.dirname(__file__), "resources")
        return os.path.join(base, *parts)

    @classmethod
    def default_dark(cls) -> ThemeEngine:
        """Factory: create an engine pre-loaded with the built-in dark theme."""
        engine = cls()
        json_path = os.path.join(os.path.dirname(__file__), "resources", "dark.json")
        qss_path = os.path.join(os.path.dirname(__file__), "resources", "dark.qss")
        engine.apply_json(json_path, qss_path)
        return engine

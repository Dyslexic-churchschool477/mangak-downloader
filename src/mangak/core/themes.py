"""
Theme/color constants shared between CLI and GUI interfaces.

Provides a Colors class with all design tokens, runtime theme switching
support, and a cache of loaded theme configurations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class Colors:
    """
    Immutable color palette shared across CLI and GUI.

    All tokens from the GUI design spec:
      - BG_*     : Background surfaces
      - TEXT_*   : Foreground text colours
      - ACCENT_* : Accent / highlight colours
      - DANGER / WARNING / SUCCESS : Semantic colours
      - BORDER   : Subtle separator colour
    """

    # --- Backgrounds ---
    BG_BASE: ClassVar[str] = "#0D0D0F"
    BG_SURFACE: ClassVar[str] = "#16161A"
    BG_ELEVATED: ClassVar[str] = "#1C1C22"
    BG_GLASS: ClassVar[str] = "rgba(22, 22, 26, 0.75)"
    BG_HOVER: ClassVar[str] = "#242430"
    BG_ACTIVE: ClassVar[str] = "#2A2A36"

    # --- Text ---
    TEXT_PRIMARY: ClassVar[str] = "#EAEAF0"
    TEXT_SECONDARY: ClassVar[str] = "#7F7F8A"

    # --- Accents ---
    ACCENT_PRIMARY: ClassVar[str] = "#6C5CE7"
    ACCENT_SECONDARY: ClassVar[str] = "#00CEC9"

    # --- Semantic ---
    DANGER: ClassVar[str] = "#FF6B6B"
    WARNING: ClassVar[str] = "#FDCB6E"
    SUCCESS: ClassVar[str] = "#00B894"

    # --- Borders ---
    BORDER: ClassVar[str] = "#2A2A32"

    # --- Internal cache ---
    _themes: ClassVar[dict[str, dict[str, str]]] = {}

    # ──────────────────────────────────────────────
    #  Class-level helpers
    # ──────────────────────────────────────────────

    @classmethod
    def as_dict(cls) -> dict[str, str]:
        """Return every colour token as a flat dict keyed by field name."""
        return {
            "BG_BASE": cls.BG_BASE,
            "BG_SURFACE": cls.BG_SURFACE,
            "BG_ELEVATED": cls.BG_ELEVATED,
            "BG_GLASS": cls.BG_GLASS,
            "BG_HOVER": cls.BG_HOVER,
            "BG_ACTIVE": cls.BG_ACTIVE,
            "TEXT_PRIMARY": cls.TEXT_PRIMARY,
            "TEXT_SECONDARY": cls.TEXT_SECONDARY,
            "ACCENT_PRIMARY": cls.ACCENT_PRIMARY,
            "ACCENT_SECONDARY": cls.ACCENT_SECONDARY,
            "DANGER": cls.DANGER,
            "WARNING": cls.WARNING,
            "SUCCESS": cls.SUCCESS,
            "BORDER": cls.BORDER,
        }

    @classmethod
    def register_theme(cls, name: str, overrides: dict[str, str]) -> None:
        """Register a named theme with colour overrides for runtime switching."""
        cls._themes[name] = overrides

    @classmethod
    def get_theme(cls, name: str) -> dict[str, str]:
        """Return the resolved colour dict for a registered theme (or the default)."""
        if name in cls._themes:
            base = cls.as_dict()
            base.update(cls._themes[name])
            return base
        return cls.as_dict()

    @classmethod
    def theme_names(cls) -> list[str]:
        """Return list of registered theme names (excluding the always-available default)."""
        return list(cls._themes.keys())

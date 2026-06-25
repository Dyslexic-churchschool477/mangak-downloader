"""GlassPanel — a frosted-glass effect QFrame with semi-transparent background, border, and shadow."""

from __future__ import annotations

from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QSizePolicy


class GlassPanel(QFrame):
    """A frosted-glass panel with semi-transparent background, rounded corners,
    a subtle border, and an optional drop shadow.

    The glass look is achieved via QSS with ``rgba`` background so that
    content behind the panel is faintly visible.
    """

    def __init__(
        self,
        parent=None,
        *,
        radius: int = 12,
        shadow: bool = True,
        border: bool = True,
    ) -> None:
        super().__init__(parent)
        self._radius = radius
        self._border = border
        self._shadow_enabled = shadow

        self.setObjectName("glassPanel")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # Drop shadow for depth
        if shadow:
            self._setup_shadow()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def set_radius(self, r: int) -> None:
        """Update the border-radius and repaint."""
        self._radius = r
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def set_border_visible(self, visible: bool) -> None:
        """Show / hide the border line."""
        self._border = visible
        self.setProperty("border", "visible" if visible else "hidden")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def set_shadow_enabled(self, enabled: bool) -> None:
        """Toggle the outer drop-shadow effect."""
        self._shadow_enabled = enabled
        if enabled:
            self._setup_shadow()
        else:
            eff = self.graphicsEffect()
            if eff is not None:
                self.setGraphicsEffect(None)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _setup_shadow(self) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(shadow)

    # ------------------------------------------------------------------
    # Paint (ensure rounded corners clip properly)
    # ------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipRect(self.rect())
        painter.end()
        super().paintEvent(event)

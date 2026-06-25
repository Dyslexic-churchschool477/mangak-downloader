"""ProgressRing — a circular arc progress indicator with animated value, label, and gradient stroke."""

from __future__ import annotations

from typing import Union

from PyQt6.QtCore import (
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    pyqtProperty,
)
from PyQt6.QtGui import (
    QColor,
    QConicalGradient,
    QFont,
    QPainter,
    QPaintEvent,
    QPen,
)
from PyQt6.QtWidgets import QWidget


class ProgressRing(QWidget):
    """A circular progress ring with animated arc, gradient stroke, and centre label."""

    def __init__(
        self,
        parent=None,
        *,
        diameter: int = 64,
        stroke_width: int = 4,
    ) -> None:
        super().__init__(parent)
        self._diameter = max(32, diameter)
        self._stroke = max(2, stroke_width)
        self._label = ""
        self._track_color = QColor("#2A2A32")
        self._arc_color_start = QColor("#6C5CE7")
        self._arc_color_end = QColor("#00CEC9")

        self.setFixedSize(self._diameter, self._diameter)
        self.__pv = 0.0  # backing field for pyqtProperty

        self._anim = QPropertyAnimation(self, b"_progress_value", self)
        self._anim.setDuration(400)
        self._anim.setStartValue(0.0)

    # ── Public API ──────────────────────────────────────────────────────

    def set_value(self, v: float, animated: bool = True) -> None:
        v = max(0.0, min(1.0, v))
        if animated:
            self._anim.stop()
            self._anim.setStartValue(self.__pv)
            self._anim.setEndValue(v)
            self._anim.start()
        else:
            self.__pv = v
            self.update()

    def value(self) -> float:
        return self.__pv

    def set_label(self, text: str) -> None:
        self._label = text
        self.update()

    def label(self) -> str:
        return self._label

    def set_track_color(self, color: Union[QColor, str]) -> None:
        self._track_color = QColor(color) if isinstance(color, str) else color
        self.update()

    def set_arc_colors(self, start: Union[QColor, str], end: Union[QColor, str]) -> None:
        self._arc_color_start = QColor(start) if isinstance(start, str) else start
        self._arc_color_end = QColor(end) if isinstance(end, str) else end
        self.update()

    def reset(self) -> None:
        self._anim.stop()
        self.__pv = 0.0
        self.update()

    # ── Qt property (for animation) ─────────────────────────────────────

    def _get_pv(self) -> float:
        return self.__pv

    def _set_pv(self, v: float) -> None:
        self.__pv = v
        self.update()

    _progress_value = pyqtProperty(float, fget=_get_pv, fset=_set_pv)

    # ── Paint ───────────────────────────────────────────────────────────

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        side = min(rect.width(), rect.height())
        if side <= 0:
            painter.end()
            return

        margin = self._stroke // 2 + 1
        arc_rect = QRectF(
            rect.x() + margin,
            rect.y() + margin,
            side - 2 * margin,
            side - 2 * margin,
        )

        # Track ring
        pen = QPen(self._track_color, self._stroke, Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(arc_rect, 0, 360 * 16)

        # Progress arc
        cur_val = self.__pv
        if cur_val > 0.0:
            span = int(360 * cur_val * 16)
            start_angle = 90 * 16  # 12 o'clock

            grad = QConicalGradient(arc_rect.center(), 90)
            grad.setColorAt(0.0, self._arc_color_start)
            grad.setColorAt(1.0, self._arc_color_end)

            pen = QPen(grad, self._stroke, Qt.PenStyle.SolidLine)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawArc(arc_rect, start_angle, -span)

        # Centre percentage text
        pct = f"{int(cur_val * 100)}%"
        font = QFont("Inter")
        font.setPixelSize(max(9, side // 5))
        painter.setFont(font)
        painter.setPen(QColor("#6C5CE7"))
        painter.drawText(arc_rect, Qt.AlignmentFlag.AlignCenter, pct)

        painter.end()

    def sizeHint(self) -> QSize:
        return QSize(self._diameter, self._diameter)

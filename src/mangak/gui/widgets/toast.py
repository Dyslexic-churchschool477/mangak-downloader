"""Toast + ToastManager — non-blocking notification popups with slide-in, auto-dismiss, and fade-out."""

from __future__ import annotations

from enum import Enum, auto

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    pyqtProperty,
)
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class ToastType(Enum):
    SUCCESS = auto()
    ERROR = auto()
    INFO = auto()
    WARNING = auto()


_COLORS: dict[ToastType, tuple[str, str]] = {
    ToastType.SUCCESS: ("#00B894", "rgba(0, 184, 148, 0.10)"),
    ToastType.ERROR:   ("#FF6B6B", "rgba(255, 107, 107, 0.10)"),
    ToastType.INFO:    ("#6C5CE7", "rgba(108, 92, 231, 0.10)"),
    ToastType.WARNING: ("#FDCB6E", "rgba(253, 203, 110, 0.10)"),
}

_ICONS: dict[ToastType, str] = {
    ToastType.SUCCESS: "\u2713",
    ToastType.ERROR:   "\u2715",
    ToastType.INFO:    "\u2139",
    ToastType.WARNING: "\u26A0",
}


class Toast(QFrame):
    """A single toast notification with a coloured left bar, icon, title,
    and message.  Fades in, auto-dismisses, then fades out."""

    def __init__(
        self,
        parent: QWidget,
        title: str,
        message: str = "",
        toast_type: ToastType = ToastType.INFO,
        duration_ms: int = 3000,
    ) -> None:
        super().__init__(parent)
        self._duration = duration_ms
        self._toast_type = toast_type
        self._t_opacity = 1.0

        self.setObjectName("toast")
        self.setFixedWidth(360)
        self.setMinimumHeight(60)
        self.setMaximumHeight(120)

        # Window-floating frame
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Layout
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Left colour bar
        bar = QFrame()
        bar.setFixedWidth(4)
        bar.setStyleSheet(f"background-color: {_COLORS[toast_type][0]}; border-radius: 2px;")
        outer.addWidget(bar)

        # Content
        content = QVBoxLayout()
        content.setContentsMargins(14, 10, 14, 10)
        content.setSpacing(2)

        # Title row (icon + title)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        icon_label = QLabel(_ICONS[toast_type])
        icon_label.setStyleSheet(
            f"color: {_COLORS[toast_type][0]}; font-size: 16px; font-weight: bold; background: transparent;"
        )
        title_row.addWidget(icon_label)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #EAEAF0; font-size: 13px; font-weight: 600; background: transparent;")
        title_row.addWidget(title_lbl, 1)
        content.addLayout(title_row)

        if message:
            msg_lbl = QLabel(message)
            msg_lbl.setWordWrap(True)
            msg_lbl.setStyleSheet("color: #7F7F8A; font-size: 12px; background: transparent;")
            content.addWidget(msg_lbl)

        outer.addLayout(content, 1)

        # Animations
        self._slide_anim = QPropertyAnimation(self, b"_toast_pos", self)
        self._slide_anim.setDuration(300)
        self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._fade_anim = QPropertyAnimation(self, b"_toast_opacity", self)
        self._fade_anim.setDuration(400)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self.close)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._start_fade_out)

    # ── Public ──────────────────────────────────────────────────────────

    def show_toast(self) -> None:
        """Position in top-right of parent, slide in, start dismiss timer."""
        parent_rect = self.parent().rect() if self.parent() else QRect(0, 0, 800, 600)

        self._start_x = parent_rect.right()
        self._end_x = parent_rect.right() - self.width() - 16

        y = 16
        self.setGeometry(self._start_x, y, self.width(), self.height())
        self.show()

        self._slide_anim.setStartValue(float(self._start_x))
        self._slide_anim.setEndValue(float(self._end_x))
        self._slide_anim.start()

        self._timer.start(self._duration)

    # ── Animated properties ─────────────────────────────────────────────

    def _get_toast_pos(self) -> float:
        return float(self.x())

    def _set_toast_pos(self, x: float) -> None:
        self.move(int(x), self.y())

    _toast_pos = pyqtProperty(float, fget=_get_toast_pos, fset=_set_toast_pos)

    def _get_toast_opacity(self) -> float:
        return self._t_opacity

    def _set_toast_opacity(self, o: float) -> None:
        self._t_opacity = o
        self.update()

    _toast_opacity = pyqtProperty(float, fget=_get_toast_opacity, fset=_set_toast_opacity)

    # ── Paint ───────────────────────────────────────────────────────────

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._t_opacity)

        bg_color = QColor(28, 28, 34, 220)
        painter.setBrush(bg_color)
        painter.setPen(QColor(42, 42, 50))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)

        painter.end()

    # ── Internal ────────────────────────────────────────────────────────

    def _start_fade_out(self) -> None:
        self._slide_anim.stop()
        self._fade_anim.start()


class ToastManager:
    """Manages multiple Toast instances anchored to a parent widget.

    Usage::

        tm = ToastManager(window)
        tm.show_toast("Downloaded", "Chapter 1 complete", "success")

    For convenience, ``ToastManager.show_toast_cls(...)`` can also be called
    as a class method — it routes through the last-created default instance.
    """

    _TYPE_MAP: dict[str, ToastType] = {
        "success": ToastType.SUCCESS,
        "error":   ToastType.ERROR,
        "info":    ToastType.INFO,
        "warning": ToastType.WARNING,
    }

    _default_instance: ToastManager | None = None

    def __init__(self, parent_widget: QWidget) -> None:
        self._parent = parent_widget
        self._toasts: list[Toast] = []
        ToastManager._default_instance = self

    def show_toast(
        self,
        title: str,
        message: str = "",
        toast_type: str = "info",
        duration_ms: int = 3000,
    ) -> None:
        """Show a new toast notification."""
        ttype = self._TYPE_MAP.get(toast_type, ToastType.INFO)
        toast = Toast(self._parent, title, message, ttype, duration_ms)
        toast.destroyed.connect(lambda t=toast: self._toasts.remove(t) if t in self._toasts else None)
        self._toasts.append(toast)
        toast.show_toast()

    @classmethod
    def show_toast_cls(
        cls,
        title: str,
        message: str = "",
        toast_type: str = "info",
        duration_ms: int = 3000,
    ) -> None:
        """Class-method convenience wrapper routing through default instance."""
        inst = cls._default_instance
        if inst is not None:
            inst.show_toast(title, message, toast_type, duration_ms)

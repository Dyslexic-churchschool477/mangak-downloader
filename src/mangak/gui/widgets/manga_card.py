"""MangaCard — a cover card widget with hover effects, async image loading, and click signal."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import (
    QObject,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QThread,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPixmap,
)
from PyQt6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QSizePolicy


class CoverLoader(QObject):
    """Worker that downloads a cover image in a background thread."""

    finished = pyqtSignal(object)  # QPixmap or None

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    @pyqtSlot()
    def run(self) -> None:
        import urllib.request

        pixmap = None
        try:
            req = urllib.request.Request(
                self._url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Referer": "https://mangak.io/",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
                pix = QPixmap()
                if pix.loadFromData(data):
                    pixmap = pix.scaled(
                        180, 260,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
        except Exception:
            pass
        self.finished.emit(pixmap)


class MangaCard(QFrame):
    """A manga cover card with hover lift, click signal, and async image loading."""

    clicked_with_slug = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._slug = ""
        self._title = ""
        self._status = ""
        self._rating = 0.0
        self._pixmap = self._make_placeholder()
        self._hovered = False
        self._scale_factor = 1.0
        self._shadow_blur = 16.0
        self._loader_thread: Optional[QThread] = None
        self._loader: Optional[CoverLoader] = None

        self.setObjectName("mangaCard")
        self.setFixedSize(180, 260)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

        self._scale_anim = QPropertyAnimation(self, b"scale_factor", self)
        self._scale_anim.setDuration(200)

        self._shadow_anim = QPropertyAnimation(self, b"shadow_blur", self)
        self._shadow_anim.setDuration(200)

    def set_data(self, slug: str, title: str, cover_url: str = "",
                 status: str = "", rating: float = 0.0) -> None:
        self._slug = slug
        self._title = title
        self._status = status
        self._rating = rating
        self.update()
        if cover_url:
            self._load_cover(cover_url)

    def slug(self) -> str:
        return self._slug

    def _load_cover(self, url: str) -> None:
        # Kill previous thread cleanly
        if self._loader_thread is not None:
            try:
                self._loader_thread.quit()
                self._loader_thread.wait(500)
            except RuntimeError:
                pass
            self._loader_thread = None
            self._loader = None

        self._loader = CoverLoader(url)
        self._loader.finished.connect(self._on_cover_loaded, type=Qt.ConnectionType.QueuedConnection)
        self._loader_thread = QThread(self)
        self._loader.moveToThread(self._loader_thread)
        self._loader_thread.started.connect(self._loader.run)
        self._loader.finished.connect(self._loader_thread.quit)
        self._loader_thread.finished.connect(self._loader.deleteLater)
        self._loader_thread.start()

    def stop_loader(self) -> None:
        """Stop the cover loader thread safely."""
        if self._loader_thread is not None:
            try:
                if self._loader_thread.isRunning():
                    self._loader_thread.quit()
                    self._loader_thread.wait(500)
            except RuntimeError:
                pass
            self._loader_thread = None
            self._loader = None

    @pyqtSlot(object)
    def _on_cover_loaded(self, pixmap: Optional[QPixmap]) -> None:
        if pixmap is not None and not pixmap.isNull():
            self._pixmap = pixmap
        self.update()

    @staticmethod
    def _make_placeholder() -> QPixmap:
        pm = QPixmap(180, 260)
        pm.fill(QColor("#1C1C22"))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = p.pen()
        pen.setColor(QColor("#4A4A55"))
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(QColor("#242430"))
        r = QRectF(40, 60, 100, 140)
        p.drawRoundedRect(r, 6, 6)
        p.setPen(QColor("#6C5CE7"))
        f = QFont("Segoe UI", 24)
        p.setFont(f)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, "📖")
        p.end()
        return pm

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._scale_anim.stop()
        self._scale_anim.setStartValue(1.0)
        self._scale_anim.setEndValue(1.05)
        self._scale_anim.start()
        self._shadow_anim.stop()
        self._shadow_anim.setStartValue(16)
        self._shadow_anim.setEndValue(28)
        self._shadow_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._scale_anim.stop()
        self._scale_anim.setStartValue(1.05)
        self._scale_anim.setEndValue(1.0)
        self._scale_anim.start()
        self._shadow_anim.stop()
        self._shadow_anim.setStartValue(28)
        self._shadow_anim.setEndValue(16)
        self._shadow_anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._slug:
            self.clicked_with_slug.emit(self._slug)
        super().mousePressEvent(event)

    @pyqtProperty(float)
    def scale_factor(self) -> float:
        return self._scale_factor

    @scale_factor.setter
    def scale_factor(self, s: float) -> None:
        self._scale_factor = s
        self.update()

    @pyqtProperty(float)
    def shadow_blur(self) -> float:
        return self._shadow_blur

    @shadow_blur.setter
    def shadow_blur(self, b: float) -> None:
        self._shadow_blur = b
        eff = self.graphicsEffect()
        if isinstance(eff, QGraphicsDropShadowEffect):
            eff.setBlurRadius(b)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w, h = self.width(), self.height()
        scale = self._scale_factor
        if scale != 1.0:
            painter.translate(w / 2, h / 2)
            painter.scale(scale, scale)
            painter.translate(-w / 2, -h / 2)

        clip_path = QPainterPath()
        clip_path.addRoundedRect(0, 0, w, h, 10, 10)
        painter.setClipPath(clip_path)

        # Cover image
        if self._pixmap and not self._pixmap.isNull():
            pw, ph = self._pixmap.width(), self._pixmap.height()
            src = QRect(0, 0, pw, ph)
            if pw / ph > w / h:
                tw = int(ph * w / h)
                src = QRect((pw - tw) // 2, 0, tw, ph)
            else:
                th = int(pw * h / w)
                src = QRect(0, (ph - th) // 2, pw, th)
            painter.drawPixmap(QRect(0, 0, w, h), self._pixmap, src)
        else:
            painter.drawPixmap(QRect(0, 0, 180, 260), self._make_placeholder(), QRect(0, 0, 180, 260))

        # Gradient overlay
        grad = QLinearGradient(0, h * 0.55, 0, h)
        grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad.setColorAt(1.0, QColor(13, 13, 15, 220))
        painter.setBrush(grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, int(h * 0.55), w, int(h * 0.45))

        # Hover border
        if self._hovered:
            pb = painter.pen()
            pb.setColor(QColor(108, 92, 231, 80))
            pb.setWidth(2)
            painter.setPen(pb)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(1, 1, w - 2, h - 2, 10, 10)

        # Title
        tf = QFont("Inter", 11, QFont.Weight.Bold)
        tf.setPixelSize(11)
        painter.setFont(tf)
        painter.setPen(QColor("#EAEAF0"))
        tr = QRect(10, h - 52, w - 20, 36)
        elided = painter.fontMetrics().elidedText(self._title, Qt.TextElideMode.ElideRight, w - 20)
        painter.drawText(tr, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, elided)

        # Status badge
        if self._status:
            sc = {"Ongoing": "#00B894", "Completed": "#6C5CE7", "Hiatus": "#FDCB6E", "Cancelled": "#FF6B6B"}.get(self._status, "#7F7F8A")
            sf = QFont("Inter")
            sf.setPixelSize(9)
            painter.setFont(sf)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(sc))
            bw = painter.fontMetrics().horizontalAdvance(self._status) + 12
            painter.drawRoundedRect(QRect(10, 10, bw, 18), 4, 4)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(QRect(10, 10, bw, 18), Qt.AlignmentFlag.AlignCenter, self._status)

        # Rating
        if self._rating > 0:
            stars = "★" * int(self._rating) + "☆" * (5 - int(self._rating))
            rf = QFont("Inter")
            rf.setPixelSize(9)
            painter.setFont(rf)
            painter.setPen(QColor("#FDCB6E"))
            painter.drawText(10, h - 8, stars)

        painter.end()

    def sizeHint(self) -> QSize:
        return QSize(180, 260)

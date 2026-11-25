"""Stofree branding widgets built from the *original* supplied artwork.

Three supplied images, three jobs (none is recoloured, stretched or redrawn):

* ``logo.png``            - square emblem: loading screen, application/taskbar icon, About.
* ``darkmode_logo.png``   - white wordmark, shown on the dark theme (dashboard header, sidebar).
* ``lightmode_logo.png``  - dark wordmark, shown on the light theme.

Images are scaled with their aspect ratio preserved and their transparency intact.
"""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QBitmap, QColor, QIcon, QPainter, QPixmap, QRegion
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import theme
from ..utils import assets
from ..utils.constants import APP_NAME, APP_SUBTITLE

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICON_MARGIN = 0.04            # transparent breathing room around the emblem inside the icon


def scaled_pixmap(filename: str, width: int, dpr: float = 1.0) -> QPixmap | None:
    """``filename`` scaled to ``width`` logical px, aspect ratio preserved, HiDPI aware."""
    src = assets.load_pixmap(filename)
    if src is None:
        return None
    pm = src.scaledToWidth(max(1, round(width * dpr)), Qt.SmoothTransformation)
    pm.setDevicePixelRatio(dpr)
    return pm


def scaled_logo(width: int, dpr: float = 1.0) -> QPixmap | None:
    """The main logo (emblem) scaled to ``width``."""
    return scaled_pixmap(assets.LOGO_FILE, width, dpr)


class ThemedWordmark(QLabel):
    """The Stofree wordmark that follows the theme: white on dark, dark on light.
    Falls back to plain text (in the theme's text colour) if the image is unavailable."""

    def __init__(self, width: int = 160, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._logo_width = width
        self.has_logo = False
        self.current_file: str | None = None
        self.setAlignment(Qt.AlignCenter)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.apply_theme()

    def apply_theme(self, p: theme.Palette | None = None) -> None:
        p = p or theme.palette()
        filename = assets.themed_logo_file(p.is_dark)
        pm = scaled_pixmap(filename, self._logo_width, self.devicePixelRatioF() or 1.0)
        if pm is None:
            self.has_logo, self.current_file = False, None
            self.setPixmap(QPixmap())
            self.setText(APP_NAME)
            self.setStyleSheet(f"background: transparent; color: {p.text}; "
                               f"font-size: 16pt; font-weight: 700;")
        else:
            self.has_logo, self.current_file = True, filename
            self.setText("")
            self.setStyleSheet("background: transparent;")
            self.setPixmap(pm)


class EmblemBadge(QFrame):
    """The main logo (emblem) on a light rounded plate - it is designed for light backgrounds,
    so the plate keeps its dark outline and lettering readable on the dark theme."""

    def __init__(self, width: int = 150, padding: int = 10, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LogoPlate")
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(padding, padding, padding, padding)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background: transparent;")
        lay.addWidget(self.label)
        pm = scaled_logo(width, self.devicePixelRatioF() or 1.0)
        self.has_logo = pm is not None
        if pm is None:
            self.label.setText(APP_NAME)
            self.label.setStyleSheet("background: transparent; color: #1E1B18; "
                                     "font-weight: 700; font-size: 14pt;")
        else:
            self.label.setPixmap(pm)

    def logo_pixmap(self) -> QPixmap | None:
        return self.label.pixmap() if self.has_logo else None


class BrandHeader(QWidget):
    """Sidebar branding: themed wordmark + subtitle; collapses to the emblem icon."""

    def __init__(self, logo_width: int = 190) -> None:
        super().__init__()
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        self.logo = ThemedWordmark(logo_width)
        col.addWidget(self.logo, 0, Qt.AlignHCenter)
        self.subtitle = QLabel(APP_SUBTITLE)
        self.subtitle.setObjectName("BrandSub")
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setWordWrap(True)
        col.addWidget(self.subtitle)
        self.compact = QLabel()
        self.compact.setAlignment(Qt.AlignCenter)
        icon = app_icon()
        self.has_compact = not icon.isNull()
        if self.has_compact:
            self.compact.setPixmap(icon.pixmap(QSize(40, 40)))
        self.compact.setVisible(False)
        col.addWidget(self.compact)

    def set_collapsed(self, collapsed: bool) -> None:
        self.logo.setVisible(not collapsed)
        self.subtitle.setVisible(not collapsed)
        self.compact.setVisible(collapsed and self.has_compact)

    def apply_theme(self, p: theme.Palette | None = None) -> None:
        self.logo.apply_theme(p)


# --------------------------------------------------------------------------- application icon
@lru_cache(maxsize=1)
def _emblem_content_rect() -> QRect | None:
    """Bounding box of the emblem's non-transparent pixels (to trim empty margins in icons)."""
    src = assets.load_logo()
    if src is None:
        return None
    mask = QBitmap.fromImage(src.toImage().createAlphaMask())
    rect = QRegion(mask).boundingRect()
    return rect if not rect.isEmpty() else QRect(src.rect())


def render_icon_pixmap(size: int, dpr: float = 1.0) -> QPixmap | None:
    """Square, transparent icon image: the emblem (empty margins trimmed, proportions kept)
    centred with a small margin. Returns ``None`` if ``logo.png`` is unavailable."""
    src = assets.load_logo()
    rect = _emblem_content_rect()
    if src is None or rect is None:
        return None
    px = max(1, round(size * dpr))
    out = QPixmap(px, px)
    out.fill(Qt.transparent)
    inner = px * (1 - 2 * ICON_MARGIN)
    scale = inner / max(rect.width(), rect.height())           # one scale for both axes
    w, h = rect.width() * scale, rect.height() * scale
    target = QRectF((px - w) / 2, (px - h) / 2, w, h)
    p = QPainter(out)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    p.drawPixmap(target, src, QRectF(rect))
    p.end()
    out.setDevicePixelRatio(dpr)
    return out


_icon_cache: QIcon | None = None


def app_icon() -> QIcon:
    """Multi-resolution QIcon (window, taskbar). Null if ``logo.png`` is missing."""
    global _icon_cache
    if _icon_cache is None:
        icon = QIcon()
        for s in ICON_SIZES:
            pm = render_icon_pixmap(s)
            if pm is not None:
                icon.addPixmap(pm)
        _icon_cache = icon
    return _icon_cache


def reset_icon_cache() -> None:
    global _icon_cache
    _icon_cache = None
    _emblem_content_rect.cache_clear()

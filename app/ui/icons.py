"""Theme-aware SVG icons rendered from assets/icons."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).resolve().parents[2] / "assets" / "icons"
_cache: dict[tuple[str, str, int], QIcon] = {}


def icon(name: str, color: str = "#FFFFFF", size: int = 20) -> QIcon:
    key = (name, color, size)
    if key in _cache:
        return _cache[key]
    path = ICON_DIR / f"{name}.svg"
    ico = QIcon()
    if path.exists():
        svg = path.read_text(encoding="utf-8").replace("#COLOR", color)
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        for scale in (1, 2):
            px = size * scale
            img = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
            img.fill(Qt.transparent)
            painter = QPainter(img)
            renderer.render(painter)
            painter.end()
            pm = QPixmap.fromImage(img)
            pm.setDevicePixelRatio(scale)
            ico.addPixmap(pm)
    _cache[key] = ico
    return ico

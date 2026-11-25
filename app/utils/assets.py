"""Asset path resolution and safe image loading.

Works in three situations without any hard-coded absolute paths:

* development (assets live next to the ``app`` package),
* PyInstaller one-folder / one-file builds (``sys._MEIPASS``),
* an explicit override via the ``STOFREE_ASSETS`` environment variable.

Every loader returns ``None`` instead of raising when an asset is missing or corrupt, so
callers can fall back gracefully.
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from .logger import get_logger

log = get_logger("assets")

LOGO_FILE = "logo.png"                      # square emblem: loading screen + main brand identity
LOGO_DARK_FILE = "darkmode_logo.png"        # white wordmark, for the dark theme
LOGO_LIGHT_FILE = "lightmode_logo.png"      # dark wordmark, for the light theme
SPLASH_GIF_FILE = "Ani.gif"
ICON_FILE = "stofree.ico"


def base_dir() -> Path:
    """Root directory that contains the ``assets`` folder."""
    override = os.environ.get("STOFREE_ASSETS")
    if override:
        return Path(override).parent if Path(override).name == "assets" else Path(override)
    frozen_root = getattr(sys, "_MEIPASS", None)          # set by PyInstaller
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[2]


def asset_path(*parts: str) -> Path:
    """Path of an asset below ``assets/`` (existence is not checked)."""
    return base_dir().joinpath("assets", *parts)


def existing_asset(*parts: str) -> Path | None:
    p = asset_path(*parts)
    if p.is_file():
        return p
    log.warning("Asset not found: %s", p)
    return None


def branding_path(filename: str) -> Path | None:
    return existing_asset("branding", filename)


# ---------------------------------------------------------------- Qt loaders (lazy imports)
@lru_cache(maxsize=8)
def load_pixmap(filename: str):
    """Load ``assets/branding/<filename>`` as a QPixmap, or ``None`` if missing/invalid."""
    from PySide6.QtGui import QPixmap

    path = branding_path(filename)
    if path is None:
        return None
    pm = QPixmap(str(path))
    if pm.isNull():
        log.warning("Could not decode image: %s", path)
        return None
    return pm


def load_logo():
    """The main logo (square emblem) as a QPixmap, or ``None``."""
    return load_pixmap(LOGO_FILE)


def themed_logo_file(is_dark: bool) -> str:
    """Wordmark file to use for the given theme."""
    return LOGO_DARK_FILE if is_dark else LOGO_LIGHT_FILE


def load_themed_logo(is_dark: bool):
    """Dark-mode or light-mode wordmark as a QPixmap, or ``None``."""
    return load_pixmap(themed_logo_file(is_dark))


def logo_aspect_ratio(filename: str = LOGO_FILE, default: float = 1.0) -> float:
    """width / height of a branding image; used to size it without distortion."""
    pm = load_pixmap(filename)
    return pm.width() / pm.height() if pm is not None and pm.height() else default

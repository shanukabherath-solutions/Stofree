"""Per-user data locations.

Everything Stofree writes (settings, logs) lives under ``%LOCALAPPDATA%\\Stofree``. Nothing is
ever written next to the executable (``C:\\Program Files`` is read-only for normal users) or
inside PyInstaller's temporary extraction folder (``sys._MEIPASS``, deleted on exit in
one-file builds). Reports are only written where the user explicitly chooses to save them.
"""
from __future__ import annotations

import os
from pathlib import Path

from .constants import APP_NAME

SETTINGS_FILE_NAME = "settings.ini"
LOG_DIR_NAME = "logs"


def user_data_dir() -> Path:
    """``%LOCALAPPDATA%\\Stofree`` (``~/.local/share/Stofree`` on non-Windows dev machines)."""
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / APP_NAME.replace(" ", "")


def settings_file() -> Path:
    return user_data_dir() / SETTINGS_FILE_NAME


def log_dir() -> Path:
    return user_data_dir() / LOG_DIR_NAME

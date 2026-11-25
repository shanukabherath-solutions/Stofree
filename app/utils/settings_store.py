"""Persistent user settings stored as an INI file in ``%LOCALAPPDATA%\\Stofree``.

Earlier development builds used ``QSettings(org, app)`` which, on Windows, writes to the
registry. Settings now live in ``settings.ini`` so they are easy to find, back up or delete,
and the uninstaller can offer to remove them. On first run, any values left by an older build
are copied over once (the old location is only read, never modified).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from .constants import APP_NAME, APP_ORG
from .logger import get_logger
from .paths import settings_file

log = get_logger("settings")


def _migrate_legacy(target: QSettings) -> int:
    """Copy keys from the old native-format settings into ``target`` if it is still empty."""
    if target.allKeys():
        return 0
    legacy = QSettings(APP_ORG, APP_NAME)           # registry on Windows; read-only use
    keys = legacy.allKeys()
    for key in keys:
        target.setValue(key, legacy.value(key))
    if keys:
        target.sync()
        log.info("Migrated %d setting(s) from the previous settings location", len(keys))
    return len(keys)


def create_settings(path: Path | str | None = None, migrate: bool = True) -> QSettings:
    """Open (and create the folder for) the INI settings file. Never raises."""
    ini = Path(path) if path else settings_file()
    try:
        ini.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        log.warning("Could not create the settings folder %s", ini.parent, exc_info=True)
    settings = QSettings(str(ini), QSettings.IniFormat)
    if migrate and path is None:
        try:
            _migrate_legacy(settings)
        except Exception:  # noqa: BLE001 - a failed migration must never block start-up
            log.warning("Settings migration failed", exc_info=True)
    return settings

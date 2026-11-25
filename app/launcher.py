"""Start-up orchestration: splash screen -> main window.

The splash is created exactly once, in ``main()``. Nothing in the navigation code can
re-create it, and ``Launcher`` guards against revealing the window twice.
"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QObject, QTimer

from .main_window import MainWindow
from .ui.splash import StartupSplash
from .utils.constants import APP_ID
from .utils.logger import get_logger

log = get_logger("launcher")

READY_TIMEOUT_MS = 8000        # open the window even if drive detection is slow


def set_windows_app_id(app_id: str = APP_ID) -> bool:
    """Give the process its own taskbar identity so Windows shows the Stofree icon
    (and groups windows under it) instead of the Python interpreter's. No-op elsewhere."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)  # type: ignore[attr-defined]
        return True
    except Exception:  # noqa: BLE001 - purely cosmetic
        log.warning("Could not set the Windows AppUserModelID", exc_info=True)
        return False


def splash_enabled(no_splash_flag: bool = False) -> bool:
    return not (no_splash_flag or os.environ.get("STOFREE_NO_SPLASH"))


class Launcher(QObject):
    """Shows the main window once drives are known *and* the splash has played long enough."""

    def __init__(self, window: MainWindow, splash: StartupSplash | None,
                 timeout_ms: int = READY_TIMEOUT_MS) -> None:
        super().__init__(window)
        self.window = window
        self.splash = splash
        self.revealed = False
        self._ready_called = False
        window.state.drives_changed.connect(self._on_ready)
        QTimer.singleShot(timeout_ms, self._on_ready)

    def start(self) -> None:
        if self.splash is not None:
            self.splash.set_status("Detecting drives...")
        self.window.state.refresh_drives_async()      # worker thread; GUI stays responsive

    def _on_ready(self) -> None:
        if self._ready_called:
            return
        self._ready_called = True
        if self.splash is None:
            self._reveal()
            return
        self.splash.set_status("Opening dashboard...")
        self.splash.finished.connect(self._reveal)
        self.splash.finish()

    def _reveal(self) -> None:
        if self.revealed:
            return
        self.revealed = True
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        log.info("Main window shown")

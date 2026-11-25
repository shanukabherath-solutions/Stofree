"""Detects drives off the GUI thread (a disconnected network share can stall for seconds)."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..core.drive_manager import list_drives
from ..utils.logger import get_logger

log = get_logger("drives")


class DriveWorker(QThread):
    drives_ready = Signal(object)        # list[DriveInfo]

    def __init__(self, include_removable: bool, parent=None) -> None:
        super().__init__(parent)
        self._include_removable = include_removable

    def run(self) -> None:
        try:
            drives = list_drives(include_removable=self._include_removable)
        except Exception:  # noqa: BLE001 - never let detection kill start-up
            log.exception("Drive detection failed")
            drives = []
        self.drives_ready.emit(drives)

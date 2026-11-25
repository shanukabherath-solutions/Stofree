"""Background scanning thread. The scan never runs on the GUI thread."""
from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal

from ..core.disk_scanner import DiskScanner
from ..utils.logger import get_logger

log = get_logger("worker")


class ScanWorker(QThread):
    progress = Signal(object)        # ScanProgress
    scan_done = Signal(object)       # ScanResult (may be flagged cancelled)
    scan_failed = Signal(str)

    def __init__(self, root: str, top_files_limit: int, parent=None) -> None:
        super().__init__(parent)
        self.root = root
        self._cancel = threading.Event()
        self._scanner = DiskScanner(top_files_limit=top_files_limit)

    def cancel(self) -> None:
        """Request cancellation; traversal stops before the next filesystem entry."""
        self._cancel.set()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()

    def run(self) -> None:  # executed in the worker thread
        try:
            result = self._scanner.scan(self.root, self.progress.emit, self._cancel)
        except Exception as exc:  # noqa: BLE001 - report any failure to the UI
            log.exception("Scan failed for %s", self.root)
            self.scan_failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.scan_done.emit(result)

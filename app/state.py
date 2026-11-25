"""Shared application state: drives, current scan, settings. Pages observe its signals."""
from __future__ import annotations

import json
import os

from PySide6.QtCore import QObject, QSettings, Signal

from .core.disk_scanner import ScanResult
from .core.drive_manager import DriveInfo, list_drives
from .utils.constants import DEFAULT_TOP_FILES
from .utils.logger import get_logger
from .utils.settings_store import create_settings
from .workers.drive_worker import DriveWorker
from .workers.scan_worker import ScanWorker

log = get_logger("state")


class AppState(QObject):
    drives_changed = Signal()
    selected_changed = Signal(str)
    scan_started = Signal(str)
    scan_progress = Signal(object)
    scan_finished = Signal(object)       # ScanResult
    scan_failed = Signal(str)
    last_scans_changed = Signal()
    theme_changed = Signal(str)
    settings_changed = Signal()

    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        self.settings = settings or create_settings()
        self.drives: list[DriveInfo] = []
        self.selected_root: str | None = None
        self.result: ScanResult | None = None
        self.scanning = False
        self._worker: ScanWorker | None = None
        self._drive_worker: DriveWorker | None = None
        self.last_scans: dict[str, dict] = self._load_last_scans()

    # ------------------------------------------------------------------ settings
    @property
    def theme(self) -> str:
        return str(self.settings.value("theme", "dark"))

    def set_theme(self, name: str) -> None:
        self.settings.setValue("theme", name)
        self.theme_changed.emit(name)

    @property
    def top_files_limit(self) -> int:
        return int(self.settings.value("top_files_limit", DEFAULT_TOP_FILES))

    @property
    def export_depth(self) -> int:
        return int(self.settings.value("export_depth", 4))

    @property
    def include_removable(self) -> bool:
        return str(self.settings.value("include_removable", "true")).lower() == "true"

    @property
    def animations(self) -> bool:
        return str(self.settings.value("animations", "true")).lower() == "true"

    def set_value(self, key: str, value) -> None:
        self.settings.setValue(key, value)
        self.settings_changed.emit()

    # ------------------------------------------------------------------ drives
    def refresh_drives(self) -> None:
        """Detect drives synchronously (blocks until done)."""
        self._set_drives(list_drives(include_removable=self.include_removable))

    def refresh_drives_async(self) -> None:
        """Detect drives on a worker thread; ``drives_changed`` fires when finished."""
        if self._drive_worker is not None and self._drive_worker.isRunning():
            return
        worker = DriveWorker(self.include_removable)
        worker.drives_ready.connect(self._set_drives)
        worker.finished.connect(lambda w=worker: self._drive_worker_done(w))
        self._drive_worker = worker
        worker.start()

    def _drive_worker_done(self, worker: DriveWorker) -> None:
        if self._drive_worker is worker:
            self._drive_worker = None
        worker.deleteLater()

    def _set_drives(self, drives: list[DriveInfo]) -> None:
        self.drives = drives
        mounts = {d.mountpoint for d in self.drives}
        custom_ok = self.scanning or (
            self.result is not None and self.selected_root == self.result.root_path)
        if self.selected_root not in mounts and not custom_ok:
            self.selected_root = self.drives[0].mountpoint if self.drives else None
        self.drives_changed.emit()

    def select(self, root: str) -> None:
        if root != self.selected_root:
            self.selected_root = root
            self.selected_changed.emit(root)

    def drive_for(self, root: str | None) -> DriveInfo | None:
        """Drive that contains ``root`` (exact mount point or the longest matching prefix)."""
        if not root:
            return None
        key = os.path.normcase(root)
        best: DriveInfo | None = None
        for d in self.drives:
            mp = os.path.normcase(d.mountpoint)
            if key == mp:
                return d
            if key.startswith(mp) and (best is None or len(mp) > len(os.path.normcase(best.mountpoint))):
                best = d
        return best

    # ------------------------------------------------------------------ last scan info
    def _load_last_scans(self) -> dict[str, dict]:
        try:
            raw = self.settings.value("last_scans", "{}")
            if isinstance(raw, (list, tuple)):      # INI files split unquoted commas into a list
                raw = ",".join(str(x) for x in raw)
            data = json.loads(str(raw))
            return data if isinstance(data, dict) else {}
        except (ValueError, TypeError):
            return {}

    def _remember(self, r: ScanResult) -> None:
        self.last_scans[r.root_path] = {
            "timestamp": r.started_at.isoformat(timespec="seconds"),
            "files": r.total_files, "folders": r.total_folders, "bytes": r.total_size,
            "duration": round(r.duration, 1), "cancelled": r.cancelled, "errors": r.error_count,
        }
        self.settings.setValue("last_scans", json.dumps(self.last_scans))
        self.last_scans_changed.emit()

    # ------------------------------------------------------------------ scanning
    def start_scan(self, root: str) -> bool:
        if self.scanning:
            return False
        self.scanning = True
        self.select(root)
        worker = ScanWorker(root, self.top_files_limit)
        worker.progress.connect(self.scan_progress)
        worker.scan_done.connect(self._on_done)
        worker.scan_failed.connect(self._on_failed)
        worker.finished.connect(lambda w=worker: self._on_thread_finished(w))
        self._worker = worker
        self.scan_started.emit(root)
        worker.start()
        return True

    def cancel_scan(self) -> None:
        if self._worker is not None and self.scanning:
            self._worker.cancel()

    def wait_for_scan(self, timeout_ms: int = 5000) -> None:
        """Cancel any running scan and wait for the thread (used on application exit)."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(timeout_ms)
        if self._drive_worker is not None and self._drive_worker.isRunning():
            self._drive_worker.wait(timeout_ms)

    def _on_done(self, result: ScanResult) -> None:
        self.scanning = False
        self.result = result
        self._remember(result)
        self.scan_finished.emit(result)

    def _on_failed(self, message: str) -> None:
        self.scanning = False
        self.scan_failed.emit(message)

    def _on_thread_finished(self, worker: ScanWorker) -> None:
        # Bound to the specific worker so a newer scan's worker is never touched.
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()

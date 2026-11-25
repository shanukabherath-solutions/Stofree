"""Drive Scanner page: choose a drive/folder, start, monitor and cancel a scan."""
from __future__ import annotations

import os
import time

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from .. import theme
from ..core.disk_scanner import ScanProgress, ScanResult
from ..state import AppState
from ..utils.formatters import format_count, format_duration, format_size
from .icons import icon
from .widgets import Card, ElidedLabel, PageHeader, StatTile, make_label, set_role, set_variant


class ScannerPage(QWidget):
    scan_finished = Signal()

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.state = state
        self._t0 = 0.0
        self._expected_bytes = 0
        self._busy = False

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(16)
        root.addWidget(PageHeader("Drive Scanner",
                                  "Scan a drive or folder to see what is using your disk space"))

        # ---- controls
        ctl = Card()
        cl = QHBoxLayout(ctl)
        cl.setContentsMargins(18, 14, 18, 14)
        cl.setSpacing(10)
        cl.addWidget(make_label("Location", "muted"))
        self.combo = QComboBox()
        self.combo.setMinimumWidth(280)
        self.combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        cl.addWidget(self.combo, 1)
        self.refresh_btn = QPushButton()
        self.refresh_btn.setToolTip("Re-detect drives")
        self.refresh_btn.clicked.connect(lambda: self.state.refresh_drives_async())
        cl.addWidget(self.refresh_btn)
        self.folder_btn = QPushButton("Scan folder...")
        self.folder_btn.clicked.connect(self._choose_folder)
        cl.addWidget(self.folder_btn)
        self.start_btn = QPushButton(" Start scan")
        set_variant(self.start_btn, "primary")
        self.start_btn.clicked.connect(self._start)
        cl.addWidget(self.start_btn)
        self.cancel_btn = QPushButton(" Cancel")
        set_variant(self.cancel_btn, "danger")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        cl.addWidget(self.cancel_btn)
        root.addWidget(ctl)

        # ---- progress
        pc = Card()
        pl = QVBoxLayout(pc)
        pl.setContentsMargins(18, 16, 18, 16)
        pl.setSpacing(8)
        self.status = make_label("Ready. Choose a drive and press Start scan.", "h2")
        pl.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        pl.addWidget(self.progress)
        row = QHBoxLayout()
        row.addWidget(make_label("Current folder:", "muted"))
        self.current = ElidedLabel("-")
        row.addWidget(self.current, 1)
        pl.addLayout(row)
        self.note = make_label("", "muted", wrap=True)
        pl.addWidget(self.note)
        root.addWidget(pc)

        # ---- stats
        grid = QGridLayout()
        grid.setSpacing(12)
        self.tiles = {name: StatTile(name) for name in
                      ("Files scanned", "Folders scanned", "Data scanned", "Access errors",
                       "Elapsed", "Speed (files/s)")}
        for i, t in enumerate(self.tiles.values()):
            grid.addWidget(t, i // 3, i % 3)
            grid.setColumnStretch(i % 3, 1)
        root.addLayout(grid)

        # ---- log
        root.addWidget(make_label("Skipped items and errors", "h2"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Permission errors and skipped links/junctions appear here after a scan.")
        self.log.setMinimumHeight(110)
        root.addWidget(self.log, 1)

        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._tick)

        s = self.state
        s.drives_changed.connect(self._fill_combo)
        s.selected_changed.connect(self._sync_selection)
        s.scan_started.connect(self._on_started)
        s.scan_progress.connect(self._on_progress)
        s.scan_finished.connect(self._on_finished)
        s.scan_failed.connect(self._on_failed)
        self.combo.currentIndexChanged.connect(self._combo_changed)
        self._fill_combo()
        self.apply_theme()

    # ---------------------------------------------------------------- combo handling
    def _fill_combo(self) -> None:
        self.combo.blockSignals(True)
        self.combo.clear()
        for d in self.state.drives:
            self.combo.addItem(f"{d.display_name}   -   {d.percent_used:.0f}% used of {format_size(d.total)}",
                               d.mountpoint)
        sel = self.state.selected_root
        if sel and self.combo.findData(sel) < 0:          # custom folder
            self.combo.addItem(sel, sel)
        idx = self.combo.findData(sel) if sel else -1
        self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)
        self._update_buttons()

    def _sync_selection(self, root: str) -> None:
        if self.combo.findData(root) < 0:
            self.combo.addItem(root, root)
        self.combo.blockSignals(True)
        self.combo.setCurrentIndex(self.combo.findData(root))
        self.combo.blockSignals(False)

    def _combo_changed(self, _i: int) -> None:
        root = self.combo.currentData()
        if root:
            self.state.select(root)

    def _choose_folder(self) -> None:
        start = self.state.selected_root or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, "Choose a folder to scan", start)
        if path:
            path = os.path.normpath(path)
            if self.combo.findData(path) < 0:
                self.combo.addItem(path, path)
            self.combo.setCurrentIndex(self.combo.findData(path))
            self._start()

    # ---------------------------------------------------------------- start / cancel
    def _update_buttons(self) -> None:
        self.start_btn.setEnabled(not self._busy and self.combo.currentData() is not None)
        for w in (self.combo, self.refresh_btn, self.folder_btn):
            w.setEnabled(not self._busy)
        self.cancel_btn.setEnabled(self._busy)

    def _start(self) -> None:
        root = self.combo.currentData()
        if not root or self._busy:
            return
        if not os.path.isdir(root):
            QMessageBox.warning(self, "Location unavailable", f"'{root}' is not accessible.")
            return
        self.state.start_scan(root)

    def start_scan_for(self, root: str) -> None:
        """Called by other pages (dashboard) to begin a scan of a given location."""
        if self.combo.findData(root) < 0:
            self.combo.addItem(root, root)
        self.combo.setCurrentIndex(self.combo.findData(root))
        self._start()

    def _cancel(self) -> None:
        self.cancel_btn.setEnabled(False)
        self.status.setText("Cancelling... finishing the current directory listing")
        self.state.cancel_scan()

    # ---------------------------------------------------------------- state callbacks
    def _on_started(self, root: str) -> None:
        self._busy = True
        self._t0 = time.monotonic()
        drive = self.state.drive_for(root)
        is_whole_drive = drive is not None and os.path.normcase(drive.mountpoint) == os.path.normcase(root)
        self._expected_bytes = drive.used if is_whole_drive else 0
        self.progress.setRange(0, 1000 if self._expected_bytes else 0)   # 0,0 -> busy indicator
        self.progress.setValue(0)
        self.status.setText(f"Scanning {root}")
        self.note.setText("Progress is estimated from the drive's used space; the scan only reads "
                          "file metadata, never file contents." if self._expected_bytes
                          else "Scanning a folder - total size is unknown, so progress is indeterminate.")
        self.log.clear()
        for t in self.tiles.values():
            t.set_value("0")
        self.tiles["Data scanned"].set_value("0 B")
        self._update_buttons()
        self.timer.start()

    def _on_progress(self, p: ScanProgress) -> None:
        self.tiles["Files scanned"].set_value(format_count(p.files))
        self.tiles["Folders scanned"].set_value(format_count(p.folders))
        self.tiles["Data scanned"].set_value(format_size(p.bytes_scanned))
        self.tiles["Access errors"].set_value(format_count(p.errors))
        self.tiles["Speed (files/s)"].set_value(format_count(int(p.files / p.elapsed)) if p.elapsed > 0.2 else "-")
        self.current.setText(p.current_dir)
        if self._expected_bytes:
            est = min(990, int(p.bytes_scanned / self._expected_bytes * 1000))
            self.progress.setValue(est)
            self.status.setText(f"Scanning... about {est / 10:.0f}% (estimate)")

    def _tick(self) -> None:
        self.tiles["Elapsed"].set_value(format_duration(time.monotonic() - self._t0))

    def _finish_ui(self) -> None:
        self._busy = False
        self.timer.stop()
        self._update_buttons()

    def _on_finished(self, r: ScanResult) -> None:
        self._finish_ui()
        self._on_progress(ScanProgress(r.total_files, r.total_folders, r.total_size, r.root_path,
                                       r.error_count, r.duration))
        self.tiles["Elapsed"].set_value(format_duration(r.duration))
        self.current.setText(r.root_path)
        if r.cancelled:
            self.status.setText("Scan cancelled - partial results are available")
            self.note.setText("Totals reflect only what was scanned before cancelling.")
            self.progress.setRange(0, 1000)
        else:
            self.status.setText(f"Scan complete in {format_duration(r.duration)}")
            self.note.setText("Results are available in Largest Files, Folder Explorer, File Types and Reports.")
            self.progress.setRange(0, 1000)
            self.progress.setValue(1000)
        lines = []
        if r.skipped_links:
            lines.append(f"[info] {format_count(r.skipped_links)} symbolic links / junctions / reparse points "
                         "were skipped (never followed).")
            lines += [f"  skipped: {p}" for p in r.skipped_samples[:20]]
        if r.error_count:
            lines.append(f"[warn] {format_count(r.error_count)} items could not be read "
                         f"(showing first {len(r.errors)}):")
            lines += [f"  {e}" for e in r.errors]
        self.log.setPlainText("\n".join(lines) if lines else "No errors. No links were skipped.")
        self.scan_finished.emit()

    def _on_failed(self, message: str) -> None:
        self._finish_ui()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.status.setText("Scan failed")
        self.note.setText(message)
        self.log.setPlainText(message)

    def apply_theme(self, _p=None) -> None:
        p = theme.palette()
        self.refresh_btn.setIcon(icon("refresh", p.text, 18))
        self.start_btn.setIcon(icon("play", "#FFFFFF", 16))
        self.cancel_btn.setIcon(icon("stop", p.danger, 16))

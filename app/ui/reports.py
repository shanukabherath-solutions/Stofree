"""Reports page: export scan results to CSV / JSON."""
from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog, QGridLayout, QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from ..core import report_generator as rg
from ..core.disk_scanner import ScanResult
from ..state import AppState
from ..utils.constants import APP_FILE_PREFIX
from ..utils.formatters import format_count, format_size, format_timestamp
from ..utils.logger import get_logger
from .icons import icon
from .widgets import Card, ChoiceBox, PageHeader, make_label, set_variant

log = get_logger("reports")


class ReportsPage(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.state = state
        self._last_path: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(16)
        root.addWidget(PageHeader("Reports", "Export the results of the last scan"))

        self.summary_card = Card()
        sl = QVBoxLayout(self.summary_card)
        sl.setContentsMargins(18, 16, 18, 16)
        sl.addWidget(make_label("Scan to export", "h2"))
        self.summary = make_label("No scan results yet. Run a scan first.", "muted", wrap=True)
        sl.addWidget(self.summary)
        root.addWidget(self.summary_card)

        opt = Card()
        ol = QGridLayout(opt)
        ol.setContentsMargins(18, 16, 18, 16)
        ol.setHorizontalSpacing(14)
        ol.setVerticalSpacing(10)
        ol.addWidget(make_label("Options", "h2"), 0, 0, 1, 3)
        ol.addWidget(make_label("Folder levels to include (folders CSV / JSON)", "muted"), 1, 0)
        self.depth = ChoiceBox([("All levels", 0)] + [(f"{n} level{'s' if n > 1 else ''}", n)
                                                      for n in (1, 2, 3, 4, 5, 6, 8, 10)])
        self.depth.setValue(state.export_depth)
        ol.addWidget(self.depth, 1, 1)
        ol.addWidget(make_label("Files to include (largest first)", "muted"), 2, 0)
        self.max_files = ChoiceBox([("All retained files", 0)] + [(f"Top {n:,}", n)
                                                                  for n in (100, 500, 1000, 5000, 10000)])
        ol.addWidget(self.max_files, 2, 1)
        ol.setColumnStretch(2, 1)
        root.addWidget(opt)

        btns = Card()
        bl = QHBoxLayout(btns)
        bl.setContentsMargins(18, 16, 18, 16)
        bl.setSpacing(10)
        self.files_btn = QPushButton(" Export files (CSV)")
        self.folders_btn = QPushButton(" Export folders (CSV)")
        self.json_btn = QPushButton(" Export full report (JSON)")
        set_variant(self.json_btn, "primary")
        for b in (self.files_btn, self.folders_btn, self.json_btn):
            b.setEnabled(False)
            bl.addWidget(b)
        bl.addStretch(1)
        root.addWidget(btns)

        row = QHBoxLayout()
        self.status = make_label("", "muted", wrap=True)
        row.addWidget(self.status, 1)
        self.open_btn = QPushButton("Show in folder")
        self.open_btn.setVisible(False)
        self.open_btn.clicked.connect(self._open_location)
        row.addWidget(self.open_btn)
        root.addLayout(row)
        root.addStretch(1)

        self.files_btn.clicked.connect(self._export_files)
        self.folders_btn.clicked.connect(self._export_folders)
        self.json_btn.clicked.connect(self._export_json)
        self.state.scan_finished.connect(self.set_result)
        self.apply_theme()
        if state.result:
            self.set_result(state.result)

    # ------------------------------------------------------------------ helpers
    def set_result(self, r: ScanResult) -> None:
        self.summary.setText(
            f"{r.root_path}\nScanned {format_timestamp(r.started_at)}  -  {format_count(r.total_files)} files, "
            f"{format_count(r.total_folders)} folders, {format_size(r.total_size)}"
            + ("  -  PARTIAL (scan was cancelled)" if r.cancelled else ""))
        for b in (self.files_btn, self.folders_btn, self.json_btn):
            b.setEnabled(True)

    def _default_name(self, kind: str, ext: str) -> str:
        r = self.state.result
        tag = "".join(ch for ch in (r.drive if r else "scan") if ch.isalnum()) or "scan"
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        return os.path.join(os.path.expanduser("~"), f"{APP_FILE_PREFIX}_{kind}_{tag}_{stamp}.{ext}")

    def _ask_path(self, kind: str, ext: str, filt: str) -> str | None:
        path, _ = QFileDialog.getSaveFileName(self, "Save report", self._default_name(kind, ext), filt)
        return path or None

    def _depth(self) -> int | None:
        return self.depth.value() or None

    def _run(self, kind: str, ext: str, filt: str, fn) -> None:
        r = self.state.result
        if r is None:
            return
        path = self._ask_path(kind, ext, filt)
        if not path:
            return
        try:
            count = fn(r, path)
        except OSError as exc:
            log.error("Export failed: %s", exc)
            QMessageBox.critical(self, "Export failed", f"Could not write the report:\n{exc}")
            self.status.setText("Export failed.")
            return
        self._last_path = path
        what = f"{format_count(count)} rows" if isinstance(count, int) else "full report"
        self.status.setText(f"Saved {what} to {path}")
        self.open_btn.setVisible(True)
        log.info("Exported %s to %s", kind, path)

    def _export_files(self) -> None:
        self._run("files", "csv", "CSV files (*.csv)",
                  lambda r, p: rg.export_files_csv(r, p, self.max_files.value() or None))

    def _export_folders(self) -> None:
        self._run("folders", "csv", "CSV files (*.csv)",
                  lambda r, p: rg.export_folders_csv(r, p, self._depth()))

    def _export_json(self) -> None:
        def go(r, p):
            rg.export_json(r, p, self._depth(), self.max_files.value() or None)
        self._run("report", "json", "JSON files (*.json)", go)

    def _open_location(self) -> None:
        if self._last_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self._last_path)))

    def apply_theme(self, _p=None) -> None:
        from .. import theme
        ic = icon("export", theme.palette().text, 18)
        self.files_btn.setIcon(ic)
        self.folders_btn.setIcon(ic)
        self.json_btn.setIcon(icon("export", "#FFFFFF", 18))

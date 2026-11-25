"""Dashboard: drive overview cards, usage donut and last-scan information."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .. import theme
from ..core.drive_manager import DriveInfo
from ..state import AppState
from ..utils.formatters import (
    format_count, format_duration, format_size, format_timestamp,
)
from .icons import icon
from .branding import ThemedWordmark
from .widgets import Card, PageHeader, PieChartWidget, UsageBar, make_label, set_variant

CARD_MIN_WIDTH = 330


class DriveCard(QFrame):
    clicked = Signal(str)
    scan_requested = Signal(str)

    def __init__(self, drive: DriveInfo) -> None:
        super().__init__()
        self.drive = drive
        self.setObjectName("DriveCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("selected", False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(8)

        top = QHBoxLayout()
        self.icon_label = QLabel()
        top.addWidget(self.icon_label)
        name = make_label(drive.display_name, "h2")
        top.addWidget(name, 1)
        kind_text = drive.fstype or "Drive"
        if drive.kind != "unknown":
            kind_text += f" - {drive.kind}"
        kind = make_label(kind_text, "muted")
        top.addWidget(kind)
        lay.addLayout(top)

        row = QHBoxLayout()
        self.pct = make_label(f"{drive.percent_used:.0f}%", "pct")
        row.addWidget(self.pct)
        row.addWidget(make_label("used", "muted"), 0, Qt.AlignBottom)
        row.addStretch(1)
        lay.addLayout(row)

        self.bar = UsageBar(10)
        self.bar.set_value(drive.percent_used)
        lay.addWidget(self.bar)

        figs = QHBoxLayout()
        for caption, value in (("Used", drive.used), ("Free", drive.free), ("Total", drive.total)):
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(make_label(format_size(value), "h2"))
            col.addWidget(make_label(caption, "statcaption"))
            figs.addLayout(col)
        lay.addLayout(figs)

        self.last_scan = make_label("Last scan: never", "muted", wrap=True)
        lay.addWidget(self.last_scan)

        self.scan_btn = QPushButton(" Scan this drive")
        set_variant(self.scan_btn, "primary")
        self.scan_btn.clicked.connect(lambda: self.scan_requested.emit(self.drive.mountpoint))
        lay.addWidget(self.scan_btn)
        self.apply_theme()

    def apply_theme(self) -> None:
        self.icon_label.setPixmap(icon("drive", theme.palette().accent, 24).pixmap(24, 24))
        self.scan_btn.setIcon(icon("play", "#FFFFFF", 16))
        self.bar.update()

    def set_selected(self, flag: bool) -> None:
        self.setProperty("selected", flag)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_last_scan(self, info: dict | None) -> None:
        if not info:
            self.last_scan.setText("Last scan: never")
            return
        ts = format_timestamp(datetime.fromisoformat(info["timestamp"]))
        partial = " (partial)" if info.get("cancelled") else ""
        self.last_scan.setText(f"Last scan: {ts}{partial} - {format_count(info['files'])} files")

    def set_busy(self, busy: bool) -> None:
        self.scan_btn.setEnabled(not busy)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.drive.mountpoint)
        super().mousePressEvent(e)


class DashboardPage(QWidget):
    scan_requested = Signal(str)

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.state = state
        self.cards: list[DriveCard] = []
        self._cols = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 16)
        outer.setSpacing(16)
        header = PageHeader("Dashboard", "Storage overview of your drives")
        self.brand_logo = ThemedWordmark(width=150)   # darkmode_logo.png / lightmode_logo.png by theme
        self.brand_logo.setContentsMargins(0, 0, 16, 0)       # breathing room before Refresh
        header.add_action(self.brand_logo)
        self.refresh_btn = QPushButton(" Refresh")
        self.refresh_btn.clicked.connect(lambda: self.state.refresh_drives_async())
        header.add_action(self.refresh_btn)
        outer.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body.setObjectName("Page")
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(0, 0, 8, 0)
        self.body_layout.setSpacing(16)

        self.empty_label = make_label("No drives detected.", "muted")
        self.empty_label.setVisible(False)
        self.body_layout.addWidget(self.empty_label)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(16)
        self.body_layout.addWidget(self.grid_host)

        # donut + last scan
        lower = QHBoxLayout()
        lower.setSpacing(16)
        self.donut_card = Card()
        dl = QVBoxLayout(self.donut_card)
        dl.setContentsMargins(18, 16, 18, 16)
        self.donut_title = make_label("Storage usage", "h2")
        dl.addWidget(self.donut_title)
        self.donut = PieChartWidget(min_height=250)
        dl.addWidget(self.donut, 1)
        lower.addWidget(self.donut_card, 1)

        self.info_card = Card()
        il = QVBoxLayout(self.info_card)
        il.setContentsMargins(18, 16, 18, 16)
        il.setSpacing(6)
        self.info_title = make_label("Last scan", "h2")
        il.addWidget(self.info_title)
        self.info_grid = QGridLayout()
        self.info_grid.setHorizontalSpacing(24)
        self.info_grid.setVerticalSpacing(8)
        self.info_values: dict[str, QLabel] = {}
        for i, key in enumerate(("Scanned on", "Location", "Files", "Folders", "Data scanned",
                                 "Duration", "Largest category", "Access errors")):
            self.info_grid.addWidget(make_label(key, "muted"), i, 0)
            val = QLabel("-")
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.info_values[key] = val
            self.info_grid.addWidget(val, i, 1)
        self.info_grid.setColumnStretch(1, 1)
        il.addLayout(self.info_grid)
        il.addStretch(1)
        self.info_note = make_label("", "muted", wrap=True)
        il.addWidget(self.info_note)
        lower.addWidget(self.info_card, 1)
        self.body_layout.addLayout(lower)
        self.body_layout.addStretch(1)

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        s = self.state
        s.drives_changed.connect(self.rebuild)
        s.selected_changed.connect(lambda _r: self.refresh_selection())
        s.last_scans_changed.connect(self.refresh_selection)
        s.scan_started.connect(lambda _r: self._set_busy(True))
        s.scan_finished.connect(lambda _r: self._set_busy(False))
        s.scan_failed.connect(lambda _m: self._set_busy(False))
        self.rebuild()

    # ---------------------------------------------------------------- building
    def rebuild(self) -> None:
        for c in self.cards:
            c.setParent(None)
            c.deleteLater()
        self.cards = []
        for d in self.state.drives:
            card = DriveCard(d)
            card.clicked.connect(self.state.select)
            card.scan_requested.connect(self.scan_requested)
            card.set_busy(self.state.scanning)
            self.cards.append(card)
        self.empty_label.setVisible(not self.cards)
        self._cols = 0
        self._relayout()
        self.refresh_selection()

    def _relayout(self) -> None:
        # Use the page width: child widgets are not yet resized when resizeEvent fires.
        width = self.width() - 28 * 2 - 24
        cols = max(1, (width + 16) // (CARD_MIN_WIDTH + 16))
        cols = min(cols, max(1, len(self.cards)))
        if cols == self._cols and self.grid.count() == len(self.cards):
            return
        self._cols = cols
        while self.grid.count():
            self.grid.takeAt(0)
        for i, card in enumerate(self.cards):
            self.grid.addWidget(card, i // cols, i % cols)
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._relayout()

    def _set_busy(self, busy: bool) -> None:
        for c in self.cards:
            c.set_busy(busy)
        self.refresh_selection()

    # ---------------------------------------------------------------- selection / info
    def refresh_selection(self) -> None:
        st = self.state
        for c in self.cards:
            c.set_selected(c.drive.mountpoint == st.selected_root)
            c.set_last_scan(st.last_scans.get(c.drive.mountpoint))
        drive = st.drive_for(st.selected_root)
        self._update_donut(drive)
        self._update_info()

    def _update_donut(self, drive: DriveInfo | None) -> None:
        p = theme.palette()
        if drive is None:
            self.donut_title.setText("Storage usage")
            self.donut.set_data([], "-", "No drive selected")
            return
        self.donut_title.setText(f"Storage usage - {drive.display_name}")
        used_color = p.success if drive.percent_used < 70 else p.warning if drive.percent_used < 90 else p.danger
        self.donut.set_data(
            [("Used", drive.used, used_color), ("Free", drive.free, p.track)],
            f"{drive.percent_used:.0f}%", f"{format_size(drive.used)} of {format_size(drive.total)}")

    def _update_info(self) -> None:
        st, v = self.state, self.info_values
        root = st.selected_root
        info = st.last_scans.get(root) if root else None
        for lab in v.values():
            lab.setText("-")
        if st.scanning:
            self.info_note.setText("A scan is currently running - see the Drive Scanner page.")
        else:
            self.info_note.setText("" if info else "This location has not been scanned yet. "
                                   "Click 'Scan this drive' to analyse it.")
        if not info:
            return
        v["Scanned on"].setText(format_timestamp(datetime.fromisoformat(info["timestamp"]))
                                + (" (cancelled - partial results)" if info.get("cancelled") else ""))
        v["Location"].setText(root or "-")
        v["Files"].setText(format_count(info["files"]))
        v["Folders"].setText(format_count(info["folders"]))
        v["Data scanned"].setText(format_size(info["bytes"]))
        v["Duration"].setText(format_duration(info["duration"]))
        v["Access errors"].setText(format_count(info.get("errors", 0)))
        res = st.result
        if res is not None and res.root_path == root and res.type_stats.by_category:
            cat, n, b = res.type_stats.category_rows()[0]
            v["Largest category"].setText(f"{cat} - {format_size(b)} ({format_count(n)} files)")

    def apply_theme(self, p=None) -> None:
        self.brand_logo.apply_theme(p)
        for c in self.cards:
            c.apply_theme()
        self.refresh_selection()

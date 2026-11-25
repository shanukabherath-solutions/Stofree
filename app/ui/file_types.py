"""File Types page: per-category and per-extension storage breakdown."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QHBoxLayout, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import theme
from ..core.disk_scanner import ScanResult
from ..state import AppState
from ..utils.constants import CATEGORY_COLORS
from ..utils.formatters import format_count, format_percent, format_size
from .widgets import Card, PageHeader, PieChartWidget, make_label


def _item(text: str, align_right: bool = False, sort_value=None) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    if align_right:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if sort_value is not None:
        it.setData(Qt.UserRole, sort_value)
    return it


class NumItem(QTableWidgetItem):
    """Sorts by its numeric UserRole value rather than text."""

    def __lt__(self, other) -> bool:
        a, b = self.data(Qt.UserRole), other.data(Qt.UserRole)
        return a < b if a is not None and b is not None else super().__lt__(other)


def _num(text: str, value: int) -> NumItem:
    it = NumItem(text)
    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    it.setData(Qt.UserRole, value)
    return it


class FileTypesPage(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.state = state
        self._result: ScanResult | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(14)
        root.addWidget(PageHeader("File Types", "How scanned storage is distributed across file categories"))

        top = QHBoxLayout()
        top.setSpacing(16)
        self.cat_table = self._make_table(["Category", "Files", "Size", "% of scanned data"])
        top.addWidget(self.cat_table, 3)
        chart_card = Card()
        cl = QVBoxLayout(chart_card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.addWidget(make_label("Share by size", "h2"))
        self.pie = PieChartWidget(show_legend=False, min_height=250)
        cl.addWidget(self.pie, 1)
        top.addWidget(chart_card, 2)
        root.addLayout(top, 3)

        root.addWidget(make_label("Largest extensions", "h2"))
        self.ext_table = self._make_table(["Extension", "Files", "Size", "% of scanned data"])
        root.addWidget(self.ext_table, 2)
        self.empty = make_label("Run a scan to analyse file types.", "muted")
        root.addWidget(self.empty)

        self.state.scan_finished.connect(self.set_result)
        if state.result:
            self.set_result(state.result)

    def _make_table(self, headers: list[str]) -> QTableWidget:
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setAlternatingRowColors(True)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, len(headers)):
            t.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        return t

    def set_result(self, r: ScanResult) -> None:
        self._result = r
        self.empty.setVisible(False)
        total = r.type_stats.total_bytes()
        cats = r.type_stats.category_rows()

        self.cat_table.setSortingEnabled(False)
        self.cat_table.setRowCount(len(cats))
        for i, (cat, n, b) in enumerate(cats):
            name = _item(f"  {cat}")
            name.setData(Qt.DecorationRole, self._swatch(CATEGORY_COLORS.get(cat, "#888888")))
            self.cat_table.setItem(i, 0, name)
            self.cat_table.setItem(i, 1, _num(format_count(n), n))
            self.cat_table.setItem(i, 2, _num(format_size(b), b))
            self.cat_table.setItem(i, 3, _num(format_percent(b, total), int(b * 10000 / total) if total else 0))
        self.cat_table.setSortingEnabled(True)
        self.cat_table.sortByColumn(2, Qt.DescendingOrder)

        exts = r.type_stats.extension_rows(30)
        self.ext_table.setSortingEnabled(False)
        self.ext_table.setRowCount(len(exts))
        for i, (ext, n, b) in enumerate(exts):
            self.ext_table.setItem(i, 0, _item(ext))
            self.ext_table.setItem(i, 1, _num(format_count(n), n))
            self.ext_table.setItem(i, 2, _num(format_size(b), b))
            self.ext_table.setItem(i, 3, _num(format_percent(b, total), int(b * 10000 / total) if total else 0))
        self.ext_table.setSortingEnabled(True)
        self.ext_table.sortByColumn(2, Qt.DescendingOrder)
        self._update_pie()

    def _swatch(self, color: str):
        pm = QPixmap(14, 14)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, 14, 14, 4, 4)
        p.end()
        return QIcon(pm)

    def _update_pie(self) -> None:
        r = self._result
        if r is None:
            return
        total = r.type_stats.total_bytes()
        items = [(c, b, CATEGORY_COLORS.get(c, "#888888")) for c, _n, b in r.type_stats.category_rows()]
        self.pie.set_data(items, format_size(total), f"{format_count(r.total_files)} files")

    def apply_theme(self, _p=None) -> None:
        self._update_pie()

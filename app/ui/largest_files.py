"""Largest Files page: model-backed table with sorting, search and category filter."""
from __future__ import annotations

import os

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QUrl,
)
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLineEdit, QMenu, QTableView,
    QVBoxLayout, QWidget,
)

from ..core.disk_scanner import ScanResult
from ..core.file_analyzer import FileRecord, categorize_extension
from ..state import AppState
from ..utils.constants import CATEGORY_ORDER
from ..utils.formatters import format_count, format_size
from .widgets import PageHeader, make_label

COLUMNS = ["File name", "Size", "Extension", "Parent directory", "Full path"]
SORT_ROLE = Qt.UserRole + 1


class FilesTableModel(QAbstractTableModel):
    """Read-only model over (name, size, ext, parent, path, category) tuples."""

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[tuple[str, int, str, str, str, str]] = []

    def set_records(self, records: list[FileRecord]) -> None:
        self.beginResetModel()
        rows = []
        for r in records:
            ext = r.extension
            rows.append((r.name, r.size, ext.lstrip(".").upper() or "-", r.parent, r.path,
                         categorize_extension(ext)))
        self._rows = rows
        self.endResetModel()

    def row(self, i: int):
        return self._rows[i]

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        name, size, ext, parent, path, _cat = self._rows[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            return (name, format_size(size), ext, parent, path)[col]
        if role == SORT_ROLE:
            return (name.lower(), size, ext.lower(), parent.lower(), path.lower())[col]
        if role == Qt.TextAlignmentRole and col == 1:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ToolTipRole:
            return path
        return None


class FilesProxy(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.setSortRole(SORT_ROLE)
        self.text = ""
        self.category = ""

    def set_filters(self, text: str, category: str) -> None:
        # Qt >= 6.10: beginFilterChange()/endFilterChange() replace invalidateFilter().
        if hasattr(self, "beginFilterChange"):
            self.beginFilterChange()
            self.text, self.category = text.strip().lower(), category
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            self.text, self.category = text.strip().lower(), category
            self.invalidateFilter()

    def filterAcceptsRow(self, row, parent) -> bool:  # noqa: N802
        name, _s, ext, par, path, cat = self.sourceModel().row(row)
        if self.category and cat != self.category:
            return False
        if self.text:
            hay = f"{name} {path} {ext}".lower()
            return all(tok in hay for tok in self.text.split())
        return True


class LargestFilesPage(QWidget):
    SORTS = [("Largest first", 1, Qt.DescendingOrder), ("Smallest first", 1, Qt.AscendingOrder),
             ("File name (A-Z)", 0, Qt.AscendingOrder), ("File type (A-Z)", 2, Qt.AscendingOrder)]

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.state = state
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(14)
        root.addWidget(PageHeader("Largest Files", "The biggest files found in the last scan"))

        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name, path or extension...")
        self.search.setClearButtonEnabled(True)
        bar.addWidget(self.search, 1)
        self.category = QComboBox()
        self.category.addItem("All types", "")
        for c in CATEGORY_ORDER:
            self.category.addItem(c, c)
        bar.addWidget(self.category)
        self.sort_combo = QComboBox()
        for label, *_ in self.SORTS:
            self.sort_combo.addItem(label)
        bar.addWidget(make_label("Sort:", "muted"))
        bar.addWidget(self.sort_combo)
        root.addLayout(bar)

        self.model = FilesTableModel()
        self.proxy = FilesProxy()
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideMiddle)
        hh = self.table.horizontalHeader()
        hh.setStretchLastSection(True)
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setSectionResizeMode(0, QHeaderView.Interactive)
        hh.setSectionResizeMode(3, QHeaderView.Interactive)
        self.table.setColumnWidth(0, 260)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 260)
        root.addWidget(self.table, 1)

        self.summary = make_label("Run a scan to see the largest files.", "muted")
        root.addWidget(self.summary)

        self.search.textChanged.connect(self._filters_changed)
        self.category.currentIndexChanged.connect(self._filters_changed)
        self.sort_combo.currentIndexChanged.connect(self._apply_sort)
        self.table.customContextMenuRequested.connect(self._menu)
        self.table.doubleClicked.connect(lambda _i: self._open_folder())
        self.proxy.layoutChanged.connect(self._update_summary)
        self.proxy.modelReset.connect(self._update_summary)
        self.state.scan_finished.connect(self.set_result)
        self._apply_sort()
        if state.result:
            self.set_result(state.result)

    def set_result(self, r: ScanResult) -> None:
        self.model.set_records(r.top_files)
        self._apply_sort()
        self._update_summary()

    def _apply_sort(self) -> None:
        _label, col, order = self.SORTS[self.sort_combo.currentIndex()]
        self.table.sortByColumn(col, order)

    def _filters_changed(self) -> None:
        self.proxy.set_filters(self.search.text(), self.category.currentData() or "")
        self._update_summary()

    def _update_summary(self) -> None:
        r = self.state.result
        if r is None:
            return
        shown = self.proxy.rowCount()
        total = self.model.rowCount()
        size = sum(self.model.row(self.proxy.mapToSource(self.proxy.index(i, 0)).row())[1]
                   for i in range(shown)) if shown <= 50_000 else 0
        extra = ""
        if r.total_files > total:
            extra = f"  -  tracking the {format_count(total)} largest of {format_count(r.total_files)} files"
        self.summary.setText(f"Showing {format_count(shown)} of {format_count(total)} files "
                             f"({format_size(size)}){extra}")

    # ---- row actions (read-only: open / copy only)
    def _selected_rows(self):
        return [self.model.row(self.proxy.mapToSource(i).row())
                for i in self.table.selectionModel().selectedRows()]

    def _open_folder(self) -> None:
        rows = self._selected_rows()
        if rows and os.path.isdir(rows[0][3]):
            QDesktopServices.openUrl(QUrl.fromLocalFile(rows[0][3]))

    def _menu(self, pos) -> None:
        if not self._selected_rows():
            return
        m = QMenu(self)
        a_open = m.addAction("Open containing folder")
        a_path = m.addAction("Copy full path")
        a_name = m.addAction("Copy file name")
        chosen = m.exec(self.table.viewport().mapToGlobal(pos))
        rows = self._selected_rows()
        cb = QGuiApplication.clipboard()
        if chosen is a_open:
            self._open_folder()
        elif chosen is a_path:
            cb.setText("\n".join(r[4] for r in rows))
        elif chosen is a_name:
            cb.setText("\n".join(r[0] for r in rows))

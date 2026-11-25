"""Folder Explorer page: sortable folder tree + comparison chart of the selected folder."""
from __future__ import annotations

import os

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QHBoxLayout, QHeaderView, QMenu, QPushButton, QSplitter,
    QStyle, QStyledItemDelegate, QTreeView, QVBoxLayout, QWidget,
)

from .. import theme
from ..core.disk_scanner import ScanResult
from ..core.folder_analyzer import FolderNode
from ..state import AppState
from ..utils.formatters import format_count, format_size
from .widgets import BarChartWidget, Card, PageHeader, make_label

PCT_ROLE = Qt.UserRole + 2


class FolderTreeModel(QAbstractItemModel):
    HEADERS = ["Folder", "Size", "% of parent", "Files", "Subfolders"]

    def __init__(self) -> None:
        super().__init__()
        self._root: FolderNode | None = None
        self._sort_col = 1
        self._sort_order = Qt.DescendingOrder
        self._cache: dict[int, list[FolderNode]] = {}
        self._rows: dict[int, int] = {}
        self._folder_icon = None

    # ---- data
    def set_root(self, node: FolderNode | None) -> None:
        self.beginResetModel()
        self._root = node
        self._clear_cache()
        self.endResetModel()

    def _clear_cache(self) -> None:
        self._cache.clear()
        self._rows.clear()
        if self._root is not None:
            self._rows[id(self._root)] = 0

    def _key(self, n: FolderNode):
        c = self._sort_col
        if c == 0:
            return n.name.lower()
        if c in (1, 2):
            return n.size
        if c == 3:
            return n.file_count
        return n.folder_count

    def _kids(self, node: FolderNode | None) -> list[FolderNode]:
        if node is None:
            return [self._root] if self._root is not None else []
        kids = self._cache.get(id(node))
        if kids is None:
            kids = sorted(node.children, key=self._key, reverse=self._sort_order == Qt.DescendingOrder)
            self._cache[id(node)] = kids
            for i, c in enumerate(kids):
                self._rows[id(c)] = i
        return kids

    # ---- model interface
    def index(self, row, column, parent=QModelIndex()):
        if row < 0 or column < 0 or column >= len(self.HEADERS):
            return QModelIndex()
        pnode = parent.internalPointer() if parent.isValid() else None
        kids = self._kids(pnode)
        if row >= len(kids):
            return QModelIndex()
        return self.createIndex(row, column, kids[row])

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        node: FolderNode = index.internalPointer()
        p = node.parent
        if p is None:
            return QModelIndex()
        self._kids(p.parent)             # make sure p's row number is cached
        return self.createIndex(self._rows[id(p)], 0, p)

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            return 1 if self._root is not None else 0
        return len(parent.internalPointer().children)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return len(self.HEADERS)

    def hasChildren(self, parent=QModelIndex()) -> bool:  # noqa: N802
        if not parent.isValid():
            return self._root is not None
        return bool(parent.internalPointer().children)

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        if orientation == Qt.Horizontal and role == Qt.TextAlignmentRole and section > 0:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def _pct(self, n: FolderNode) -> float:
        if n.parent is None or n.parent.size <= 0:
            return 100.0 if n.parent is None else 0.0
        return n.size / n.parent.size * 100.0

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        n: FolderNode = index.internalPointer()
        c = index.column()
        if role == Qt.DisplayRole:
            if c == 0:
                return n.name if n.accessible else f"{n.name}  (access denied)"
            return (None, format_size(n.size), f"{self._pct(n):.1f}%",
                    format_count(n.file_count), format_count(n.folder_count))[c]
        if role == Qt.DecorationRole and c == 0:
            if self._folder_icon is None:
                self._folder_icon = QApplication.style().standardIcon(QStyle.SP_DirIcon)
            return self._folder_icon
        if role == PCT_ROLE and c == 2:
            return self._pct(n)
        if role == Qt.TextAlignmentRole and c > 0:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ToolTipRole:
            return n.path
        if role == Qt.ForegroundRole and not n.accessible:
            return QColor(theme.palette().warning)
        return None

    def sort(self, column: int, order=Qt.AscendingOrder) -> None:
        self.beginResetModel()
        self._sort_col, self._sort_order = column, order
        self._clear_cache()
        self.endResetModel()

    @staticmethod
    def node(index) -> FolderNode | None:
        return index.internalPointer() if index.isValid() else None


class PercentBarDelegate(QStyledItemDelegate):
    """Draws a thin share-of-parent bar behind the percentage text."""

    def paint(self, painter: QPainter, option, index) -> None:
        super().paint(painter, option, index)
        pct = index.data(PCT_ROLE)
        if pct is None:
            return
        p = theme.palette()
        r = option.rect.adjusted(8, 0, -8, -4)
        r.setTop(r.bottom() - 3)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(p.track))
        painter.drawRoundedRect(r, 1.5, 1.5)
        w = max(2, int(r.width() * min(pct, 100) / 100))
        r2 = r.adjusted(0, 0, -(r.width() - w), 0)
        painter.setBrush(QColor(p.accent))
        painter.drawRoundedRect(r2, 1.5, 1.5)
        painter.restore()


class FolderExplorerPage(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.state = state
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(14)
        header = PageHeader("Folder Explorer", "Browse folders by size to find what uses the most space")
        self.expand_btn = QPushButton("Expand top level")
        self.collapse_btn = QPushButton("Collapse all")
        header.add_action(self.expand_btn)
        header.add_action(self.collapse_btn)
        root.addWidget(header)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)

        self.model = FolderTreeModel()
        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSortingEnabled(True)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setItemDelegateForColumn(2, PercentBarDelegate(self.tree))
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.setAnimated(True)
        hh = self.tree.header()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for col, w in ((1, 100), (2, 110), (3, 90), (4, 100)):
            hh.setSectionResizeMode(col, QHeaderView.Interactive)
            self.tree.setColumnWidth(col, w)
        self.tree.sortByColumn(1, Qt.DescendingOrder)
        split.addWidget(self.tree)

        side = Card()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(16, 14, 16, 14)
        self.sel_title = make_label("Select a folder", "h2")
        self.sel_title.setWordWrap(True)
        sl.addWidget(self.sel_title)
        self.sel_info = make_label("", "muted", wrap=True)
        sl.addWidget(self.sel_info)
        sl.addWidget(make_label("Largest items inside", "muted"))
        self.chart = BarChartWidget("Nothing to compare")
        sl.addWidget(self.chart, 1)
        split.addWidget(side)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        root.addWidget(split, 1)

        self.empty = make_label("Run a scan to explore folders.", "muted")
        root.addWidget(self.empty)

        self.tree.selectionModel().currentChanged.connect(self._selected)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.expand_btn.clicked.connect(self._expand_top)
        self.collapse_btn.clicked.connect(self.tree.collapseAll)
        self.state.scan_finished.connect(self.set_result)
        if state.result:
            self.set_result(state.result)

    def set_result(self, r: ScanResult) -> None:
        self.model.set_root(r.root)
        self.empty.setVisible(False)
        self._expand_top()
        idx = self.model.index(0, 0)
        self.tree.setCurrentIndex(idx)
        self._show_node(r.root)

    def _expand_top(self) -> None:
        idx = self.model.index(0, 0)
        if idx.isValid():
            self.tree.expand(idx)

    def _selected(self, current: QModelIndex, _prev) -> None:
        node = self.model.node(current)
        if node is not None:
            self._show_node(node)

    def _show_node(self, node: FolderNode) -> None:
        self.sel_title.setText(node.path)
        denied = "" if node.accessible else "  -  access denied, contents unknown"
        self.sel_info.setText(f"{format_size(node.size)}  -  {format_count(node.file_count)} files  -  "
                              f"{format_count(node.folder_count)} subfolders{denied}")
        items = [(c.name, c.size) for c in node.children_by_size()[:10] if c.size > 0]
        if node.direct_size > 0:
            items.append((f"(files in {node.name or 'this folder'})", node.direct_size))
            items.sort(key=lambda t: t[1], reverse=True)
            items = items[:10]
        self.chart.set_data(items, empty_text="This folder has no sized contents")

    def _menu(self, pos) -> None:
        node = self.model.node(self.tree.indexAt(pos))
        if node is None:
            return
        m = QMenu(self)
        a_open = m.addAction("Open in File Explorer")
        a_copy = m.addAction("Copy folder path")
        chosen = m.exec(self.tree.viewport().mapToGlobal(pos))
        if chosen is a_open and os.path.isdir(node.path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(node.path))
        elif chosen is a_copy:
            QGuiApplication.clipboard().setText(node.path)

    def apply_theme(self, _p=None) -> None:
        self.chart.apply_theme()
        self.tree.viewport().update()

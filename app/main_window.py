"""Main window: sidebar navigation + stacked pages, wired to the shared AppState."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QSizePolicy, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from . import theme
from .state import AppState
from .ui.branding import BrandHeader, app_icon
from .ui.dashboard import DashboardPage
from .ui.file_types import FileTypesPage
from .ui.folder_explorer import FolderExplorerPage
from .ui.icons import icon
from .ui.largest_files import LargestFilesPage
from .ui.reports import ReportsPage
from .ui.scanner import ScannerPage
from .ui.settings import SettingsPage
from .ui.widgets import fade_in, set_animations_enabled
from .utils.constants import APP_NAME, APP_SUBTITLE, APP_VERSION
from .utils.formatters import format_count, format_duration, format_size

NAV = [("Dashboard", "dashboard"), ("Drive Scanner", "scanner"), ("Largest Files", "largest_files"),
       ("Folder Explorer", "folder_explorer"), ("File Types", "file_types"),
       ("Reports", "reports"), ("Settings", "settings")]
COLLAPSE_BELOW = 980
SIDEBAR_FULL, SIDEBAR_SLIM = 226, 68


class MainWindow(QMainWindow):
    def __init__(self, state: AppState | None = None, auto_refresh: bool = True) -> None:
        super().__init__()
        self.state = state or AppState()
        set_animations_enabled(self.state.animations)
        self.setWindowTitle(f"{APP_NAME} - {APP_SUBTITLE}")
        icon = app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.resize(1280, 820)
        self.setMinimumSize(860, 580)
        self._collapsed = False

        central = QWidget()
        self.setCentralWidget(central)
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # ---- sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(SIDEBAR_FULL)
        sl = QVBoxLayout(self.sidebar)
        sl.setContentsMargins(12, 18, 12, 14)
        sl.setSpacing(4)
        self.brand_header = BrandHeader(logo_width=SIDEBAR_FULL - 24 - 16)
        sl.addWidget(self.brand_header)
        sl.addSpacing(14)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.nav_buttons: list[QToolButton] = []
        for i, (label, _icon) in enumerate(NAV):
            b = QToolButton()
            b.setObjectName("NavButton")
            b.setText(f"  {label}")
            b.setCheckable(True)
            b.setToolTip(label)
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setIconSize(QSize(20, 20))
            b.setMinimumHeight(40)
            b.setCursor(Qt.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.group.addButton(b, i)
            self.nav_buttons.append(b)
            sl.addWidget(b)
        sl.addStretch(1)
        self.theme_btn = QToolButton()
        self.theme_btn.setObjectName("IconButton")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setToolTip("Toggle dark / light theme")
        self.theme_btn.clicked.connect(self._toggle_theme)
        sl.addWidget(self.theme_btn, 0, Qt.AlignLeft)
        self.version = QLabel(f"{APP_NAME} v{APP_VERSION} - read-only")
        self.version.setObjectName("BrandSub")
        sl.addWidget(self.version)
        row.addWidget(self.sidebar)

        # ---- pages
        self.stack = QStackedWidget()
        s = self.state
        self.dashboard = DashboardPage(s)
        self.scanner = ScannerPage(s)
        self.largest = LargestFilesPage(s)
        self.explorer = FolderExplorerPage(s)
        self.types = FileTypesPage(s)
        self.reports = ReportsPage(s)
        self.settings_page = SettingsPage(s)
        self.pages = [self.dashboard, self.scanner, self.largest, self.explorer,
                      self.types, self.reports, self.settings_page]
        for p in self.pages:
            self.stack.addWidget(p)
        row.addWidget(self.stack, 1)

        self.group.idClicked.connect(self._goto)
        self.dashboard.scan_requested.connect(self._scan_from_dashboard)
        s.theme_changed.connect(self._apply_theme)
        s.scan_started.connect(lambda r: self.statusBar().showMessage(f"Scanning {r} ..."))
        s.scan_finished.connect(self._on_scan_finished)
        s.scan_failed.connect(self._on_scan_failed)

        self.statusBar().showMessage("Ready")
        self._apply_theme(s.theme, initial=True)
        self.nav_buttons[0].setChecked(True)
        if auto_refresh:
            s.refresh_drives()

    # ------------------------------------------------------------------ navigation
    def goto(self, index: int) -> None:
        self.nav_buttons[index].setChecked(True)
        self._goto(index)

    def _goto(self, index: int) -> None:
        if self.stack.currentIndex() != index:
            self.stack.setCurrentIndex(index)
            fade_in(self.stack.currentWidget())

    def _scan_from_dashboard(self, root: str) -> None:
        self.goto(1)
        self.scanner.start_scan_for(root)

    # ------------------------------------------------------------------ scan events
    def _on_scan_finished(self, r) -> None:
        state = "cancelled (partial)" if r.cancelled else "complete"
        self.statusBar().showMessage(
            f"Scan {state}: {format_count(r.total_files)} files, {format_count(r.total_folders)} folders, "
            f"{format_size(r.total_size)} in {format_duration(r.duration)}")

    def _on_scan_failed(self, message: str) -> None:
        self.statusBar().showMessage("Scan failed")
        QMessageBox.warning(self, "Scan failed", message)

    # ------------------------------------------------------------------ theme
    def _toggle_theme(self) -> None:
        self.state.set_theme("light" if theme.palette().is_dark else "dark")
        self.pages[6].theme_combo.blockSignals(True)
        self.pages[6].theme_combo.setCurrentIndex(self.pages[6].theme_combo.findData(self.state.theme))
        self.pages[6].theme_combo.blockSignals(False)

    def _apply_theme(self, name: str, initial: bool = False) -> None:
        p = theme.apply_theme(QApplication.instance(), name)
        for b, (_label, ic) in zip(self.nav_buttons, NAV):
            icn = QIcon()
            icn.addPixmap(icon(ic, p.muted, 20).pixmap(20, 20), QIcon.Normal, QIcon.Off)
            icn.addPixmap(icon(ic, "#FFFFFF", 20).pixmap(20, 20), QIcon.Normal, QIcon.On)
            b.setIcon(icn)
        self.theme_btn.setIcon(icon("sun" if p.is_dark else "moon", p.text, 18))
        self.brand_header.apply_theme(p)
        for page in self.pages:
            if hasattr(page, "apply_theme"):
                page.apply_theme(p)
        self.update()

    # ------------------------------------------------------------------ responsive sidebar
    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        collapsed = self.width() < COLLAPSE_BELOW
        if collapsed != self._collapsed:
            self._collapsed = collapsed
            self.sidebar.setFixedWidth(SIDEBAR_SLIM if collapsed else SIDEBAR_FULL)
            style = Qt.ToolButtonIconOnly if collapsed else Qt.ToolButtonTextBesideIcon
            for b in self.nav_buttons:
                b.setToolButtonStyle(style)
            self.brand_header.set_collapsed(collapsed)
            self.version.setVisible(not collapsed)

    # ------------------------------------------------------------------ shutdown
    def closeEvent(self, e) -> None:  # noqa: N802
        if self.state.scanning:
            ans = QMessageBox.question(self, "Scan in progress",
                                       "A scan is still running. Cancel it and exit?")
            if ans != QMessageBox.Yes:
                e.ignore()
                return
        self.state.wait_for_scan()
        super().closeEvent(e)

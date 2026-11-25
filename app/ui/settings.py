"""Settings page: theme, scan options, diagnostics."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QPushButton, QVBoxLayout, QWidget,
)

from ..state import AppState
from ..utils.constants import APP_NAME, APP_SUBTITLE, APP_VERSION
from ..utils.logger import log_dir
from .branding import EmblemBadge
from .widgets import Card, ChoiceBox, PageHeader, make_label, set_animations_enabled


class SettingsPage(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.state = state
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(16)
        root.addWidget(PageHeader("Settings", "Appearance and scan preferences"))

        card = Card()
        g = QGridLayout(card)
        g.setContentsMargins(18, 16, 18, 16)
        g.setHorizontalSpacing(18)
        g.setVerticalSpacing(14)
        g.setColumnStretch(2, 1)

        g.addWidget(make_label("Appearance", "h2"), 0, 0, 1, 3)
        g.addWidget(make_label("Theme", "muted"), 1, 0)
        self.theme_combo = QComboBox()
        for label, key in (("Dark", "dark"), ("Light", "light"), ("Follow system", "system")):
            self.theme_combo.addItem(label, key)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(state.theme)))
        g.addWidget(self.theme_combo, 1, 1)
        self.anim = QCheckBox("Enable animations")
        self.anim.setChecked(state.animations)
        g.addWidget(self.anim, 2, 1, 1, 2)

        g.addWidget(make_label("Scanning", "h2"), 3, 0, 1, 3)
        g.addWidget(make_label("Largest files to keep", "muted"), 4, 0)
        self.top_files = ChoiceBox([(f"{n:,}", n) for n in (1000, 5000, 10_000, 25_000, 50_000, 100_000)])
        self.top_files.setValue(state.top_files_limit)
        g.addWidget(self.top_files, 4, 1)
        g.addWidget(make_label("Applies to the next scan. Only the largest N files are kept in memory; "
                               "totals always include every file.", "muted", wrap=True), 4, 2)
        self.removable = QCheckBox("Include removable drives")
        self.removable.setChecked(state.include_removable)
        g.addWidget(self.removable, 5, 1, 1, 2)
        root.addWidget(card)

        diag = Card()
        d = QVBoxLayout(diag)
        d.setContentsMargins(18, 16, 18, 16)
        d.addWidget(make_label("Diagnostics", "h2"))
        d.addWidget(make_label(f"Log folder: {log_dir()}", "muted", wrap=True))
        btn = QPushButton("Open log folder")
        btn.clicked.connect(self._open_logs)
        d.addWidget(btn)
        root.addWidget(diag)

        about = Card()
        a = QHBoxLayout(about)
        a.setContentsMargins(18, 16, 18, 16)
        a.setSpacing(20)
        self.about_logo = EmblemBadge(width=150, padding=12)
        a.addWidget(self.about_logo, 0, Qt.AlignTop)
        info = QVBoxLayout()
        info.setSpacing(4)
        info.addWidget(make_label(f"About {APP_NAME}", "h2"))
        info.addWidget(make_label(f"{APP_SUBTITLE}  -  version {APP_VERSION}", "muted"))
        info.addWidget(make_label(f"{APP_NAME} is strictly read-only: it never deletes, moves, or "
                                  "modifies files, and never reads file contents. It only reads file "
                                  "names, sizes and folder structure.", "muted", wrap=True))
        info.addStretch(1)
        a.addLayout(info, 1)
        root.addWidget(about)
        root.addStretch(1)

        self.theme_combo.currentIndexChanged.connect(lambda _i: state.set_theme(self.theme_combo.currentData()))
        self.anim.toggled.connect(self._anim_changed)
        self.top_files.valueChanged.connect(lambda v: state.set_value("top_files_limit", v))
        self.removable.toggled.connect(self._removable_changed)

    def _anim_changed(self, on: bool) -> None:
        set_animations_enabled(on)
        self.state.set_value("animations", "true" if on else "false")

    def _removable_changed(self, on: bool) -> None:
        self.state.set_value("include_removable", "true" if on else "false")
        self.state.refresh_drives_async()

    def _open_logs(self) -> None:
        d = log_dir()
        os.makedirs(d, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

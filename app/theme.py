"""Dark / light themes and the application stylesheet."""
from __future__ import annotations

from dataclasses import dataclass
from string import Template

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from .utils.assets import asset_path


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    sidebar: str
    surface: str
    surface_alt: str
    border: str
    text: str
    muted: str
    accent: str
    accent_hover: str
    success: str
    warning: str
    danger: str
    track: str
    hover: str

    @property
    def is_dark(self) -> bool:
        return self.name == "dark"


DARK = Palette(
    name="dark", bg="#14161B", sidebar="#0F1115", surface="#1C1F26", surface_alt="#242834",
    border="#2D323E", text="#E7EAF0", muted="#9AA3B5", accent="#4F8EF7", accent_hover="#6AA1FA",
    success="#34C08A", warning="#F2A33A", danger="#EC5F57", track="#2A2F3B", hover="#262B37",
)
LIGHT = Palette(
    name="light", bg="#F3F5F9", sidebar="#E8ECF4", surface="#FFFFFF", surface_alt="#F0F2F8",
    border="#DCE1EB", text="#1A1E28", muted="#5E6A80", accent="#2563EB", accent_hover="#3B78F0",
    success="#1E9E6A", warning="#D98412", danger="#D6453D", track="#E3E7F0", hover="#E2E7F1",
)
PALETTES = {"dark": DARK, "light": LIGHT}

_current: Palette = DARK


def palette() -> Palette:
    return _current


_QSS = Template("""
* { font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif; font-size: 10pt; }
QMainWindow, QWidget#Page, QStackedWidget { background: $bg; }
QWidget { color: $text; }
QToolTip { background: $surface_alt; color: $text; border: 1px solid $border; padding: 4px 6px; }

/* ---- sidebar ---- */
QFrame#Sidebar { background: $sidebar; border-right: 1px solid $border; }
QFrame#LogoPlate { background: #FFFFFF; border: 1px solid $border; border-radius: 10px; }
QLabel#BrandSub { color: $muted; font-size: 8.5pt; }
QToolButton#NavButton { background: transparent; border: none; border-radius: 8px;
    padding: 10px 12px; text-align: left; color: $muted; font-weight: 500; }
QToolButton#NavButton:hover { background: $hover; color: $text; }
QToolButton#NavButton:checked { background: $accent; color: #FFFFFF; }
QToolButton#IconButton { background: transparent; border: 1px solid $border; border-radius: 8px; padding: 7px; }
QToolButton#IconButton:hover { background: $hover; }

/* ---- text roles ---- */
QLabel { background: transparent; }
QLabel[role="title"] { font-size: 19pt; font-weight: 700; }
QLabel[role="subtitle"] { color: $muted; }
QLabel[role="h2"] { font-size: 11.5pt; font-weight: 600; }
QLabel[role="muted"] { color: $muted; }
QLabel[role="stat"] { font-size: 17pt; font-weight: 700; }
QLabel[role="statcaption"] { color: $muted; font-size: 8.5pt; }
QLabel[role="pct"] { font-size: 20pt; font-weight: 700; }
QLabel[role="ok"] { color: $success; }
QLabel[role="warn"] { color: $warning; }
QLabel[role="bad"] { color: $danger; }

/* ---- cards ---- */
QFrame#Card, QFrame#DriveCard { background: $surface; border: 1px solid $border; border-radius: 12px; }
QFrame#DriveCard:hover { border-color: $accent; }
QFrame#DriveCard[selected="true"] { border: 2px solid $accent; }
QFrame#Card QLabel, QFrame#DriveCard QLabel { background: transparent; }

/* ---- buttons ---- */
QPushButton { background: $surface_alt; border: 1px solid $border; border-radius: 8px; padding: 8px 16px; font-weight: 500; }
QPushButton:hover { background: $hover; border-color: $accent; }
QPushButton:disabled { color: $muted; background: $surface; border-color: $border; }
QPushButton[variant="primary"] { background: $accent; border-color: $accent; color: #FFFFFF; }
QPushButton[variant="primary"]:hover { background: $accent_hover; }
QPushButton[variant="primary"]:disabled { background: $track; border-color: $track; color: $muted; }
QPushButton[variant="danger"] { background: transparent; border-color: $danger; color: $danger; }
QPushButton[variant="danger"]:hover { background: $danger; color: #FFFFFF; }
QPushButton[variant="danger"]:disabled { border-color: $border; color: $muted; }

/* ---- inputs ---- */
QLineEdit, QComboBox, QSpinBox { background: $surface; border: 1px solid $border; border-radius: 8px;
    padding: 7px 10px; selection-background-color: $accent; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: $accent; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: $surface; border: 1px solid $border; selection-background-color: $accent;
    selection-color: #FFFFFF; outline: none; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1px solid $border; background: $surface; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: url("$check"); }

/* ---- progress ---- */
QProgressBar { background: $track; border: none; border-radius: 6px; height: 12px; text-align: center; color: transparent; }
QProgressBar::chunk { background: $accent; border-radius: 6px; }

/* ---- tables / trees ---- */
QTableView, QTreeView, QTableWidget { background: $surface; alternate-background-color: $surface_alt;
    border: 1px solid $border; border-radius: 10px; gridline-color: transparent; outline: none;
    selection-background-color: $accent; selection-color: #FFFFFF; }
QTableView::item, QTreeView::item, QTableWidget::item { padding: 5px 6px; border: none; }
QTableView::item:hover, QTreeView::item:hover { background: $hover; }
QTableView::item:selected, QTreeView::item:selected, QTableWidget::item:selected { background: $accent; color: #FFFFFF; }
QHeaderView::section { background: $surface; color: $muted; border: none; border-bottom: 1px solid $border;
    padding: 8px 8px; font-weight: 600; }
QPlainTextEdit { background: $surface; border: 1px solid $border; border-radius: 10px; padding: 6px;
    font-family: "Cascadia Mono", "Consolas", monospace; font-size: 9pt; }

/* ---- scrollbars ---- */
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: $track; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: $muted; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: $track; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: $muted; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }

QMenu { background: $surface; border: 1px solid $border; border-radius: 8px; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 5px; }
QMenu::item:selected { background: $accent; color: #FFFFFF; }
QStatusBar { background: $sidebar; color: $muted; border-top: 1px solid $border; }
QSplitter::handle { background: transparent; }
""")


_CHECK_ICON = asset_path("icons", "check.svg").as_posix()   # frozen-aware; quoted in the QSS


def build_stylesheet(p: Palette) -> str:
    return _QSS.substitute(p.__dict__, check=_CHECK_ICON)


def _qpalette(p: Palette) -> QPalette:
    qp = QPalette()
    for role, color in (
        (QPalette.Window, p.bg), (QPalette.WindowText, p.text), (QPalette.Base, p.surface),
        (QPalette.AlternateBase, p.surface_alt), (QPalette.Text, p.text),
        (QPalette.Button, p.surface_alt), (QPalette.ButtonText, p.text),
        (QPalette.ToolTipBase, p.surface_alt), (QPalette.ToolTipText, p.text),
        (QPalette.Highlight, p.accent), (QPalette.HighlightedText, "#FFFFFF"),
        (QPalette.PlaceholderText, p.muted),
    ):
        qp.setColor(role, QColor(color))
    return qp


def system_theme_name(app: QApplication) -> str:
    try:
        from PySide6.QtCore import Qt
        return "dark" if app.styleHints().colorScheme() == Qt.ColorScheme.Dark else "light"
    except Exception:  # noqa: BLE001
        return "dark"


def apply_theme(app: QApplication, name: str) -> Palette:
    """Apply 'dark', 'light' or 'system' to the whole application."""
    global _current
    if name == "system":
        name = system_theme_name(app)
    _current = PALETTES.get(name, DARK)
    app.setStyle("Fusion")
    app.setPalette(_qpalette(_current))
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(build_stylesheet(_current))
    return _current

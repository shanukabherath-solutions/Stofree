"""Reusable UI building blocks: cards, usage bar, charts, helpers."""
from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCharts import (
    QBarCategoryAxis, QBarSet, QChart, QChartView, QHorizontalBarSeries, QPieSeries,
    QValueAxis, QAbstractBarSeries,
)
from PySide6.QtCore import (
    QEasingCurve, QMargins, QPropertyAnimation, QRectF, Qt, QVariantAnimation, Signal,
)
from PySide6.QtGui import QBrush, QColor, QCursor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel, QSizePolicy,
    QToolTip, QVBoxLayout, QWidget,
)

from .. import theme
from ..utils.formatters import elide_middle, format_size

ANIMATIONS_ENABLED = True


def set_animations_enabled(flag: bool) -> None:
    global ANIMATIONS_ENABLED
    ANIMATIONS_ENABLED = bool(flag)


# --------------------------------------------------------------------------- helpers
def set_role(widget: QWidget, role: str) -> QWidget:
    widget.setProperty("role", role)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    return widget


def make_label(text: str = "", role: str = "", wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if role:
        lab.setProperty("role", role)
    lab.setWordWrap(wrap)
    return lab


def set_variant(button: QWidget, variant: str) -> None:
    button.setProperty("variant", variant)
    button.style().unpolish(button)
    button.style().polish(button)


def fade_in(widget: QWidget, duration: int = 220) -> None:
    """Subtle fade-in used when switching pages."""
    if not ANIMATIONS_ENABLED:
        return
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    widget._fade_anim = anim  # keep reference
    anim.start()


class ChoiceBox(QComboBox):
    """Drop-down of preset integer values with a spin-box-like value()/setValue() API."""

    valueChanged = Signal(int)

    def __init__(self, choices: Sequence[tuple[str, int]]) -> None:
        super().__init__()
        for label, val in choices:
            self.addItem(label, val)
        self.currentIndexChanged.connect(lambda _i: self.valueChanged.emit(self.value()))

    def value(self) -> int:
        return int(self.currentData())

    def setValue(self, v: int) -> None:  # noqa: N802
        idx = self.findData(int(v))
        if idx < 0:                         # keep unusual stored values selectable
            self.addItem(f"{int(v):,}", int(v))
            idx = self.count() - 1
        self.setCurrentIndex(idx)


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, object_name: str = "Card") -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setAttribute(Qt.WA_StyledBackground, True)


class PageHeader(QWidget):
    """Title + subtitle on the left, optional action widgets on the right."""

    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(make_label(title, "title"))
        if subtitle:
            col.addWidget(make_label(subtitle, "subtitle"))
        row.addLayout(col, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        row.addLayout(self.actions)

    def add_action(self, widget: QWidget) -> None:
        self.actions.addWidget(widget)


class StatTile(Card):
    def __init__(self, caption: str, value: str = "-") -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(0)
        self.value_label = make_label(value, "stat")
        lay.addWidget(self.value_label)
        lay.addWidget(make_label(caption, "statcaption"))

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)


class ElidedLabel(QLabel):
    """Label that elides the middle of long text (paths) instead of widening the layout."""

    def __init__(self, text: str = "") -> None:
        super().__init__()
        self._full = text
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(40)
        self._refresh()

    def setText(self, text: str) -> None:  # noqa: N802
        self._full = text
        self._refresh()

    def fullText(self) -> str:  # noqa: N802
        return self._full

    def _refresh(self) -> None:
        fm = QFontMetrics(self.font())
        width = max(self.width() - 4, 40)
        super().setText(fm.elidedText(self._full, Qt.ElideMiddle, width))

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._refresh()


class UsageBar(QWidget):
    """Rounded progress bar whose colour reflects how full a drive is; animates changes."""

    def __init__(self, height: int = 10, thresholds: bool = True) -> None:
        super().__init__()
        self.setFixedHeight(height)
        self._target = 0.0
        self._shown = 0.0
        self._thresholds = thresholds
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(500)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

    def value(self) -> float:
        return self._target

    def set_value(self, pct: float, animate: bool = True) -> None:
        pct = max(0.0, min(100.0, pct))
        self._anim.stop()
        if animate and ANIMATIONS_ENABLED:
            self._anim.setStartValue(self._shown)
            self._anim.setEndValue(pct)
            self._anim.start()
        else:
            self._shown = pct
            self.update()
        self._target = pct

    def _on_anim(self, v) -> None:
        self._shown = float(v)
        self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        p = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        radius = r.height() / 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(p.track))
        painter.drawRoundedRect(r, radius, radius)
        if self._shown > 0:
            color = p.accent
            if self._thresholds:
                color = p.success if self._target < 70 else p.warning if self._target < 90 else p.danger
            w = max(r.height(), r.width() * self._shown / 100.0)
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(QRectF(r.left(), r.top(), w, r.height()), radius, radius)


# --------------------------------------------------------------------------- charts
def _style_chart(chart: QChart, p: theme.Palette) -> None:
    chart.setTheme(QChart.ChartThemeDark if p.is_dark else QChart.ChartThemeLight)
    chart.setBackgroundVisible(False)
    chart.setBackgroundBrush(QBrush(Qt.transparent))
    chart.setMargins(QMargins(0, 0, 0, 0))
    chart.legend().setVisible(False)
    chart.setAnimationOptions(QChart.SeriesAnimations if ANIMATIONS_ENABLED else QChart.NoAnimation)


def _make_view(chart: QChart) -> QChartView:
    view = QChartView(chart)
    view.setRenderHint(QPainter.Antialiasing)
    view.setFrameShape(QFrame.NoFrame)
    view.setStyleSheet("background: transparent; border: none;")
    view.setBackgroundBrush(QBrush(Qt.transparent))
    return view


class PieChartWidget(QWidget):
    """Donut chart with centre text, hover highlighting and an optional legend row."""

    def __init__(self, hole: float = 0.64, show_legend: bool = True, min_height: int = 230) -> None:
        super().__init__()
        self._hole = hole
        self._show_legend = show_legend
        self._items: list[tuple[str, float, str]] = []
        self._fmt: Callable[[float], str] = format_size
        self._def_title = ""
        self._def_sub = ""

        self.chart = QChart()
        self.view = _make_view(self.chart)
        self.view.setMinimumHeight(min_height)

        self.center_title = make_label("", "pct")
        self.center_title.setAlignment(Qt.AlignCenter)
        self.center_sub = make_label("", "muted")
        self.center_sub.setAlignment(Qt.AlignCenter)
        center = QWidget()
        center.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addStretch(1)
        cl.addWidget(self.center_title)
        cl.addWidget(self.center_sub)
        cl.addStretch(1)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(self.view, 0, 0)
        grid.addWidget(center, 0, 0, Qt.AlignCenter)

        self.legend = QLabel()
        self.legend.setAlignment(Qt.AlignCenter)
        self.legend.setWordWrap(True)
        self.legend.setVisible(show_legend)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addLayout(grid, 1)
        root.addWidget(self.legend)

    # ---- API
    def set_data(self, items: Sequence[tuple[str, float, str]], center_title: str,
                 center_sub: str, formatter: Callable[[float], str] = format_size) -> None:
        self._items = [(n, float(v), c) for n, v, c in items]
        self._def_title, self._def_sub, self._fmt = center_title, center_sub, formatter
        self._render()

    def apply_theme(self, _p: theme.Palette | None = None) -> None:
        self._render()

    # ---- internals
    def _render(self) -> None:
        p = theme.palette()
        _style_chart(self.chart, p)
        self.chart.removeAllSeries()
        series = QPieSeries()
        series.setHoleSize(self._hole)
        series.setPieSize(0.92)
        total = sum(v for _, v, _ in self._items)
        visible = [(n, v, c) for n, v, c in self._items if v > 0]
        if not visible:
            visible = [("No data", 1.0, p.track)]
        for name, value, color in visible:
            s = series.append(name, value)
            s.setLabelVisible(False)
            s.setBrush(QColor(color))
            s.setPen(QPen(QColor(p.surface), 2))
            s.hovered.connect(lambda state, sl=s, n=name, v=value: self._on_hover(state, sl, n, v, total))
        self.chart.addSeries(series)
        self.center_title.setText(self._def_title)
        self.center_sub.setText(self._def_sub)
        if self._show_legend:
            parts = [f'<span style="color:{c}">&#9679;</span> {n} <b>{self._fmt(v)}</b>'
                     for n, v, c in self._items]
            self.legend.setText("&nbsp;&nbsp;&nbsp;".join(parts))

    def _on_hover(self, state: bool, sl, name: str, value: float, total: float) -> None:
        sl.setExploded(state)
        sl.setExplodeDistanceFactor(0.05)
        if state and total > 0:
            self.center_title.setText(f"{value / total * 100:.1f}%")
            self.center_sub.setText(f"{name} - {self._fmt(value)}")
        else:
            self.center_title.setText(self._def_title)
            self.center_sub.setText(self._def_sub)


class BarChartWidget(QWidget):
    """Horizontal bar chart (largest at top) with unit-scaled axis and hover tooltips."""

    UNITS = ("B", "KB", "MB", "GB", "TB")

    def __init__(self, empty_text: str = "No data") -> None:
        super().__init__()
        self.chart = QChart()
        self.view = _make_view(self.chart)
        self._empty = make_label(empty_text, "muted")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty_text = empty_text
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(self.view, 0, 0)
        grid.addWidget(self._empty, 0, 0, Qt.AlignCenter)
        self._items: list[tuple[str, int]] = []
        self._color: str | None = None

    def set_data(self, items: Sequence[tuple[str, int]], color: str | None = None,
                 empty_text: str | None = None) -> None:
        self._items = [(n, int(v)) for n, v in items if v > 0]
        self._color = color
        if empty_text:
            self._empty.setText(empty_text)
        self._render()

    def apply_theme(self, _p: theme.Palette | None = None) -> None:
        self._render()

    def _render(self) -> None:
        p = theme.palette()
        _style_chart(self.chart, p)
        for ax in self.chart.axes():
            self.chart.removeAxis(ax)
        self.chart.removeAllSeries()
        self._empty.setVisible(not self._items)
        self.view.setVisible(bool(self._items))
        if not self._items:
            return

        items = list(reversed(self._items))            # first item ends up on top
        max_v = max(v for _, v in items)
        exp = 0
        while exp < len(self.UNITS) - 1 and max_v / (1024 ** exp) >= 1024:
            exp += 1
        unit, div = self.UNITS[exp], 1024 ** exp

        bar_set = QBarSet("Size")
        bar_set.setColor(QColor(self._color or p.accent))
        bar_set.setBorderColor(QColor(self._color or p.accent))
        for _, v in items:
            bar_set.append(v / div)
        series = QHorizontalBarSeries()
        series.append(bar_set)
        series.setBarWidth(0.62)
        series.setLabelsVisible(True)
        series.setLabelsPosition(QAbstractBarSeries.LabelsOutsideEnd)
        series.setLabelsFormat(f"@value {unit}")
        series.setLabelsPrecision(3 if unit != "B" else 4)
        series.hovered.connect(lambda state, idx, _bs: self._on_hover(state, idx, items))
        self.chart.addSeries(series)

        cat = QBarCategoryAxis()
        cat.append([elide_middle(n, 26) for n, _ in items])
        cat.setLabelsColor(QColor(p.text))
        cat.setGridLineVisible(False)
        cat.setLinePenColor(QColor(p.border))
        self.chart.addAxis(cat, Qt.AlignLeft)
        series.attachAxis(cat)

        val = QValueAxis()
        val.setRange(0, max_v / div * 1.28)
        val.setLabelFormat("%.0f")
        val.applyNiceNumbers()
        val.setLabelsColor(QColor(p.muted))
        val.setGridLineColor(QColor(p.border))
        val.setLinePenColor(QColor(p.border))
        val.setTitleText(unit)
        val.setTitleBrush(QBrush(QColor(p.muted)))
        self.chart.addAxis(val, Qt.AlignBottom)
        series.attachAxis(val)
        self.view.setMinimumHeight(60 + 30 * len(items))

    def _on_hover(self, state: bool, idx: int, items: list[tuple[str, int]]) -> None:
        if state and 0 <= idx < len(items):
            name, size = items[idx]
            QToolTip.showText(QCursor.pos(), f"{name}\n{format_size(size)}", self.view)
        else:
            QToolTip.hideText()

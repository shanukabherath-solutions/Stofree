"""Animated startup splash screen.

Shows the main logo (``assets/branding/logo.png``) and plays the supplied
``assets/branding/Ani.gif`` with ``QMovie`` (no re-creation of the animation) beside it as the
loading indicator. The card is light because both pieces of artwork are designed for light
backgrounds.

Behaviour
---------
* Never blocks the GUI thread: it uses timers only (no sleeping) so the animation keeps
  playing while the main window is being prepared.
* ``finish()`` closes the splash once the minimum display time has elapsed, then emits
  ``finished``. It is idempotent, so the splash can never be shown twice.
* If the GIF cannot be loaded the splash shows the logo only; if neither asset can be
  loaded ``StartupSplash.create()`` returns ``None`` and start-up simply continues.
"""
from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImageReader, QMovie, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..utils import assets
from ..utils.constants import APP_NAME, APP_SUBTITLE
from ..utils.logger import get_logger
from .branding import scaled_logo

log = get_logger("splash")

CARD_BG = QColor("#FFFFFF")
CARD_BORDER = QColor("#D9DEE8")
GIF_BOX = QSize(190, 190)          # the GIF is scaled to fit inside this, ratio preserved
LOGO_WIDTH = 250                   # main logo (square emblem) width
MIN_DURATION_MS = 1360             # two full loops of the 680 ms animation
FADE_MS = 160


def fit_keep_aspect(size: QSize, box: QSize) -> QSize:
    """Largest size with the aspect ratio of ``size`` that fits inside ``box``."""
    if size.width() <= 0 or size.height() <= 0:
        return QSize(box)
    return size.scaled(box, Qt.KeepAspectRatio)


class StartupSplash(QWidget):
    finished = Signal()

    def __init__(self, min_duration_ms: int = MIN_DURATION_MS) -> None:
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowTitle(APP_NAME)
        self._min_ms = min_duration_ms
        self._finish_requested = False
        self._done = False
        self._shown_at = QTimer(self)
        self._shown_at.setSingleShot(True)
        self._min_elapsed = False

        self.movie: QMovie | None = None
        self.gif_size = QSize()
        self.has_logo = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 30, 36, 24)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignHCenter)

        # ---- main logo (original logo.png, proportional) beside the animation
        row = QHBoxLayout()
        row.setSpacing(18)
        row.setAlignment(Qt.AlignHCenter)

        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setStyleSheet("background: transparent;")
        pm = scaled_logo(LOGO_WIDTH, self.devicePixelRatioF() or 1.0)
        if pm is not None:
            self.logo_label.setPixmap(pm)
            self.has_logo = True
        else:
            self.logo_label.setText(APP_NAME)
            self.logo_label.setStyleSheet("background: transparent; color: #1E1B18; "
                                          "font-size: 30pt; font-weight: 700;")
        row.addWidget(self.logo_label, 0, Qt.AlignVCenter)

        # ---- animation (the real GIF, via QMovie)
        self.gif_label = QLabel()
        self.gif_label.setAlignment(Qt.AlignCenter)
        self.gif_label.setStyleSheet("background: transparent;")
        self._setup_movie()
        if self.movie is not None:
            row.addWidget(self.gif_label, 0, Qt.AlignVCenter)
        lay.addLayout(row)

        sub = QLabel(APP_SUBTITLE)
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("background: transparent; color: #5E6A80; font-size: 10pt;")
        lay.addWidget(sub)
        self.status = QLabel("Starting...")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("background: transparent; color: #8A93A6; font-size: 8.5pt;")
        lay.addSpacing(6)
        lay.addWidget(self.status)
        gif_w = GIF_BOX.width() + 18 if self.movie is not None else 0
        self.setFixedWidth(LOGO_WIDTH + gif_w + 72)
        self.adjustSize()

    # ------------------------------------------------------------------ construction
    @classmethod
    def create(cls, min_duration_ms: int = MIN_DURATION_MS) -> "StartupSplash | None":
        """Build a splash, or ``None`` when neither the GIF nor the logo can be loaded."""
        splash = cls(min_duration_ms)
        if splash.movie is None and not splash.has_logo:
            log.warning("No splash artwork available; skipping splash screen.")
            splash.deleteLater()
            return None
        return splash

    @property
    def animated(self) -> bool:
        return self.movie is not None

    def _setup_movie(self) -> None:
        path = assets.branding_path(assets.SPLASH_GIF_FILE)
        if path is None:
            return
        reader = QImageReader(str(path))
        native = reader.size()                       # reads the header only (fast)
        movie = QMovie(str(path))
        if not movie.isValid() or movie.frameCount() == 0 and not native.isValid():
            log.warning("Splash GIF could not be loaded: %s", path)
            return
        self.gif_size = fit_keep_aspect(native if native.isValid() else GIF_BOX, GIF_BOX)
        movie.setScaledSize(self.gif_size)           # same ratio as the source: no distortion
        movie.setCacheMode(QMovie.CacheAll)          # decode each frame once
        self.gif_label.setFixedSize(self.gif_size)
        self.gif_label.setMovie(movie)
        self.movie = movie

    # ------------------------------------------------------------------ painting
    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(CARD_BORDER, 1))
        p.setBrush(CARD_BG)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 18, 18)

    # ------------------------------------------------------------------ lifecycle
    def show_centered(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(geo.center() - self.rect().center())
        self.show()
        if self.movie is not None:
            self.movie.start()
        self._shown_at.timeout.connect(self._on_min_elapsed)
        self._shown_at.start(self._min_ms)

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def _on_min_elapsed(self) -> None:
        self._min_elapsed = True
        if self._finish_requested:
            self._close_now()

    def finish(self) -> None:
        """Ask the splash to close once the minimum display time has passed."""
        if self._done:
            return
        self._finish_requested = True
        if self._min_elapsed or not self.isVisible():
            self._close_now()

    def _close_now(self) -> None:
        if self._done:
            return
        self._done = True
        self._shown_at.stop()
        # Emit as soon as the window is allowed to appear; the fade-out overlaps it.
        self.finished.emit()
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(FADE_MS)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self._teardown)
        self._fade = anim
        anim.start()

    def _teardown(self) -> None:
        if self.movie is not None:
            self.movie.stop()
        self.close()
        self.deleteLater()

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.movie is not None:
            self.movie.stop()
        self._done = True
        super().closeEvent(e)

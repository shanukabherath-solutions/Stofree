"""Branding, splash screen and start-up sequencing (headless, offscreen)."""
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QImageReader

from app import launcher as launcher_mod
from app.launcher import Launcher, set_windows_app_id
from app.main_window import MainWindow
from app.state import AppState
from app.ui import branding
from app.ui.splash import StartupSplash, fit_keep_aspect
from app.utils import assets
from app.utils.constants import APP_NAME, APP_SUBTITLE

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def fresh_asset_caches():
    assets.load_pixmap.cache_clear()
    branding.reset_icon_cache()
    yield
    assets.load_pixmap.cache_clear()
    branding.reset_icon_cache()


@pytest.fixture
def make_window(qtbot, tmp_path):
    made = []

    def factory(auto_refresh=True):
        st = AppState(QSettings(str(tmp_path / f"s{len(made)}.ini"), QSettings.IniFormat))
        w = MainWindow(st, auto_refresh=auto_refresh)
        qtbot.addWidget(w)
        made.append(w)
        return w

    yield factory
    for w in made:
        w.state.wait_for_scan()


def is_visible(widget) -> bool:
    """The splash deletes itself when closed; a deleted widget counts as not visible."""
    try:
        return widget.isVisible()
    except RuntimeError:
        return False


# ----------------------------------------------------------------------------- logo / icon
def test_emblem_badge_uses_main_logo_with_correct_proportions(qtbot):
    badge = branding.EmblemBadge(width=200)
    qtbot.addWidget(badge)
    assert badge.has_logo
    pm = badge.logo_pixmap()
    assert pm.width() == pm.height() == 200                      # logo.png is square: stays square
    assert pm.hasAlphaChannel()


def test_emblem_badge_falls_back_to_text_when_logo_missing(qtbot, monkeypatch):
    monkeypatch.setattr(assets, "load_pixmap", lambda name: None)
    badge = branding.EmblemBadge(width=200)
    qtbot.addWidget(badge)
    assert not badge.has_logo and badge.label.text() == APP_NAME


def test_wordmark_follows_theme_and_keeps_aspect_ratio(qtbot):
    from app import theme
    wm = branding.ThemedWordmark(width=240)
    qtbot.addWidget(wm)
    wm.apply_theme(theme.DARK)
    assert wm.has_logo and wm.current_file == "darkmode_logo.png"
    dark_ratio = wm.pixmap().width() / wm.pixmap().height()
    assert abs(dark_ratio - 2000 / 473) < 0.06
    wm.apply_theme(theme.LIGHT)
    assert wm.current_file == "lightmode_logo.png"
    assert abs(wm.pixmap().width() / wm.pixmap().height() - 2000 / 473) < 0.06
    wm.apply_theme(theme.DARK)
    assert wm.current_file == "darkmode_logo.png"


def test_wordmark_falls_back_to_text_when_image_missing(qtbot, monkeypatch):
    from app import theme
    real = assets.load_pixmap
    monkeypatch.setattr(assets, "load_pixmap", lambda n: None if n == "darkmode_logo.png" else real(n))
    wm = branding.ThemedWordmark(width=200)
    qtbot.addWidget(wm)
    wm.apply_theme(theme.DARK)                                  # dark file missing -> text
    assert not wm.has_logo and wm.text() == APP_NAME
    wm.apply_theme(theme.LIGHT)                                 # light file present -> image again
    assert wm.has_logo and wm.text() == ""


def test_app_icon_is_multi_resolution_and_square():
    icon = branding.app_icon()
    assert not icon.isNull()
    sizes = {(s.width(), s.height()) for s in icon.availableSizes()}
    assert {(16, 16), (32, 32), (256, 256)} <= sizes
    assert all(w == h for w, h in sizes)


def test_app_icon_null_without_logo(monkeypatch):
    monkeypatch.setattr(assets, "load_logo", lambda: None)
    assert branding.app_icon().isNull()


def test_icon_is_transparent_trimmed_and_proportional():
    img = branding.render_icon_pixmap(256).toImage()
    assert img.width() == img.height() == 256
    assert img.pixelColor(0, 0).alpha() == 0                      # transparency preserved (no plate)
    assert img.pixelColor(128, 128).alpha() == 255                # emblem fills the centre
    xs = [x for x in range(256) for y in range(0, 256, 4) if img.pixelColor(x, y).alpha() > 40]
    ys = [y for y in range(256) for x in range(0, 256, 4) if img.pixelColor(x, y).alpha() > 40]
    w, h = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
    assert h > 230                                                # trimmed margins -> fills the icon
    assert abs(w / h - 1487 / 1627) < 0.03                        # original emblem proportions kept


# ----------------------------------------------------------------------------- window identity
def test_window_identity_and_branding_text(make_window):
    w = make_window()
    assert w.windowTitle() == f"{APP_NAME} - {APP_SUBTITLE}" == "Stofree - Windows Disk Space Analyzer"
    assert not w.windowIcon().isNull()
    assert w.brand_header.subtitle.text() == "Windows Disk Space Analyzer"
    assert w.brand_header.logo.has_logo and w.brand_header.has_compact
    assert w.dashboard.brand_logo.has_logo
    assert w.settings_page.about_logo.has_logo


def test_dashboard_and_sidebar_logo_switch_with_theme(make_window, qtbot):
    w = make_window()
    w.show()
    w.state.set_theme("dark")
    assert w.dashboard.brand_logo.current_file == "darkmode_logo.png"
    assert w.brand_header.logo.current_file == "darkmode_logo.png"
    w.state.set_theme("light")
    assert w.dashboard.brand_logo.current_file == "lightmode_logo.png"
    assert w.brand_header.logo.current_file == "lightmode_logo.png"
    w._toggle_theme()                                           # toolbar toggle swaps it back
    assert w.dashboard.brand_logo.current_file == "darkmode_logo.png"
    w.state.set_theme("system")
    from app import theme
    expected = "darkmode_logo.png" if theme.palette().is_dark else "lightmode_logo.png"
    assert w.dashboard.brand_logo.current_file == expected


def test_sidebar_shows_compact_icon_when_collapsed(make_window, qtbot):
    w = make_window()
    w.show()                                            # resize events need a visible window
    w.resize(1200, 800)
    qtbot.waitUntil(lambda: w.sidebar.width() > 150)
    assert w.brand_header.compact.isHidden()            # full logo shown while wide
    w.resize(880, 700)
    qtbot.waitUntil(lambda: w.sidebar.width() < 100)
    assert w.brand_header.logo.isHidden() and not w.brand_header.compact.isHidden()
    w.resize(1200, 800)
    qtbot.waitUntil(lambda: w.sidebar.width() > 150)
    assert not w.brand_header.logo.isHidden() and w.brand_header.compact.isHidden()


def test_no_old_name_in_user_facing_strings():
    for py in list((ROOT / "app").rglob("*.py")) + [ROOT / "main.py"]:
        assert "winspace" not in py.read_text(encoding="utf-8").lower(), py


def test_exports_and_defaults_use_new_name(make_window, qtbot, tmp_path):
    from app.core.disk_scanner import DiskScanner
    from app.core.report_generator import build_json
    (tmp_path / "t").mkdir()
    (tmp_path / "t" / "a.txt").write_text("x")
    data = build_json(DiskScanner().scan(str(tmp_path / "t")))
    assert data["generator"].startswith("Stofree ")
    w = make_window()
    assert os.path.basename(w.reports._default_name("files", "csv")).startswith("stofree_")


def test_windows_app_id_set_only_on_windows(monkeypatch):
    assert set_windows_app_id() is False or sys.platform == "win32"
    import ctypes
    calls = []
    fake = SimpleNamespace(shell32=SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=calls.append))
    monkeypatch.setattr(ctypes, "windll", fake, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    assert set_windows_app_id("Stofree.Test") is True and calls == ["Stofree.Test"]


# ----------------------------------------------------------------------------- splash
def test_splash_plays_the_real_gif_with_qmovie(qtbot):
    splash = StartupSplash.create(min_duration_ms=100)
    qtbot.addWidget(splash)
    assert splash.animated and splash.has_logo
    movie = splash.movie
    assert movie.isValid() and movie.frameCount() == 4
    assert movie.fileName().endswith("Ani.gif")
    frames = []
    movie.frameChanged.connect(frames.append)
    splash.show_centered()
    qtbot.waitUntil(lambda: len(set(frames)) >= 3, timeout=5000)
    assert movie.state() == movie.MovieState.Running


def test_splash_uses_main_logo_png(qtbot):
    splash = StartupSplash.create()
    qtbot.addWidget(splash)
    pm = splash.logo_label.pixmap()
    assert splash.has_logo and pm.width() == pm.height()          # the square emblem, not a wordmark
    expected = assets.load_logo().scaledToWidth(pm.width(), Qt.SmoothTransformation)
    assert expected.toImage().size() == pm.toImage().size()


def test_splash_gif_is_not_distorted(qtbot):
    splash = StartupSplash.create()
    qtbot.addWidget(splash)
    native = QImageReader(str(assets.branding_path("Ani.gif"))).size()
    shown = splash.gif_size
    assert abs(shown.width() / shown.height() - native.width() / native.height()) < 0.01
    # generic helper keeps ratio for non-square sources too
    assert fit_keep_aspect(QSize(400, 200), QSize(300, 300)) == QSize(300, 150)
    assert fit_keep_aspect(QSize(200, 400), QSize(300, 300)) == QSize(150, 300)


def test_splash_closes_after_minimum_time_and_only_once(qtbot):
    splash = StartupSplash.create(min_duration_ms=400)      # self-deleting: not added to qtbot
    emitted = []
    splash.finished.connect(lambda: emitted.append(time.monotonic()))
    t0 = time.monotonic()
    splash.show_centered()
    splash.finish()                                    # requested immediately...
    qtbot.wait(150)
    assert not emitted and is_visible(splash)          # ...but kept up for the minimum time
    qtbot.waitUntil(lambda: bool(emitted), timeout=3000)
    assert emitted[0] - t0 >= 0.38
    splash.finish(); splash.finish()
    qtbot.wait(300)
    assert len(emitted) == 1                           # idempotent


def test_splash_without_gif_shows_logo_only(qtbot, monkeypatch):
    real = assets.branding_path
    monkeypatch.setattr(assets, "branding_path",
                        lambda n: None if n == assets.SPLASH_GIF_FILE else real(n))
    splash = StartupSplash.create(min_duration_ms=50)
    qtbot.addWidget(splash)
    assert splash is not None and not splash.animated and splash.has_logo


def test_splash_with_corrupt_gif_degrades_gracefully(qtbot, tmp_path, monkeypatch):
    branding_dir = tmp_path / "assets" / "branding"
    branding_dir.mkdir(parents=True)
    (branding_dir / "Ani.gif").write_bytes(b"GIF89a-garbage")
    (branding_dir / "logo.png").write_bytes((ROOT / "assets" / "branding" / "logo.png").read_bytes())
    monkeypatch.setenv("STOFREE_ASSETS", str(tmp_path))
    assets.load_pixmap.cache_clear()
    splash = StartupSplash.create(min_duration_ms=50)
    qtbot.addWidget(splash)
    assert splash is not None and not splash.animated and splash.has_logo


def test_splash_skipped_when_no_artwork_at_all(qtbot, tmp_path, monkeypatch):
    (tmp_path / "assets" / "branding").mkdir(parents=True)
    monkeypatch.setenv("STOFREE_ASSETS", str(tmp_path))
    assets.load_pixmap.cache_clear()
    assert StartupSplash.create() is None


# ----------------------------------------------------------------------------- launcher
def test_launcher_shows_main_window_then_splash_closes(make_window, qtbot):
    w = make_window(auto_refresh=False)
    splash = StartupSplash.create(min_duration_ms=300)      # self-deleting: not added to qtbot
    splash.show_centered()
    lau = Launcher(w, splash)
    assert not w.isVisible()
    lau.start()                                         # async drive detection
    qtbot.waitUntil(lambda: lau.revealed, timeout=8000)
    assert w.isVisible() and w.state.drives is not None
    assert w.stack.currentIndex() == 0                  # dashboard opens first
    assert len(w.dashboard.cards) == len(w.state.drives)
    qtbot.waitUntil(lambda: not is_visible(splash), timeout=3000)


def test_launcher_without_splash(make_window, qtbot):
    w = make_window(auto_refresh=False)
    lau = Launcher(w, None)
    lau.start()
    qtbot.waitUntil(lambda: lau.revealed, timeout=8000)
    assert w.isVisible()


def test_launcher_failsafe_timeout_opens_window(make_window, qtbot):
    w = make_window(auto_refresh=False)
    lau = Launcher(w, None, timeout_ms=150)             # start() never called: drives never arrive
    qtbot.waitUntil(lambda: lau.revealed, timeout=3000)
    assert w.isVisible()


def test_navigation_never_recreates_the_splash(make_window, qtbot, monkeypatch):
    created = []
    real_init = StartupSplash.__init__
    monkeypatch.setattr(StartupSplash, "__init__", lambda self, *a, **k: (created.append(1), real_init(self, *a, **k))[1])
    w = make_window()
    w.show()
    for i in list(range(7)) + list(range(7)):
        w.goto(i)
    assert created == []


def test_refresh_button_uses_worker_thread_and_updates_dashboard(make_window, qtbot):
    w = make_window()
    n = len(w.state.drives)
    with qtbot.waitSignal(w.state.drives_changed, timeout=8000):
        w.dashboard.refresh_btn.click()
    assert len(w.state.drives) == n and len(w.dashboard.cards) == n


# ----------------------------------------------------------------------------- real entry point
@pytest.mark.parametrize("flags", [[], ["--no-splash"]])
def test_main_py_starts_and_opens_dashboard(tmp_path, flags):
    """Launch the real entry point in a subprocess and confirm the window is shown."""
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", HOME=str(tmp_path),
               XDG_CONFIG_HOME=str(tmp_path / "cfg"), XDG_DATA_HOME=str(tmp_path / "data"),
               PYTHONUNBUFFERED="1")
    proc = subprocess.Popen([sys.executable, str(ROOT / "main.py"), *flags], cwd=ROOT, env=env,
                            stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
    lines: list[str] = []
    import threading
    reader = threading.Thread(target=lambda: [lines.append(ln) for ln in proc.stderr], daemon=True)
    reader.start()                       # a reader thread avoids select()-vs-buffering pitfalls
    try:
        deadline = time.time() + 30
        while time.time() < deadline and proc.poll() is None \
                and not any("Main window shown" in ln for ln in lines):
            time.sleep(0.1)
        log = "".join(lines)
        assert "Main window shown" in log, f"window never shown. stderr so far:\n{log}"
        assert proc.poll() is None, "application exited unexpectedly"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        reader.join(timeout=5)
        proc.stderr.close()
    assert "Traceback" not in "".join(lines)

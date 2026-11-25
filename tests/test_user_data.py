"""Where Stofree writes its data, settings migration, and resilience to missing resources."""
import json
import logging
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from app.utils import assets, paths, settings_store

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def local_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    return tmp_path / "LocalAppData"


# ------------------------------------------------------------------ data locations
def test_user_data_lives_under_localappdata_stofree(local_appdata):
    assert paths.user_data_dir() == local_appdata / "Stofree"
    assert paths.settings_file() == local_appdata / "Stofree" / "settings.ini"
    assert paths.log_dir() == local_appdata / "Stofree" / "logs"


def test_user_data_is_never_inside_the_pyinstaller_bundle(tmp_path, monkeypatch, local_appdata):
    bundle = tmp_path / "_MEI99999"
    (bundle / "assets").mkdir(parents=True)
    monkeypatch.delenv("STOFREE_ASSETS", raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    for p in (paths.user_data_dir(), paths.settings_file(), paths.log_dir()):
        assert bundle not in p.parents and p != bundle
        assert assets.base_dir() not in p.parents


def test_logger_reexports_log_dir(local_appdata):
    from app.utils.logger import log_dir
    assert log_dir() == paths.log_dir()


def test_no_stream_handler_when_stderr_is_missing(tmp_path, monkeypatch):
    """Windowed PyInstaller builds have sys.stderr == None."""
    logger = logging.getLogger("stofree")
    saved = (list(logger.handlers), getattr(logger, "_stofree_configured", None),
             getattr(logger, "_stofree_logfile", None))
    try:
        for h in list(logger.handlers):
            logger.removeHandler(h)
        logger._stofree_configured = False
        monkeypatch.setattr(sys, "stderr", None)
        logfile = __import__("app.utils.logger", fromlist=["x"]).setup_logging(directory=tmp_path)
        plain = [h for h in logger.handlers if type(h) is logging.StreamHandler]
        files = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert not plain and files and logfile == tmp_path / "stofree.log"
    finally:
        for h in list(logger.handlers):
            logger.removeHandler(h)
            h.close()
        for h in saved[0]:
            logger.addHandler(h)
        logger._stofree_configured, logger._stofree_logfile = saved[1], saved[2]


# ------------------------------------------------------------------ settings file
def test_settings_are_an_ini_file_not_the_registry(tmp_path):
    ini = tmp_path / "Stofree" / "settings.ini"
    s = settings_store.create_settings(ini)
    s.setValue("theme", "light")
    s.sync()
    assert ini.is_file() and "theme=light" in ini.read_text(encoding="utf-8")
    assert s.format() == QSettings.IniFormat


def test_last_scan_json_with_commas_round_trips(qapp, tmp_path):
    from app.state import AppState
    ini = tmp_path / "s.ini"
    st = AppState(settings_store.create_settings(ini))
    payload = {"C:\\": {"files": 1, "folders": 2, "bytes": 3}}
    st.settings.setValue("last_scans", json.dumps(payload))
    st.settings.sync()
    st2 = AppState(settings_store.create_settings(ini))
    assert st2.last_scans == payload


def test_last_scans_tolerates_comma_split_list(qapp, tmp_path):
    """An INI value edited by hand may be read back as a list; it must not be lost or crash."""
    from app.state import AppState
    s = QSettings(str(tmp_path / "x.ini"), QSettings.IniFormat)
    s.setValue("last_scans", ['{"C:\\\\": {"files": 1', ' "folders": 2}}'])
    assert AppState(s).last_scans == {"C:\\": {"files": 1, "folders": 2}}


def test_legacy_settings_are_migrated_once(tmp_path):
    native_dir = tmp_path / "native"
    native_dir.mkdir()
    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(native_dir))
    legacy = QSettings("Stofree", "Stofree")
    legacy.setValue("theme", "light")
    legacy.setValue("top_files_limit", 5000)
    legacy.sync()
    target = QSettings(str(tmp_path / "new.ini"), QSettings.IniFormat)
    assert settings_store._migrate_legacy(target) == 2
    assert target.value("theme") == "light" and int(target.value("top_files_limit")) == 5000
    assert settings_store._migrate_legacy(target) == 0          # never overwrites existing settings
    legacy.clear()
    legacy.sync()


def test_create_settings_survives_unwritable_location(tmp_path):
    blocker = tmp_path / "file_not_dir"
    blocker.write_text("x")
    s = settings_store.create_settings(blocker / "sub" / "settings.ini")   # parent cannot be created
    assert s is not None                                                   # no exception


# ------------------------------------------------------------------ missing resources
def _clear_caches():
    from app.ui import branding, icons
    assets.load_pixmap.cache_clear()
    branding.reset_icon_cache()
    icons._cache.clear()


def test_application_starts_without_any_bundled_assets(qapp, tmp_path, monkeypatch):
    """Deleted/missing logo, GIF and icons must degrade gracefully, never crash."""
    (tmp_path / "assets").mkdir()
    monkeypatch.setenv("STOFREE_ASSETS", str(tmp_path))
    _clear_caches()
    try:
        from app import theme
        from app.main_window import MainWindow
        from app.state import AppState
        from app.ui.icons import icon
        from app.ui.splash import StartupSplash
        assert icon("drive").isNull()                               # missing SVG -> empty icon
        assert StartupSplash.create() is None                       # no artwork -> no splash
        assert theme.build_stylesheet(theme.DARK)                   # QSS still builds
        win = MainWindow(AppState(QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat)),
                         auto_refresh=False)
        win.close()
    finally:
        monkeypatch.delenv("STOFREE_ASSETS")
        _clear_caches()


def test_stylesheet_check_icon_url_is_quoted():
    """The installed path (C:/Program Files/...) contains a space, so url() must be quoted."""
    from app import theme
    qss = theme.build_stylesheet(theme.DARK)
    assert 'image: url("' in qss and "check.svg" in qss


# ------------------------------------------------------------------ built-in self test
def test_selftest_passes_from_source(qapp, local_appdata, tmp_path):
    from app.selftest import run_selftest
    out = tmp_path / "report.json"
    assert run_selftest(str(out)) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["ok"] and len(report["results"]) >= 9 and all(r["ok"] for r in report["results"])


def test_selftest_reports_failure_for_missing_assets(qapp, local_appdata, tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    monkeypatch.setenv("STOFREE_ASSETS", str(tmp_path))
    _clear_caches()
    try:
        from app.selftest import run_selftest
        out = tmp_path / "bad.json"
        assert run_selftest(str(out)) == 1
        report = json.loads(out.read_text(encoding="utf-8"))
        failed = {r["check"] for r in report["results"] if not r["ok"]}
        assert "bundled assets" in failed
    finally:
        monkeypatch.delenv("STOFREE_ASSETS")
        _clear_caches()


def test_selftest_argument_parsing(monkeypatch):
    from app.selftest import parse_selftest_args
    monkeypatch.delenv("STOFREE_SELFTEST_OUTPUT", raising=False)
    assert parse_selftest_args(["Stofree.exe"]) == (False, None)
    assert parse_selftest_args(["Stofree.exe", "--self-test"]) == (True, None)
    assert parse_selftest_args(["Stofree.exe", "--self-test", "r.json"]) == (True, "r.json")
    assert parse_selftest_args(["Stofree.exe", "--self-test", "--no-splash"]) == (True, None)

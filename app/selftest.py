"""Headless self-test used to verify a packaged (PyInstaller) build.

    Stofree.exe --self-test [report.json]

A windowed executable has no console, so results are written as JSON to ``report.json`` (if
given) and reported through the process exit code (0 = every check passed). Nothing is shown
on screen, nothing outside a temporary folder is modified, and the real user settings are not
touched. Scanning is read-only, as always.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable

from .utils import assets
from .utils.constants import APP_NAME, APP_VERSION
from .utils.paths import user_data_dir

BRANDING_FILES = (assets.LOGO_FILE, assets.LOGO_DARK_FILE, assets.LOGO_LIGHT_FILE,
                  assets.SPLASH_GIF_FILE, assets.ICON_FILE)
UI_ICONS = ("dashboard", "scanner", "largest_files", "folder_explorer", "file_types", "reports",
            "settings", "drive", "play", "stop", "refresh", "export", "check", "sun", "moon")


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _make_tree(root: Path) -> tuple[int, int]:
    """Small known tree; returns (file_count, total_bytes)."""
    files = {"a.txt": 100, "b.png": 2000, "docs/c.pdf": 5000, "docs/deep/d.zip": 7000,
             "media/e.mp4": 30000}
    for rel, size in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * size)
    return len(files), sum(files.values())


# ---------------------------------------------------------------------------- checks
def check_assets() -> str:
    missing = [n for n in BRANDING_FILES if assets.branding_path(n) is None]
    missing += [f"icons/{n}.svg" for n in UI_ICONS if not assets.asset_path("icons", f"{n}.svg").is_file()]
    if missing:
        raise AssertionError(f"missing bundled assets: {', '.join(missing)}")
    return f"all present under {assets.base_dir()}"


def check_images() -> str:
    from PySide6.QtGui import QMovie
    if assets.load_logo() is None:
        raise AssertionError("logo.png could not be decoded")
    gif = assets.branding_path(assets.SPLASH_GIF_FILE)
    movie = QMovie(str(gif))
    if not movie.isValid() or movie.frameCount() < 2:
        raise AssertionError("Ani.gif is not a valid animation (GIF image plugin missing?)")
    return f"logo ok; Ani.gif {movie.frameCount()} frames"


def check_icons() -> str:
    from .ui.branding import app_icon
    from .ui.icons import icon
    bad = [n for n in UI_ICONS if icon(n, "#000000", 20).isNull()]
    if bad:
        raise AssertionError(f"SVG icons failed to render (QtSvg missing?): {bad}")
    if app_icon().isNull():
        raise AssertionError("application icon is null")
    return "SVG + application icon render"


def check_splash_and_window(tmp: Path) -> str:
    from PySide6.QtCore import QSettings

    from .main_window import MainWindow
    from .state import AppState
    from .ui.splash import StartupSplash
    splash = StartupSplash.create()
    if splash is None or splash.movie is None or not splash.has_logo:
        raise AssertionError("splash could not be created with logo and animation")
    splash.close()
    state = AppState(QSettings(str(tmp / "selftest_settings.ini"), QSettings.IniFormat))
    win = MainWindow(state, auto_refresh=False)       # built but never shown
    win.close()
    return "splash (logo + GIF) and main window (incl. Qt Charts) construct"


def check_data_dir() -> str:
    d = user_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle and _inside(d, Path(bundle)):
        raise AssertionError(f"data dir {d} is inside the PyInstaller bundle")
    probe = d / ".selftest-write-check"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
    return f"{d} is writable and outside the bundle"


def check_settings(tmp: Path) -> str:
    from .utils.settings_store import create_settings
    ini = tmp / "roundtrip.ini"
    s = create_settings(ini)
    payload = json.dumps({"C:\\": {"files": 1, "folders": 2}})     # contains commas
    s.setValue("last_scans", payload)
    s.setValue("theme", "light")
    s.sync()
    s2 = create_settings(ini)
    got = s2.value("last_scans")
    if str(got) != payload or s2.value("theme") != "light":
        raise AssertionError(f"INI round-trip mismatch: {got!r}")
    return "INI settings round-trip"


def check_drives() -> str:
    from .core.drive_manager import list_drives
    drives = list_drives(include_removable=True)
    if not drives:
        raise AssertionError("no drives detected")
    return ", ".join(d.mountpoint for d in drives[:6])


def check_scan_and_export(tmp: Path) -> str:
    from .core import report_generator as rg
    from .core.disk_scanner import DiskScanner
    tree = tmp / "tree"
    n_files, n_bytes = _make_tree(tree)
    result = DiskScanner(top_files_limit=100).scan(str(tree))
    if (result.total_files, result.total_size) != (n_files, n_bytes) or result.cancelled:
        raise AssertionError(f"scan totals wrong: {result.total_files} files / {result.total_size} bytes")
    if not result.top_files or result.top_files[0].size != 30000:
        raise AssertionError("largest-file analysis wrong")
    if not result.type_stats.category_rows():
        raise AssertionError("file-type analysis empty")
    if len(result.root.children) < 2:
        raise AssertionError("folder analysis empty")
    out = tmp / "out"
    out.mkdir()
    rg.export_files_csv(result, out / "files.csv")
    rg.export_folders_csv(result, out / "folders.csv")
    rg.export_json(result, out / "report.json")
    for name in ("files.csv", "folders.csv", "report.json"):
        if (out / name).stat().st_size == 0:
            raise AssertionError(f"{name} is empty")
    json.loads((out / "report.json").read_text(encoding="utf-8"))
    return f"{n_files} files / {n_bytes} bytes scanned; CSV + JSON exported"


def check_cancel(tmp: Path) -> str:
    from .core.disk_scanner import DiskScanner
    tree = tmp / "cancel_tree"
    for i in range(40):
        (tree / f"d{i}").mkdir(parents=True)
        (tree / f"d{i}" / "f.bin").write_bytes(b"x" * 10)
    cancel = threading.Event()
    cancel.set()                                   # cancelled before traversal starts
    result = DiskScanner().scan(str(tree), cancel_event=cancel)
    if not result.cancelled or result.total_files >= 40:
        raise AssertionError("scan did not honour cancellation")
    return "cancelled scan stops and returns a partial result"


# ---------------------------------------------------------------------------- runner
def run_selftest(output: str | None = None) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="stofree-selftest-"))
    checks: list[tuple[str, Callable[[], str]]] = [
        ("bundled assets", check_assets),
        ("image decoding (logo, GIF)", check_images),
        ("icons", check_icons),
        ("splash + main window", lambda: check_splash_and_window(tmp)),
        ("user data folder", check_data_dir),
        ("settings file", lambda: check_settings(tmp)),
        ("drive detection", check_drives),
        ("scan, analysis, export", lambda: check_scan_and_export(tmp)),
        ("scan cancellation", lambda: check_cancel(tmp)),
    ]
    results = []
    for name, fn in checks:
        try:
            results.append({"check": name, "ok": True, "detail": fn()})
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            results.append({"check": name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
    shutil.rmtree(tmp, ignore_errors=True)
    ok = all(r["ok"] for r in results)
    report = {"app": APP_NAME, "version": APP_VERSION, "ok": ok,
              "frozen": bool(getattr(sys, "frozen", False)), "python": sys.version.split()[0],
              "platform": sys.platform, "bundle_dir": str(assets.base_dir()),
              "executable": sys.executable, "results": results}
    if output:
        try:
            Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
        except OSError:
            ok = False
    return 0 if ok else 1


def parse_selftest_args(argv: list[str]) -> tuple[bool, str | None]:
    """``(requested, output_path)`` from ``--self-test [path]``."""
    if "--self-test" not in argv:
        return False, None
    i = argv.index("--self-test")
    nxt = argv[i + 1] if i + 1 < len(argv) else None
    return True, (nxt if nxt and not nxt.startswith("--") else os.environ.get("STOFREE_SELFTEST_OUTPUT"))

"""Stofree - Windows Disk Space Analyzer. Entry point.

Usage:  python main.py [--no-splash]
        python main.py --self-test [report.json]   (headless check of a packaged build)
"""
from __future__ import annotations

import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from app.launcher import Launcher, set_windows_app_id, splash_enabled
from app.main_window import MainWindow
from app.selftest import parse_selftest_args, run_selftest
from app.ui.branding import app_icon
from app.ui.splash import StartupSplash
from app.utils.constants import APP_NAME, APP_ORG, APP_SUBTITLE, APP_VERSION
from app.utils import assets
from app.utils.logger import get_logger, setup_logging
from app.utils.paths import user_data_dir


def _install_excepthook() -> None:
    log = get_logger("crash")

    def hook(exc_type, exc, tb):
        log.error("Unhandled exception:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        try:
            QMessageBox.critical(None, APP_NAME, f"An unexpected error occurred:\n\n{exc}\n\n"
                                 "Details were written to the log file.")
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = hook


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    setup_logging()
    _install_excepthook()
    get_logger("main").info("%s %s starting (frozen=%s, assets=%s, data=%s)", APP_NAME, APP_VERSION,
                            bool(getattr(sys, "frozen", False)), assets.base_dir(), user_data_dir())
    set_windows_app_id()                       # must happen before any window is created

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(f"{APP_NAME} - {APP_SUBTITLE}")
    app.setOrganizationName(APP_ORG)
    app.setApplicationVersion(APP_VERSION)
    icon = app_icon()                          # built from assets/branding/logo.png
    if not icon.isNull():
        app.setWindowIcon(icon)

    selftest, selftest_out = parse_selftest_args(argv)
    if selftest:                               # packaged-build verification; no window is shown
        return run_selftest(selftest_out)

    splash = StartupSplash.create() if splash_enabled("--no-splash" in argv) else None
    if splash is not None:
        splash.show_centered()                 # GIF starts playing (QMovie)
        app.processEvents()

    window = MainWindow(auto_refresh=False)    # drives are detected on a worker thread below
    launcher = Launcher(window, splash)
    launcher.start()
    code = app.exec()
    window.state.wait_for_scan()
    return code


if __name__ == "__main__":
    sys.exit(main())

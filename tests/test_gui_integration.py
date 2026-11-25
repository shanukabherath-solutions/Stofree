"""End-to-end GUI tests (headless via the Qt 'offscreen' platform).

These drive the real MainWindow, the real worker thread and the real scanner against
temporary directories only.
"""
import os
import time

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QAbstractItemModelTester
from PySide6.QtWidgets import QApplication, QFileDialog

from app import theme
from app.core import disk_scanner as ds
from app.main_window import MainWindow
from app.state import AppState
from app.ui.folder_explorer import FolderTreeModel


def write(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "data"
    write(root / "Videos" / "movie.mp4", 500_000)
    write(root / "Videos" / "clip.mkv", 100_000)
    write(root / "Docs" / "report.pdf", 20_000)
    write(root / "Docs" / "notes.txt", 500)
    write(root / "Docs" / "deep" / "sheet.xlsx", 7_000)
    write(root / "Code" / "main.py", 900)
    write(root / "Code" / "app.js", 1_200)
    write(root / "readme", 10)
    return root


@pytest.fixture
def window(qtbot, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    win = MainWindow(AppState(settings))
    qtbot.addWidget(win)
    win.show()
    yield win
    win.state.wait_for_scan()


def run_scan(qtbot, win, root, timeout=20000):
    with qtbot.waitSignal(win.state.scan_finished, timeout=timeout):
        assert win.state.start_scan(str(root))
    return win.state.result


def test_window_builds_and_all_pages_navigate(window, qtbot):
    assert len(window.nav_buttons) == 7
    assert [b.text().strip() for b in window.nav_buttons] == [
        "Dashboard", "Drive Scanner", "Largest Files", "Folder Explorer", "File Types",
        "Reports", "Settings"]
    for i in range(7):
        window.goto(i)
        assert window.stack.currentIndex() == i


def test_scan_runs_in_worker_thread_and_populates_every_page(window, qtbot, tree):
    import threading
    seen_threads = []
    real_list = ds._list_dir
    ds._list_dir = lambda p: (seen_threads.append(threading.current_thread()), real_list(p))[1]
    try:
        r = run_scan(qtbot, window, tree)
    finally:
        ds._list_dir = real_list
    assert seen_threads and all(t is not threading.main_thread() for t in seen_threads)

    assert not r.cancelled and r.total_files == 8
    # Largest files
    assert window.largest.model.rowCount() == 8
    assert window.largest.proxy.index(0, 0).data() == "movie.mp4"
    # Folder explorer
    assert window.explorer.model.rowCount() == 1
    top = window.explorer.model.index(0, 0)
    assert window.explorer.model.rowCount(top) == 3
    assert "Videos" in window.explorer.model.index(0, 0, top).data()
    # File types
    cats = [window.types.cat_table.item(i, 0).text().strip() for i in range(window.types.cat_table.rowCount())]
    assert cats[0] == "Videos" and "Documents" in cats and "Development" in cats
    # Reports enabled, dashboard remembers the scan
    assert window.reports.json_btn.isEnabled() and window.reports.files_btn.isEnabled()
    assert str(tree) in window.state.last_scans
    assert window.state.last_scans[str(tree)]["files"] == 8


def test_largest_files_sorting_search_and_category_filter(window, qtbot, tree):
    run_scan(qtbot, window, tree)
    page = window.largest
    names = lambda: [page.proxy.index(i, 0).data() for i in range(page.proxy.rowCount())]

    page.sort_combo.setCurrentIndex(0)                       # largest first
    assert names()[:3] == ["movie.mp4", "clip.mkv", "report.pdf"]
    page.sort_combo.setCurrentIndex(1)                       # smallest first
    assert names()[0] == "readme"
    page.sort_combo.setCurrentIndex(2)                       # name A-Z
    assert names() == sorted(names(), key=str.lower)
    page.sort_combo.setCurrentIndex(3)                       # type
    exts = [page.proxy.index(i, 2).data() for i in range(page.proxy.rowCount())]
    assert exts == sorted(exts, key=str.lower)

    page.search.setText("MKV")
    assert names() == ["clip.mkv"]
    page.search.setText("docs report")                       # multiple tokens, path + name
    assert names() == ["report.pdf"]
    page.search.setText("")
    page.category.setCurrentIndex(page.category.findData("Development"))
    assert sorted(names()) == ["app.js", "main.py"]
    assert "Showing 2 of 8" in page.summary.text()


def test_folder_tree_model_is_valid_and_sortable(window, qtbot, tree):
    r = run_scan(qtbot, window, tree)
    model = FolderTreeModel()
    tester = QAbstractItemModelTester(model, QAbstractItemModelTester.FailureReportingMode.Fatal)
    model.set_root(r.root)
    root_idx = model.index(0, 0)
    assert model.rowCount(root_idx) == 3
    # size descending (default)
    assert [model.index(i, 0, root_idx).data() for i in range(3)] == ["Videos", "Docs", "Code"]
    model.sort(0, Qt.AscendingOrder)                         # by name
    assert [model.index(i, 0, root_idx).data() for i in range(3)] == ["Code", "Docs", "Videos"]
    model.sort(3, Qt.DescendingOrder)                        # by file count
    assert model.index(0, 0, root_idx).data() == "Docs"      # 3 files
    # parent() round-trips for every node
    docs = model.index(0, 0, root_idx)
    deep = model.index(0, 0, docs) if model.rowCount(docs) else None
    assert model.parent(docs) == root_idx
    if deep is not None:
        assert model.parent(deep) == docs
    assert model.index(0, 1, root_idx).data().endswith("B")  # formatted size column
    del tester


def test_cancel_stops_scan_from_the_gui(window, qtbot, tmp_path, monkeypatch):
    root = tmp_path / "big"
    for d in range(40):
        write(root / f"d{d}" / "f.bin", 10)
    real = ds._list_dir
    listed = []

    def slow(p):
        listed.append(p)
        time.sleep(0.05)
        return real(p)

    monkeypatch.setattr(ds, "_list_dir", slow)
    with qtbot.waitSignal(window.state.scan_finished, timeout=20000):
        window.state.start_scan(str(root))
        qtbot.waitUntil(lambda: len(listed) >= 3, timeout=5000)
        window.scanner._cancel()
    r = window.state.result
    assert r.cancelled
    assert len(listed) < 41                  # traversal stopped early
    n = len(listed)
    qtbot.wait(300)
    assert len(listed) == n                  # ...and nothing continued afterwards
    assert not window.state.scanning
    assert "cancelled" in window.scanner.status.text().lower()
    assert window.scanner.start_btn.isEnabled() and not window.scanner.cancel_btn.isEnabled()


def test_second_scan_can_start_after_first(window, qtbot, tree, tmp_path):
    run_scan(qtbot, window, tree)
    other = tmp_path / "other"
    write(other / "x.zip", 1234)
    r2 = run_scan(qtbot, window, other)                      # "scan another drive"
    assert r2.total_size == 1234 and window.state.result is r2
    assert window.largest.model.rowCount() == 1


def test_cannot_start_two_scans_at_once(window, qtbot, tree, monkeypatch):
    real = ds._list_dir
    monkeypatch.setattr(ds, "_list_dir", lambda p: (time.sleep(0.05), real(p))[1])
    with qtbot.waitSignal(window.state.scan_finished, timeout=20000):
        assert window.state.start_scan(str(tree))
        assert window.state.start_scan(str(tree)) is False


def test_missing_folder_reports_failure_without_crashing(window, qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    shown = []   # the app shows a modal warning; stub it so the headless test cannot block
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: shown.append(a[1:3])))
    with qtbot.waitSignal(window.state.scan_failed, timeout=10000):
        window.state.start_scan(str(tmp_path / "does_not_exist"))
    assert not window.state.scanning
    assert window.scanner.status.text() == "Scan failed"
    assert shown and shown[0][0] == "Scan failed"


def test_report_buttons_write_files(window, qtbot, tree, tmp_path, monkeypatch):
    run_scan(qtbot, window, tree)
    out = {}

    def fake_dialog(parent, caption, directory, filt):
        ext = ".json" if "JSON" in filt else ".csv"
        out["n"] = out.get("n", 0) + 1
        return str(tmp_path / f"out{out['n']}{ext}"), filt

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(fake_dialog))
    window.reports.files_btn.click()
    window.reports.folders_btn.click()
    window.reports.json_btn.click()
    import csv, json
    with open(tmp_path / "out1.csv", encoding="utf-8-sig", newline="") as fh:
        files = list(csv.DictReader(fh))
    with open(tmp_path / "out2.csv", encoding="utf-8-sig", newline="") as fh:
        folders = list(csv.DictReader(fh))
    with open(tmp_path / "out3.json", encoding="utf-8") as fh:
        data = json.load(fh)
    assert len(files) == 8 and files[0]["file_path"].endswith("movie.mp4")
    assert folders[0]["size_bytes"] == str(500_000 + 100_000 + 20_000 + 500 + 7_000 + 900 + 1_200 + 10)
    assert data["scan"]["total_files"] == 8
    assert "Saved" in window.reports.status.text()


def test_theme_switching_and_persistence(window, qtbot):
    window.state.set_theme("light")
    assert not theme.palette().is_dark and window.state.theme == "light"
    assert "#FFFFFF" in QApplication.instance().styleSheet().upper()
    window.state.set_theme("dark")
    assert theme.palette().is_dark
    window._toggle_theme()
    assert not theme.palette().is_dark
    window._toggle_theme()


def test_sidebar_collapses_when_narrow(window, qtbot):
    window.resize(1200, 800)
    qtbot.waitUntil(lambda: window.sidebar.width() > 150)
    window.resize(880, 700)
    qtbot.waitUntil(lambda: window.sidebar.width() < 100)
    window.resize(1200, 800)
    qtbot.waitUntil(lambda: window.sidebar.width() > 150)


def test_dashboard_shows_drive_cards_for_detected_drives(window):
    assert len(window.dashboard.cards) == len(window.state.drives)
    for card in window.dashboard.cards:
        assert card.drive.mountpoint
        assert card.bar.value() == pytest.approx(card.drive.percent_used)

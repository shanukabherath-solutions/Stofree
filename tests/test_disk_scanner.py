import os
import sys
import threading
import subprocess

import pytest

from app.core import disk_scanner as ds
from app.core.disk_scanner import DiskScanner, link_kind
from app.core.folder_analyzer import flatten


def write(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


@pytest.fixture
def tree(tmp_path):
    """root/
         a.txt (100)            root/docs/b.pdf (2000)   root/docs/deep/c.png (30000)
         root/media/v.mp4 (400000)   root/empty/ (no files)
    """
    root = tmp_path / "root"
    write(root / "a.txt", 100)
    write(root / "docs" / "b.pdf", 2000)
    write(root / "docs" / "deep" / "c.png", 30000)
    write(root / "media" / "v.mp4", 400000)
    (root / "empty").mkdir()
    return root


def test_file_and_folder_sizes(tree):
    r = DiskScanner().scan(str(tree))
    assert not r.cancelled
    assert r.total_files == 4
    assert r.total_size == 100 + 2000 + 30000 + 400000
    assert r.total_folders == 5          # root, docs, deep, media, empty
    by_name = {c.name: c for c in r.root.children}
    assert by_name["docs"].size == 32000
    assert by_name["docs"].file_count == 2
    assert by_name["docs"].folder_count == 1
    assert by_name["docs"].children[0].size == 30000
    assert by_name["media"].size == 400000
    assert by_name["empty"].size == 0 and by_name["empty"].file_count == 0
    assert r.root.direct_size == 100 and r.root.direct_files == 1
    assert r.root.folder_count == 4


def test_folder_sizes_are_sum_of_children(tree):
    r = DiskScanner().scan(str(tree))
    for node in r.root.walk():
        assert node.size == node.direct_size + sum(c.size for c in node.children)
        assert node.file_count == node.direct_files + sum(c.file_count for c in node.children)


def test_largest_files_and_type_stats(tree):
    r = DiskScanner().scan(str(tree))
    assert [f.name for f in r.top_files] == ["v.mp4", "c.png", "b.pdf", "a.txt"]
    cats = {c: (n, b) for c, n, b in r.type_stats.category_rows()}
    assert cats["Videos"] == (1, 400000)
    assert cats["Images"] == (1, 30000)
    assert cats["Documents"] == (2, 2100)


def test_top_files_limit(tree):
    r = DiskScanner(top_files_limit=2).scan(str(tree))
    assert len(r.top_files) == 2 and r.top_files[0].name == "v.mp4"
    assert r.total_files == 4  # totals unaffected by the retention limit


def test_nonexistent_and_file_root(tmp_path):
    with pytest.raises(FileNotFoundError):
        DiskScanner().scan(str(tmp_path / "missing"))
    f = tmp_path / "f.txt"
    f.write_text("hi")
    with pytest.raises(NotADirectoryError):
        DiskScanner().scan(str(f))


def test_scan_never_reads_file_contents(tree, monkeypatch):
    opened = []
    real_open = open

    def guarded_open(file, *a, **k):
        if str(file).startswith(str(tree)):
            opened.append(file)
        return real_open(file, *a, **k)

    monkeypatch.setattr("builtins.open", guarded_open)
    DiskScanner().scan(str(tree))
    assert opened == []


def test_progress_callbacks(tree):
    events = []
    DiskScanner(progress_every=1, min_interval=0).scan(str(tree), events.append)
    assert events, "expected progress events"
    last = events[-1]
    assert last.files == 4 and last.bytes_scanned == 432100 and last.folders == 5
    assert all(e.elapsed >= 0 for e in events)
    assert any(e.current_dir.endswith("deep") for e in events)


# ---------------------------------------------------------------- error handling
def test_permission_error_is_handled(tree, monkeypatch):
    real = ds._list_dir
    denied = str(tree / "docs")

    def fake(path):
        if path == denied:
            raise PermissionError(13, "Access is denied")
        return real(path)

    monkeypatch.setattr(ds, "_list_dir", fake)
    r = DiskScanner().scan(str(tree))
    assert r.error_count == 1 and "docs" in r.errors[0] and "PermissionError" in r.errors[0]
    docs = next(c for c in r.root.children if c.name == "docs")
    assert docs.accessible is False and docs.size == 0
    assert r.total_size == 100 + 400000      # the rest was still scanned
    assert r.total_files == 2


def test_stat_failure_on_file_is_handled(tree, monkeypatch):
    real_stat = os.DirEntry.stat if hasattr(os.DirEntry, "stat") else None
    real_list = ds._list_dir

    class Wrapper:
        """Proxy DirEntry whose stat() fails for one file (simulates a file vanishing)."""
        def __init__(self, e): self._e = e
        def __getattr__(self, n): return getattr(self._e, n)
        def stat(self, **kw):
            if self._e.name == "b.pdf":
                raise FileNotFoundError(2, "gone")
            return self._e.stat(**kw)

    monkeypatch.setattr(ds, "_list_dir", lambda p: [Wrapper(e) for e in real_list(p)])
    r = DiskScanner().scan(str(tree))
    assert r.error_count == 1 and "b.pdf" in r.errors[0]
    assert r.total_files == 3


def test_unreadable_root_does_not_crash(tree, monkeypatch):
    def boom(path):
        raise PermissionError(13, "denied")
    monkeypatch.setattr(ds, "_list_dir", boom)
    r = DiskScanner().scan(str(tree))
    assert r.total_files == 0 and r.error_count == 1 and not r.root.accessible


def test_error_list_is_capped(tmp_path, monkeypatch):
    for i in range(30):
        (tmp_path / f"d{i}").mkdir()
    real = ds._list_dir
    monkeypatch.setattr(ds, "MAX_ERRORS_KEPT", 5)
    monkeypatch.setattr(ds, "_list_dir",
                        lambda p: real(p) if p == str(tmp_path) else (_ for _ in ()).throw(PermissionError("x")))
    r = DiskScanner().scan(str(tmp_path))
    assert r.error_count == 30 and len(r.errors) == 5


# ---------------------------------------------------------------- links / junctions
def _try_symlink(link, target, is_dir):
    try:
        os.symlink(target, link, target_is_directory=is_dir)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this system")


def test_symlinks_are_not_followed(tree, tmp_path):
    outside = tmp_path / "outside"
    write(outside / "big.bin", 9_000_000)
    _try_symlink(tree / "link_dir", outside, True)
    _try_symlink(tree / "link_file", outside / "big.bin", False)
    _try_symlink(tree / "docs" / "loop", tree, True)         # would recurse forever if followed
    r = DiskScanner().scan(str(tree))
    assert r.total_size == 432100                              # nothing counted via links
    assert r.total_files == 4
    assert r.skipped_links == 3
    assert not any("big.bin" in f.path for f in r.top_files)


def test_link_kind_classification_with_fake_entries():
    class St:
        def __init__(self, attrs, tag=0):
            self.st_file_attributes, self.st_reparse_tag = attrs, tag

    class E:
        def __init__(self, sym=False, junc=False, st=None):
            self._s, self._j, self._st = sym, junc, st
        def is_symlink(self): return self._s
        def is_junction(self): return self._j
        def stat(self, follow_symlinks=True): return self._st

    assert link_kind(E(sym=True)) == "symlink"
    assert link_kind(E(junc=True)) == "junction"
    assert link_kind(E(st=St(0x400, 0xA0000003))) == "junction"      # mount point tag
    assert link_kind(E(st=St(0x400, 0xA000000C))) == "symlink"
    assert link_kind(E(st=St(0x400, 0x9000001A))) == "reparse"       # e.g. cloud placeholder
    assert link_kind(E(st=St(0x20))) is None                          # plain archive file


def test_any_reparse_point_directory_is_skipped(tree, monkeypatch):
    real = ds.link_kind
    monkeypatch.setattr(ds, "link_kind",
                        lambda e: "reparse" if e.name == "media" else real(e))
    r = DiskScanner().scan(str(tree))
    assert r.skipped_links == 1
    assert all(c.name != "media" for c in r.root.children)
    assert r.total_size == 100 + 2000 + 30000


def test_reparse_point_file_is_counted_but_link_file_is_not(tree, monkeypatch):
    real = ds.link_kind

    def fake(e):
        if e.name == "a.txt":
            return "reparse"      # e.g. OneDrive placeholder -> real file, counted
        if e.name == "b.pdf":
            return "symlink"
        return real(e)

    monkeypatch.setattr(ds, "link_kind", fake)
    r = DiskScanner().scan(str(tree))
    names = {f.name for f in r.top_files}
    assert "a.txt" in names and "b.pdf" not in names


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS junctions are Windows-only")
def test_real_junction_is_not_followed(tree, tmp_path):
    outside = tmp_path / "outside"
    write(outside / "big.bin", 5_000_000)
    res = subprocess.run(["cmd", "/c", "mklink", "/J", str(tree / "junc"), str(outside)],
                         capture_output=True, text=True)
    if res.returncode != 0:
        pytest.skip(f"could not create junction: {res.stderr}")
    r = DiskScanner().scan(str(tree))
    assert r.total_size == 432100 and r.skipped_links == 1


# ---------------------------------------------------------------- cancellation
def test_cancel_before_start(tree):
    ev = threading.Event()
    ev.set()
    r = DiskScanner().scan(str(tree), cancel_event=ev)
    assert r.cancelled and r.total_files == 0


def test_cancel_stops_traversal(tmp_path, monkeypatch):
    for d in range(10):
        for f in range(20):
            write(tmp_path / f"dir{d}" / f"f{f}.txt", 10)
    listed = []
    real = ds._list_dir
    monkeypatch.setattr(ds, "_list_dir", lambda p: (listed.append(p), real(p))[1])

    ev = threading.Event()
    calls_after_cancel = []

    def on_progress(p):
        if ev.is_set():
            calls_after_cancel.append(len(listed))
        if p.files >= 15:
            ev.set()

    r = DiskScanner(progress_every=1, min_interval=0).scan(str(tmp_path), on_progress, ev)
    assert r.cancelled
    assert r.total_files < 200
    # No directory listing may have started once the flag was set.
    dirs_when_cancelled = len(listed)
    assert dirs_when_cancelled < 11
    # Partial result is internally consistent.
    for node in r.root.walk():
        assert node.size == node.direct_size + sum(c.size for c in node.children)


def test_cancel_from_other_thread(tmp_path):
    for d in range(30):
        for f in range(40):
            write(tmp_path / f"d{d}" / f"f{f}.bin", 1)
    ev = threading.Event()
    result = {}
    t = threading.Thread(target=lambda: result.update(r=DiskScanner(progress_every=1).scan(str(tmp_path), None, ev)))
    ev.set()
    t.start()
    t.join(timeout=10)
    assert not t.is_alive()
    assert result["r"].cancelled


def test_deep_tree_does_not_hit_recursion_limit(tmp_path):
    p = tmp_path
    depth = 400  # > default recursion limit headroom for a recursive implementation w/ frames
    try:
        for i in range(depth):
            p = p / "d"
            p.mkdir()
    except OSError:
        pytest.skip("path too long for this filesystem")
    write(p / "leaf.txt", 7)
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(150)
    try:
        r = DiskScanner().scan(str(tmp_path))
    finally:
        sys.setrecursionlimit(old)
    assert r.total_size == 7 and r.total_folders == depth + 1

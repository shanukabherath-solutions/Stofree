"""Read-only recursive disk scanner.

Design notes
------------
* Uses ``os.scandir`` and an explicit stack (no recursion) so extremely deep trees are safe.
* Only metadata is read (``DirEntry.stat``). File contents are never opened.
* Symbolic links, junctions, mount points and every other reparse-point *directory*
  are never followed, preventing loops and double counting. Link-like *files* are skipped
  too; other reparse-point files (e.g. cloud placeholders) are counted as normal files.
* Cancellation is checked before every entry and before every directory listing, so no
  further traversal happens after the cancel flag is set. The partial tree is rolled up so
  the returned (cancelled) result is internally consistent.
* Only folders are kept in memory, plus a bounded list of the N largest files.
"""
from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from ..utils.constants import (
    DEFAULT_TOP_FILES, FILE_ATTRIBUTE_REPARSE_POINT, IO_REPARSE_TAG_MOUNT_POINT,
    IO_REPARSE_TAG_SYMLINK, MAX_ERRORS_KEPT, PROGRESS_EVERY_ENTRIES, PROGRESS_MIN_INTERVAL,
)
from ..utils.logger import get_logger
from .file_analyzer import FileRecord, TopFiles, TypeStats, get_extension
from .folder_analyzer import FolderNode

log = get_logger("scanner")


@dataclass
class ScanProgress:
    files: int
    folders: int
    bytes_scanned: int
    current_dir: str
    errors: int
    elapsed: float


@dataclass
class ScanResult:
    root_path: str
    drive: str
    started_at: datetime
    finished_at: datetime
    duration: float
    cancelled: bool
    total_files: int
    total_folders: int
    total_size: int
    error_count: int
    errors: list[str]
    skipped_links: int
    skipped_samples: list[str]
    root: FolderNode
    top_files: list[FileRecord]
    type_stats: TypeStats = field(default_factory=TypeStats)

    def summary(self) -> dict:
        return {
            "root": self.root_path, "drive": self.drive,
            "scan_timestamp": self.started_at.isoformat(timespec="seconds"),
            "duration_seconds": round(self.duration, 2), "cancelled": self.cancelled,
            "total_files": self.total_files, "total_folders": self.total_folders,
            "total_size_bytes": self.total_size, "errors": self.error_count,
            "skipped_links": self.skipped_links,
        }


def _list_dir(path: str) -> list[os.DirEntry]:
    """List a directory. Isolated so tests can simulate failures."""
    with os.scandir(path) as it:
        return list(it)


def link_kind(entry: os.DirEntry) -> str | None:
    """Classify link-like entries: 'symlink', 'junction', 'reparse' or None."""
    try:
        if entry.is_symlink():
            return "symlink"
        is_junction = getattr(entry, "is_junction", None)
        if is_junction is not None and is_junction():
            return "junction"
        st = entry.stat(follow_symlinks=False)
    except OSError:
        return None
    attrs = getattr(st, "st_file_attributes", 0)
    if attrs & FILE_ATTRIBUTE_REPARSE_POINT:
        tag = getattr(st, "st_reparse_tag", 0)
        if tag == IO_REPARSE_TAG_SYMLINK:
            return "symlink"
        if tag == IO_REPARSE_TAG_MOUNT_POINT:
            return "junction"
        return "reparse"
    return None


class DiskScanner:
    def __init__(self, top_files_limit: int = DEFAULT_TOP_FILES,
                 progress_every: int = PROGRESS_EVERY_ENTRIES,
                 min_interval: float = PROGRESS_MIN_INTERVAL) -> None:
        self.top_files_limit = top_files_limit
        self.progress_every = max(1, progress_every)
        self.min_interval = min_interval

    # ------------------------------------------------------------------ scan
    def scan(self, root: str, progress_callback: Callable[[ScanProgress], None] | None = None,
             cancel_event: threading.Event | None = None) -> ScanResult:
        root = os.path.abspath(root)
        if not os.path.exists(root):
            raise FileNotFoundError(f"Path does not exist: {root}")
        if not os.path.isdir(root):
            raise NotADirectoryError(f"Not a directory: {root}")

        cancel = cancel_event or threading.Event()
        started_at = datetime.now()
        t0 = time.monotonic()

        top = TopFiles(self.top_files_limit)
        types = TypeStats()
        errors: list[str] = []
        skipped: list[str] = []
        counters = {"files": 0, "dirs": 0, "bytes": 0, "errors": 0, "skipped": 0}
        state = {"since_emit": 0, "last_emit": 0.0, "current": root}

        def record_error(path: str, exc: BaseException) -> None:
            counters["errors"] += 1
            if len(errors) < MAX_ERRORS_KEPT:
                msg = getattr(exc, "strerror", None) or str(exc)
                errors.append(f"{path}: {type(exc).__name__}: {msg}")
            log.debug("Scan error at %s: %r", path, exc)

        def emit(force: bool = False) -> None:
            if progress_callback is None:
                return
            now = time.monotonic()
            if not force and now - state["last_emit"] < self.min_interval:
                return
            state["last_emit"] = now
            state["since_emit"] = 0
            progress_callback(ScanProgress(
                counters["files"], counters["dirs"], counters["bytes"],
                state["current"], counters["errors"], now - t0))

        root_node = FolderNode(root, None, name=root)
        frames: list[list] = []   # each: [node, iterator over entries]

        def enter(node: FolderNode) -> None:
            """List a directory and push a frame for it (or mark it inaccessible)."""
            counters["dirs"] += 1
            state["current"] = node.path
            try:
                entries = _list_dir(node.path)
            except OSError as exc:
                node.accessible = False
                record_error(node.path, exc)
                entries = []
            frames.append([node, iter(entries)])

        log.info("Scan started: %s", root)
        if not cancel.is_set():
            enter(root_node)
        emit(force=True)

        while frames:
            if cancel.is_set():
                break
            node, it = frames[-1]
            entry = next(it, None)
            if entry is None:
                frames.pop()
                if frames:
                    parent = frames[-1][0]
                    parent.size += node.size
                    parent.file_count += node.file_count
                    parent.folder_count += node.folder_count + 1
                continue

            state["since_emit"] += 1
            if state["since_emit"] >= self.progress_every:
                emit()

            try:
                if entry.is_dir(follow_symlinks=False):
                    if link_kind(entry) is not None:
                        counters["skipped"] += 1
                        if len(skipped) < 50:
                            skipped.append(entry.path)
                        continue
                    child = FolderNode(entry.path, node, name=entry.name)
                    node.children.append(child)
                    if cancel.is_set():
                        break
                    enter(child)
                elif entry.is_file(follow_symlinks=False):
                    kind = link_kind(entry)
                    if kind in ("symlink", "junction"):
                        counters["skipped"] += 1
                        continue
                    size = entry.stat(follow_symlinks=False).st_size
                    node.size += size
                    node.file_count += 1
                    node.direct_size += size
                    node.direct_files += 1
                    counters["files"] += 1
                    counters["bytes"] += size
                    ext = get_extension(entry.name)
                    types.add(ext, size)
                    top.add(entry.path, size)
                elif entry.is_symlink():
                    # Symlinks (to files or dirs, incl. broken ones) are never followed.
                    counters["skipped"] += 1
                    if len(skipped) < 50:
                        skipped.append(entry.path)
                # anything else (sockets, devices, ...) is ignored
            except OSError as exc:
                record_error(entry.path, exc)

        cancelled = cancel.is_set()
        # Roll up whatever is left on the stack (non-empty only when cancelled).
        while frames:
            node, _ = frames.pop()
            if frames:
                parent = frames[-1][0]
                parent.size += node.size
                parent.file_count += node.file_count
                parent.folder_count += node.folder_count + 1

        finished_at = datetime.now()
        duration = time.monotonic() - t0
        emit(force=True)
        drive = os.path.splitdrive(root)[0]
        drive = (drive + "\\") if drive else root
        result = ScanResult(
            root_path=root, drive=drive, started_at=started_at, finished_at=finished_at,
            duration=duration, cancelled=cancelled, total_files=root_node.file_count,
            total_folders=root_node.folder_count + 1, total_size=root_node.size,
            error_count=counters["errors"], errors=errors, skipped_links=counters["skipped"],
            skipped_samples=skipped, root=root_node, top_files=top.records(), type_stats=types,
        )
        log.info("Scan %s: %s files, %s folders, %s bytes, %s errors, %.1fs",
                 "cancelled" if cancelled else "finished", result.total_files,
                 result.total_folders, result.total_size, result.error_count, duration)
        return result

"""File categorisation, per-type statistics and bounded 'largest files' tracking."""
from __future__ import annotations

import heapq
import os
from dataclasses import dataclass

from ..utils.constants import CATEGORY_EXTENSIONS, OTHER_CATEGORY

_EXT_TO_CATEGORY: dict[str, str] = {
    ext: cat for cat, exts in CATEGORY_EXTENSIONS.items() for ext in exts
}


def get_extension(name: str) -> str:
    """Lower-case extension including dot ('' if none). '.gitignore' has no extension."""
    return os.path.splitext(name)[1].lower()


def categorize_extension(ext: str) -> str:
    if ext and not ext.startswith("."):
        ext = "." + ext
    return _EXT_TO_CATEGORY.get(ext.lower(), OTHER_CATEGORY)


def categorize_file(name: str) -> str:
    return categorize_extension(get_extension(name))


@dataclass(frozen=True)
class FileRecord:
    path: str
    size: int

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def extension(self) -> str:
        return get_extension(self.path)

    @property
    def parent(self) -> str:
        return os.path.dirname(self.path)

    @property
    def category(self) -> str:
        return categorize_extension(self.extension)


class TypeStats:
    """Accumulates (count, bytes) per category and per extension."""

    def __init__(self) -> None:
        self.by_category: dict[str, list[int]] = {}   # cat -> [count, bytes]
        self.by_extension: dict[str, list[int]] = {}  # ext -> [count, bytes]

    def add(self, ext: str, size: int) -> None:
        cat = categorize_extension(ext)
        c = self.by_category.setdefault(cat, [0, 0])
        c[0] += 1
        c[1] += size
        e = self.by_extension.setdefault(ext, [0, 0])
        e[0] += 1
        e[1] += size

    def total_bytes(self) -> int:
        return sum(v[1] for v in self.by_category.values())

    def category_rows(self) -> list[tuple[str, int, int]]:
        """[(category, file_count, bytes)] sorted by bytes desc."""
        rows = [(k, v[0], v[1]) for k, v in self.by_category.items()]
        rows.sort(key=lambda r: r[2], reverse=True)
        return rows

    def extension_rows(self, limit: int | None = None) -> list[tuple[str, int, int]]:
        rows = [(k or "(no extension)", v[0], v[1]) for k, v in self.by_extension.items()]
        rows.sort(key=lambda r: r[2], reverse=True)
        return rows[:limit] if limit else rows


class TopFiles:
    """Keeps only the N largest files seen (min-heap) so memory stays bounded."""

    def __init__(self, limit: int) -> None:
        self.limit = max(1, int(limit))
        self._heap: list[tuple[int, int, str]] = []
        self._seq = 0

    def add(self, path: str, size: int) -> None:
        self._seq += 1
        item = (size, self._seq, path)
        if len(self._heap) < self.limit:
            heapq.heappush(self._heap, item)
        elif size > self._heap[0][0]:
            heapq.heapreplace(self._heap, item)

    def __len__(self) -> int:
        return len(self._heap)

    def records(self) -> list[FileRecord]:
        """Largest first."""
        return [FileRecord(p, s) for s, _, p in sorted(self._heap, reverse=True)]

"""Folder tree model produced by the scanner."""
from __future__ import annotations

import os
from collections.abc import Iterator


class FolderNode:
    """One scanned directory. Sizes/counts are cumulative (include all descendants).

    Only folders are stored (never individual files) to keep memory bounded.
    """

    __slots__ = ("name", "path", "parent", "children", "size", "file_count",
                 "folder_count", "direct_size", "direct_files", "accessible")

    def __init__(self, path: str, parent: "FolderNode | None" = None, name: str | None = None):
        self.path = path
        self.name = name if name is not None else (os.path.basename(path.rstrip("\\/")) or path)
        self.parent = parent
        self.children: list[FolderNode] = []
        self.size = 0              # cumulative bytes
        self.file_count = 0        # cumulative files
        self.folder_count = 0      # cumulative sub-folders (excluding self)
        self.direct_size = 0       # bytes of files directly inside this folder
        self.direct_files = 0
        self.accessible = True

    def __repr__(self) -> str:  # pragma: no cover
        return f"FolderNode({self.path!r}, size={self.size})"

    def children_by_size(self) -> list["FolderNode"]:
        return sorted(self.children, key=lambda c: c.size, reverse=True)

    def walk(self) -> Iterator["FolderNode"]:
        """Iterative pre-order traversal (safe for very deep trees)."""
        stack = [self]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))

    def depth(self) -> int:
        d, n = 0, self
        while n.parent is not None:
            d += 1
            n = n.parent
        return d


def flatten(root: FolderNode, max_depth: int | None = None) -> list[tuple[FolderNode, int]]:
    """Return [(node, depth)] for the tree, optionally limited to ``max_depth`` levels
    below the root (root itself is depth 0)."""
    out: list[tuple[FolderNode, int]] = []
    stack: list[tuple[FolderNode, int]] = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        out.append((node, depth))
        if max_depth is None or depth < max_depth:
            for child in reversed(node.children):
                stack.append((child, depth + 1))
    return out

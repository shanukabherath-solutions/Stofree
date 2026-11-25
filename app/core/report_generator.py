"""CSV / JSON report export. Writes only the report file chosen by the caller."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from ..utils.constants import APP_NAME, APP_VERSION
from .disk_scanner import ScanResult
from .file_analyzer import categorize_extension
from .folder_analyzer import FolderNode

FILE_COLUMNS = ["drive", "file_path", "file_name", "file_type", "category",
                "parent_directory", "size_bytes", "scan_timestamp"]
FOLDER_COLUMNS = ["drive", "folder_path", "depth", "size_bytes", "file_count",
                  "subfolder_count", "scan_timestamp"]


def _ts(result: ScanResult) -> str:
    return result.started_at.isoformat(timespec="seconds")


def export_files_csv(result: ScanResult, path: str | os.PathLike, limit: int | None = None) -> int:
    """Export the retained largest files. Returns the number of rows written."""
    rows = result.top_files[:limit] if limit else result.top_files
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(FILE_COLUMNS)
        for r in rows:
            ext = r.extension
            w.writerow([result.drive, r.path, r.name, ext.lstrip("."),
                        categorize_extension(ext), r.parent, r.size, _ts(result)])
    return len(rows)


def export_folders_csv(result: ScanResult, path: str | os.PathLike,
                       max_depth: int | None = None) -> int:
    """Export folders (size-sorted siblings) up to ``max_depth`` levels below the root."""
    rows = 0
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(FOLDER_COLUMNS)
        stack: list[tuple[FolderNode, int]] = [(result.root, 0)]
        while stack:
            node, depth = stack.pop()
            w.writerow([result.drive, node.path, depth, node.size, node.file_count,
                        node.folder_count, _ts(result)])
            rows += 1
            if max_depth is None or depth < max_depth:
                for child in reversed(node.children_by_size()):
                    stack.append((child, depth + 1))
    return rows


def _node_dict(node: FolderNode, depth: int, max_depth: int | None) -> dict:
    d = {"path": node.path, "size_bytes": node.size, "file_count": node.file_count,
         "subfolder_count": node.folder_count}
    if max_depth is None or depth < max_depth:
        d["children"] = [_node_dict(c, depth + 1, max_depth) for c in node.children_by_size()]
    return d


def build_json(result: ScanResult, max_depth: int | None = 4, file_limit: int | None = None) -> dict:
    cats = [{"category": c, "file_count": n, "size_bytes": b,
             "percent": round(b / result.total_size * 100, 2) if result.total_size else 0.0}
            for c, n, b in result.type_stats.category_rows()]
    files = result.top_files[:file_limit] if file_limit else result.top_files
    # Depth-limited recursion is bounded by max_depth; guard unlimited export depth.
    tree = _node_dict(result.root, 0, max_depth if max_depth is not None else 200)
    return {
        "generator": f"{APP_NAME} {APP_VERSION}",
        "scan": result.summary(),
        "file_types": cats,
        "largest_files": [{"drive": result.drive, "file_path": r.path, "file_name": r.name,
                           "file_type": r.extension.lstrip("."), "category": r.category,
                           "parent_directory": r.parent, "size_bytes": r.size,
                           "scan_timestamp": _ts(result)} for r in files],
        "folders": tree,
        "errors_sample": result.errors[:50],
    }


def export_json(result: ScanResult, path: str | os.PathLike, max_depth: int | None = 4,
                file_limit: int | None = None) -> None:
    data = build_json(result, max_depth, file_limit)
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

import csv
import json

import pytest


def _read(path, dict_rows=True):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh)) if dict_rows else list(csv.reader(fh))

from app.core.disk_scanner import DiskScanner
from app.core.report_generator import (
    FILE_COLUMNS, FOLDER_COLUMNS, build_json, export_files_csv, export_folders_csv, export_json,
)


@pytest.fixture
def result(tmp_path):
    root = tmp_path / "scanme"
    for rel, size in [("a.txt", 10), ("docs/b.pdf", 200), ("docs/sub/c.png", 3000),
                      ("media/v,\"x\".mp4", 40000)]:   # comma + quote in name to test CSV escaping
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"0" * size)
    return DiskScanner().scan(str(root))


def test_files_csv(result, tmp_path):
    out = tmp_path / "files.csv"
    n = export_files_csv(result, out)
    assert n == 4
    rows = _read(out)
    assert list(rows[0].keys()) == FILE_COLUMNS
    assert rows[0]["size_bytes"] == "40000" and rows[0]["file_type"] == "mp4"
    assert rows[0]["category"] == "Videos"
    assert rows[0]["file_path"].endswith('v,"x".mp4')           # round-trips special chars
    assert rows[0]["scan_timestamp"] == result.started_at.isoformat(timespec="seconds")
    assert rows[0]["drive"] == result.drive
    assert sum(int(r["size_bytes"]) for r in rows) == result.total_size


def test_files_csv_limit(result, tmp_path):
    out = tmp_path / "f.csv"
    assert export_files_csv(result, out, limit=2) == 2
    assert len(_read(out, dict_rows=False)) == 3  # header + 2


def test_folders_csv_and_depth(result, tmp_path):
    out = tmp_path / "folders.csv"
    n = export_folders_csv(result, out)
    rows = _read(out)
    assert n == len(rows) == 4          # scanme, docs, sub, media
    assert list(rows[0].keys()) == FOLDER_COLUMNS
    assert rows[0]["depth"] == "0" and int(rows[0]["size_bytes"]) == result.total_size
    shallow = tmp_path / "shallow.csv"
    assert export_folders_csv(result, shallow, max_depth=1) == 3   # sub excluded
    # Siblings sorted largest first: media (40000) before docs (3200)
    assert rows[1]["folder_path"].endswith("media")


def test_json_export(result, tmp_path):
    out = tmp_path / "scan.json"
    export_json(result, out, max_depth=None)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["scan"]["total_files"] == 4
    assert data["scan"]["total_size_bytes"] == 43210
    assert data["scan"]["drive"] == result.drive
    cats = {c["category"]: c for c in data["file_types"]}
    assert cats["Videos"]["size_bytes"] == 40000 and cats["Videos"]["percent"] == pytest.approx(92.57, abs=0.01)
    assert data["largest_files"][0]["file_name"] == 'v,"x".mp4'
    assert {"file_path", "size_bytes", "file_type", "scan_timestamp", "drive"} <= set(data["largest_files"][0])
    tree = data["folders"]
    assert tree["size_bytes"] == 43210 and tree["children"][0]["path"].endswith("media")
    docs = next(c for c in tree["children"] if c["path"].endswith("docs"))
    assert docs["children"][0]["size_bytes"] == 3000


def test_json_depth_limit_omits_children(result):
    data = build_json(result, max_depth=0)
    assert "children" not in data["folders"]
    data = build_json(result, max_depth=1)
    assert "children" in data["folders"] and "children" not in data["folders"]["children"][0]


def test_json_file_limit(result):
    assert len(build_json(result, file_limit=1)["largest_files"]) == 1


def test_export_is_read_only_for_scanned_tree(result, tmp_path):
    import os
    before = sorted(os.listdir(result.root_path))
    export_files_csv(result, tmp_path / "x.csv")
    assert sorted(os.listdir(result.root_path)) == before

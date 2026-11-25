import pytest

from app.core.file_analyzer import (
    FileRecord, TopFiles, TypeStats, categorize_extension, categorize_file, get_extension,
)


@pytest.mark.parametrize("name,cat", [
    ("a.PNG", "Images"), ("b.jpeg", "Images"), ("c.webp", "Images"),
    ("v.MKV", "Videos"), ("v.mp4", "Videos"), ("s.flac", "Audio"), ("s.mp3", "Audio"),
    ("d.pdf", "Documents"), ("d.docx", "Documents"), ("n.txt", "Documents"),
    ("setup.exe", "Applications"), ("x.dll", "Applications"), ("x.msi", "Applications"),
    ("z.zip", "Archives"), ("z.7z", "Archives"), ("z.rar", "Archives"),
    ("code.py", "Development"), ("a.js", "Development"), ("a.json", "Development"),
    ("a.css", "Development"), ("a.html", "Development"), ("a.ts", "Development"),
    ("weird.xyz", "Other"), ("noext", "Other"), (".gitignore", "Other"),
])
def test_categorize_file(name, cat):
    assert categorize_file(name) == cat


def test_extension_helpers():
    assert get_extension("Archive.TAR.GZ") == ".gz"
    assert get_extension("noext") == ""
    assert categorize_extension("png") == "Images"      # dot optional
    assert categorize_extension("") == "Other"


def test_type_stats_accumulates_and_sorts():
    ts = TypeStats()
    ts.add(".png", 100)
    ts.add(".jpg", 300)
    ts.add(".mp4", 1000)
    ts.add("", 5)
    rows = ts.category_rows()
    assert rows[0] == ("Videos", 1, 1000)
    assert ("Images", 2, 400) in rows
    assert ts.total_bytes() == 1405
    assert ts.extension_rows(2)[0] == (".mp4", 1, 1000)
    assert any(r[0] == "(no extension)" for r in ts.extension_rows())


def test_top_files_bounded_and_sorted():
    top = TopFiles(3)
    for i, size in enumerate([5, 50, 1, 500, 20, 100]):
        top.add(f"/f{i}", size)
    recs = top.records()
    assert len(top) == 3
    assert [r.size for r in recs] == [500, 100, 50]


def test_file_record_properties():
    r = FileRecord(r"C:\Users\me\video.MP4", 10)
    assert r.extension == ".mp4" and r.category == "Videos"
    r2 = FileRecord("/a/b/c.txt", 1)
    assert r2.name == "c.txt" and r2.parent == "/a/b"

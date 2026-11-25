from collections import namedtuple

import psutil
import pytest

from app.core import drive_manager as dm

Part = namedtuple("Part", "device mountpoint fstype opts")
Usage = namedtuple("Usage", "total used free")


def test_drive_info_properties():
    d = dm.DriveInfo("C:\\", "C:\\", "NTFS", "System", "fixed", 1000, 250, 750)
    assert d.percent_used == 25.0
    assert d.display_name == "C: (System)"
    assert dm.DriveInfo("D:\\", "D:\\", "NTFS", "", "fixed", 0, 0, 0).percent_used == 0.0
    assert dm.DriveInfo("D:\\", "D:\\", "NTFS", "", "fixed", 10, 1, 9).display_name == "D:"


def test_list_drives_filters_and_sorts(monkeypatch):
    parts = [
        Part("D:\\", "D:\\", "NTFS", "rw,fixed"),
        Part("C:\\", "C:\\", "NTFS", "rw,fixed"),
        Part("E:\\", "E:\\", "", "cdrom"),               # optical -> skipped
        Part("F:\\", "F:\\", "FAT32", "rw,removable"),
        Part("G:\\", "G:\\", "NTFS", "rw,fixed"),        # unreadable -> skipped
    ]
    monkeypatch.setattr(psutil, "disk_partitions", lambda all=False: parts)

    def fake_usage(path):
        if path == "G:\\":
            raise PermissionError("denied")
        return Usage(2 * 1024**4, 1024**4, 1024**4)

    monkeypatch.setattr(dm.shutil, "disk_usage", fake_usage)
    drives = dm.list_drives()
    assert [d.mountpoint for d in drives] == ["C:\\", "D:\\", "F:\\"]
    assert drives[0].total == 2 * 1024**4 and drives[0].percent_used == 50.0
    assert drives[2].kind == "removable"

    no_removable = dm.list_drives(include_removable=False)
    assert [d.mountpoint for d in no_removable] == ["C:\\", "D:\\"]


def test_list_drives_skips_zero_capacity(monkeypatch):
    monkeypatch.setattr(psutil, "disk_partitions", lambda all=False: [Part("C:\\", "C:\\", "NTFS", "rw,fixed")])
    monkeypatch.setattr(dm.shutil, "disk_usage", lambda p: Usage(0, 0, 0))
    assert dm.list_drives() == []


def test_get_drive_info_real_path(tmp_path):
    info = dm.get_drive_info(str(tmp_path))
    assert info is not None and info.total > 0 and info.free <= info.total


def test_get_drive_info_missing_path_returns_none(tmp_path):
    assert dm.get_drive_info(str(tmp_path / "nope")) is None


def test_real_detection_runs():
    # Smoke test on the host OS: must not raise, entries must be internally consistent.
    for d in dm.list_drives():
        assert d.total >= d.used >= 0


def test_used_plus_free_equals_total_even_if_fs_reports_inconsistent_usage(monkeypatch):
    # e.g. ext4 with reserved blocks / overlay mounts: reported 'used' does not add up.
    monkeypatch.setattr(dm.shutil, "disk_usage", lambda p: Usage(1000, 30, 90))
    info = dm.get_drive_info("X:\\")
    assert info.used == 910 and info.free == 90
    assert info.used + info.free == info.total
    assert info.percent_used == pytest.approx(91.0)

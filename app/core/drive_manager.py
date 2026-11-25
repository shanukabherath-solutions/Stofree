"""Drive detection and capacity information (read-only)."""
from __future__ import annotations

import ctypes
import os
import shutil
from dataclasses import dataclass

import psutil

from ..utils.logger import get_logger

log = get_logger("drives")


@dataclass(frozen=True)
class DriveInfo:
    mountpoint: str          # e.g. "C:\\"
    device: str
    fstype: str
    label: str
    kind: str                # fixed / removable / remote / unknown
    total: int
    used: int
    free: int

    @property
    def percent_used(self) -> float:
        return 0.0 if self.total <= 0 else self.used / self.total * 100.0

    @property
    def display_name(self) -> str:
        letter = self.mountpoint.rstrip("\\/") or self.mountpoint
        return f"{letter} ({self.label})" if self.label else letter


def get_volume_label(mountpoint: str) -> str:
    """Return the volume label on Windows; empty string elsewhere or on failure."""
    if os.name != "nt":
        return ""
    try:
        buf = ctypes.create_unicode_buffer(261)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
            ctypes.c_wchar_p(mountpoint), buf, 261, None, None, None, None, 0)
        return buf.value if ok else ""
    except Exception:  # noqa: BLE001 - label is cosmetic
        return ""


def _kind_from_opts(opts: str) -> str:
    o = (opts or "").lower()
    if "remote" in o:
        return "remote"
    if "removable" in o:
        return "removable"
    if "fixed" in o:
        return "fixed"
    return "unknown"


def get_drive_info(mountpoint: str, device: str = "", fstype: str = "",
                   opts: str = "") -> DriveInfo | None:
    """Build a DriveInfo for a path. Returns None if usage cannot be read."""
    try:
        usage = shutil.disk_usage(mountpoint)
    except (OSError, PermissionError) as exc:
        log.info("Skipping %s: %s", mountpoint, exc)
        return None
    # Define used = total - free so used + free == total on every filesystem. Some
    # filesystems (reserved blocks, overlay mounts) report a 'used' figure that does not
    # add up, which would make charts and percentages disagree.
    used = max(0, usage.total - usage.free)
    return DriveInfo(
        mountpoint=mountpoint, device=device or mountpoint, fstype=fstype,
        label=get_volume_label(mountpoint), kind=_kind_from_opts(opts),
        total=usage.total, used=used, free=usage.free,
    )


def list_drives(include_removable: bool = True) -> list[DriveInfo]:
    """Detect mounted drives. On Windows these are C:\\, D:\\, ...

    Optical drives / unreadable (empty card reader) volumes are skipped.
    """
    drives: list[DriveInfo] = []
    try:
        partitions = psutil.disk_partitions(all=False)
    except (OSError, PermissionError) as exc:  # pragma: no cover - platform dependent
        log.error("Could not enumerate drives: %s", exc)
        return drives

    seen: set[str] = set()
    for part in partitions:
        opts = (part.opts or "").lower()
        if "cdrom" in opts or (os.name == "nt" and not part.fstype):
            continue
        if not include_removable and "removable" in opts:
            continue
        if part.mountpoint in seen:
            continue
        info = get_drive_info(part.mountpoint, part.device, part.fstype, part.opts)
        if info is not None and info.total > 0:
            seen.add(part.mountpoint)
            drives.append(info)
    drives.sort(key=lambda d: d.mountpoint.lower())
    return drives

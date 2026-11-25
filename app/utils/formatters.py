"""Human-readable formatting helpers."""
from __future__ import annotations

from datetime import datetime

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def format_size(num_bytes: float, precision: int = 2) -> str:
    """Format a byte count using binary (1024) steps, e.g. ``1.50 GB``."""
    value = float(num_bytes)
    if value < 0:
        return "-" + format_size(-value, precision)
    for unit in _UNITS:
        if value < 1024 or unit == _UNITS[-1]:
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.{precision}f} {unit}"
        value /= 1024
    return f"{value:.{precision}f} PB"  # pragma: no cover


def format_percent(part: float, whole: float, precision: int = 1) -> str:
    if whole <= 0:
        return "0.0%"
    return f"{part / whole * 100:.{precision}f}%"


def percent(part: float, whole: float) -> float:
    return 0.0 if whole <= 0 else part / whole * 100.0


def format_count(n: int) -> str:
    return f"{n:,}"


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def format_timestamp(ts: datetime | float | None) -> str:
    if ts is None:
        return "Never"
    if not isinstance(ts, datetime):
        ts = datetime.fromtimestamp(ts)
    return ts.strftime("%Y-%m-%d %H:%M")


def elide_middle(text: str, max_len: int = 80) -> str:
    if len(text) <= max_len:
        return text
    keep = max_len - 3
    head = keep // 2
    tail = keep - head
    return text[:head] + "..." + text[-tail:]

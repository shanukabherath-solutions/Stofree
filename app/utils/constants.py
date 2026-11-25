"""Application-wide constants."""
from __future__ import annotations

APP_NAME = "Stofree"
APP_SUBTITLE = "Windows Disk Space Analyzer"
APP_ORG = "Stofree"
APP_ID = "Stofree.DiskSpaceAnalyzer"      # Windows AppUserModelID (taskbar identity)
APP_VERSION = "1.0.0"
APP_FILE_PREFIX = "stofree"               # default prefix of exported report files

# Windows file attribute / reparse tag constants (used by the scanner).
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003  # junctions and volume mount points
IO_REPARSE_TAG_SYMLINK = 0xA000000C

# Scanner defaults
DEFAULT_TOP_FILES = 10_000        # how many of the largest files are retained
MAX_ERRORS_KEPT = 500             # cap on stored error messages (count is unbounded)
PROGRESS_EVERY_ENTRIES = 750      # progress callback granularity
PROGRESS_MIN_INTERVAL = 0.10      # seconds between progress emissions

OTHER_CATEGORY = "Other"

# Extension -> category.  Extensions are lower-case and include the dot.
CATEGORY_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "Images": (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff",
               ".svg", ".ico", ".heic", ".raw"),
    "Videos": (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg"),
    "Audio": (".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"),
    "Documents": (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt",
                  ".rtf", ".odt", ".csv", ".md"),
    "Applications": (".exe", ".msi", ".dll", ".sys", ".apk", ".msix"),
    "Archives": (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".cab"),
    "Development": (".py", ".js", ".ts", ".html", ".css", ".json", ".java", ".c", ".cpp",
                    ".h", ".cs", ".go", ".rs", ".xml", ".yml", ".yaml", ".pyc"),
}

CATEGORY_ORDER = list(CATEGORY_EXTENSIONS) + [OTHER_CATEGORY]

CATEGORY_COLORS = {
    "Images": "#4F8EF7",
    "Videos": "#E5574F",
    "Audio": "#A06CD5",
    "Documents": "#2FB57C",
    "Applications": "#F2A33A",
    "Archives": "#E07BB0",
    "Development": "#35B6C9",
    "Other": "#8A93A6",
}

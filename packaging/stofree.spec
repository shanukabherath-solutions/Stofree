# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Stofree (Windows). Run from the project root:

    pyinstaller --noconfirm --clean packaging\\Stofree.spec                      # ONEDIR (default)
    set STOFREE_BUILD_MODE=onefile && pyinstaller ... packaging\\Stofree.spec    # ONEFILE

``scripts\\build_windows.ps1`` does this for you (and is the recommended way).

ONEDIR  -> dist\\Stofree\\Stofree.exe + supporting files (_internal\\...). This is the build the
           Inno Setup installer packages. Fastest start-up, easiest for antivirus/LGPL review.
ONEFILE -> a single Stofree.exe that unpacks itself to a temporary folder on every launch.
           Convenient to copy around; slower to start. Stofree never writes settings or reports
           there (see app/utils/paths.py); user data lives in %LOCALAPPDATA%\\Stofree.

The whole ``assets`` folder (logo.png, Ani.gif, stofree.ico, UI icons) is bundled and found at
run time through app/utils/assets.py (sys._MEIPASS).
"""
import os
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent                      # noqa: F821  (SPECPATH is injected)
ICON = ROOT / "assets" / "branding" / "stofree.ico"
VERSION_FILE = ROOT / "packaging" / "version_info.txt"
MODE = os.environ.get("STOFREE_BUILD_MODE", "onedir").strip().lower()

if MODE not in ("onedir", "onefile"):
    raise SystemExit(f"STOFREE_BUILD_MODE must be 'onedir' or 'onefile', not {MODE!r}")
# Fail loudly instead of silently producing an exe without branding / version resources.
for required in (ICON, VERSION_FILE, ROOT / "assets" / "branding" / "logo.png",
                 ROOT / "assets" / "branding" / "Ani.gif"):
    if not required.is_file():
        raise SystemExit(f"Required build input is missing: {required}")

a = Analysis(                                                # noqa: F821
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / "assets"), "assets")],
    hiddenimports=["PySide6.QtSvg", "PySide6.QtCharts"],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "tkinter", "pytest", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)                                            # noqa: F821

_common = dict(
    name="Stofree",                       # -> Stofree.exe
    icon=str(ICON),
    version=str(VERSION_FILE),            # Windows version resource (Details tab)
    console=False,                        # GUI application: no console window
    disable_windowed_traceback=False,
    upx=False,                            # UPX-packed binaries trigger more antivirus false positives
    uac_admin=False,                      # never request elevation: scanning needs no admin rights
)

if MODE == "onedir":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **_common)   # noqa: F821
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Stofree")  # noqa: F821
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **_common)     # noqa: F821

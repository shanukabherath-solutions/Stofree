<p align="center">
  <img src="assets/branding/logo.png" alt="Stofree" width="260">
</p>

<h3 align="center">Windows Disk Space Analyzer</h3>

**Stofree** shows you where your disk space went. It scans a drive or folder, then lets you explore
folder sizes, find the largest files, see storage by file type, and export the results to CSV/JSON.

Stofree is **strictly read-only**: it never deletes, moves, renames or modifies anything, and it
never opens file contents - only names, sizes and folder structure are read.

## Features

- **Dashboard** - every Windows drive with capacity, used/free space, usage %, animated usage bars,
  a donut chart and last-scan information.
- **Drive Scanner** - background scan with live progress, current folder, file/folder counters,
  elapsed time, cancellation, and a log of skipped links and access errors.
- **Largest Files** - the biggest files found, with sorting (largest / smallest / name / type),
  a search box and a category filter. Backed by a table model, so it stays fast with large results.
- **Folder Explorer** - sortable folder tree with size, share of parent, file and sub-folder counts,
  plus a folder-size comparison chart.
- **File Types** - storage and share per category (Images, Videos, Audio, Documents, Applications,
  Archives, Development, Other) with a donut chart and a per-extension table.
- **Reports** - CSV (files, folders) and JSON export with drive, path, size, type and scan timestamp.
- **Settings** - dark / light / system theme, animations, number of largest files kept, removable
  drives, log folder, About.
- **Branding** - theme-aware Stofree wordmark (dark/light variants), `logo.png` loading screen with
  animated `Ani.gif`, application and taskbar icon.

## Screenshots

> Placeholders - add your own captures to `docs/screenshots/`.

| Dashboard | Folder Explorer | File Types |
|---|---|---|
| `docs/screenshots/dashboard.png` | `docs/screenshots/explorer.png` | `docs/screenshots/types.png` |

## Technology

Python 3.12, PySide6 (Qt 6: GUI, Qt Charts, QMovie), `os.scandir`/`pathlib`, `psutil` and `shutil`
for drive information, `QThread` workers, `pytest` / `pytest-qt`.
For building: PyInstaller (executable), Pillow (icon and installer artwork) and Inno Setup 7 (installer).

## Installation (Windows 10 / 11)

1. Install **Python 3.12 (64-bit)** from <https://www.python.org/downloads/>
   (tick *"Add python.exe to PATH"*).
2. Open **PowerShell** in the project folder and run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process RemoteSigned` once, or use
`.\.venv\Scripts\activate.bat` from Command Prompt.

## Run Stofree

```powershell
python main.py
```

Stofree does **not** need administrator rights. Folders Windows protects (for example
`System Volume Information`) are reported as access errors and skipped; they never stop the scan.

| Option | Effect |
|---|---|
| `python main.py --no-splash` | Start without the animated splash screen |
| `STOFREE_NO_SPLASH=1` (environment variable) | Same, without a command-line flag |

## Run the tests

```powershell
pip install pytest-qt        # pytest itself is in requirements.txt
python -m pytest
```

The GUI tests run headless (Qt `offscreen` platform) and only ever touch temporary directories.
One test (a real NTFS junction) runs on Windows only and is skipped elsewhere.

## Branding and assets

| File | What it is | Used for |
|---|---|---|
| `assets/branding/logo.png` | Square emblem (triangle, cursor, paper + wordmark) | **Loading screen**, **main logo**: window / taskbar / executable icon, About section, collapsed-sidebar icon |
| `assets/branding/darkmode_logo.png` | White wordmark | **Dashboard header and sidebar in dark mode** |
| `assets/branding/lightmode_logo.png` | Dark wordmark | **Dashboard header and sidebar in light mode** |
| `assets/branding/Ani.gif` | 4-frame animation | Loading indicator on the splash screen (played with `QMovie`) |
| `assets/branding/stofree.ico` | Multi-resolution Windows icon | Executable icon (generated from `logo.png`) |

- The supplied artwork is used **as-is** and is never modified. Automated tests pin the SHA-256
  checksum of every supplied file so accidental changes are caught.
- The wordmark in the dashboard header and sidebar switches **live** when you change the theme
  (Settings, the sun/moon button, or "Follow system"). If a themed image is missing, Stofree falls
  back to the plain text name in the theme's text colour.
- `logo.png` is designed for light backgrounds (dark outline and lettering), so the splash card is
  light, and in the About section it sits on a light badge.
- The window/taskbar icon is composed at run time from `logo.png`: only the empty transparent margins
  are trimmed; proportions and transparency are preserved. On a dark taskbar the emblem's black
  outline blends in, while the yellow triangle and cursor stay clearly visible.
- `stofree.ico` is regenerated by `python tools/make_icon.py` (needs Pillow) using the same
  composition. It reads `logo.png` read-only.
- On Windows the process sets its own AppUserModelID (`Stofree.DiskSpaceAnalyzer`) so the taskbar
  shows the Stofree icon rather than Python's.

### Splash screen behaviour

The splash is created once at start-up. It shows `logo.png` with `Ani.gif` playing beside it at its
original aspect ratio, and closes automatically when the dashboard is ready (after at least ~1.4 s so the animation is actually seen).
Drive detection runs on a worker thread, so the animation never freezes. If the GIF cannot be loaded
the splash shows the logo alone; if no artwork loads at all, Stofree simply opens the main window.

### Asset loading

`app/utils/assets.py` resolves paths relative to the project (development), `sys._MEIPASS`
(PyInstaller) or the `STOFREE_ASSETS` environment variable. Missing or corrupt images return `None`
instead of raising, and no absolute paths are hard-coded. Every lookup (logo, GIF, UI icons, stylesheet check-mark)
goes through this one resolver.

## Build, package and install (Windows)

Stofree ships as a PyInstaller application plus an Inno Setup 7 installer. Everything is driven by one
script and works from the existing `.venv` (Python 3.12, 64-bit):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt     # once
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

(`build_windows.bat` in the project root is a convenience wrapper for the same script.)

| Option | Effect |
|---|---|
| *(none)* | ONEDIR build + validation + installer (if Inno Setup 7 is installed) |
| `-OneFile` | additionally build the standalone single-file `Stofree.exe` |
| `-RunTests` | run `pytest` first (needs `pytest-qt`) |
| `-SkipInstaller` | build the executables only |
| `-SkipSelfTest` | skip the post-build `--self-test` (e.g. a build server with no desktop session) |
| `-InnoCompiler <path>` | use a specific `ISCC.exe` (otherwise `$env:INNO_SETUP_COMPILER`, `PATH`, and the usual `Inno Setup 7` folders are searched) |

The script (1) checks the `.venv` is Python 3.12 64-bit, (2) verifies the dependencies and that
`APP_VERSION`, `packaging\version_info.txt` agree, (3) installs PyInstaller/Pillow if missing, (4) optionally
tests, (5) builds ONEDIR, (6) validates it (files present, Windows version resource, `--self-test`),
(7) optionally builds ONEFILE, (8) compiles the installer, (9) prints where everything is. Any failing step
stops the script with a message and exit code 1. If Inno Setup 7 is not installed the script says so in a
warning and in the summary - it does not pretend an installer was built.
Install Inno Setup 7 with `winget install --id JRSoftware.InnoSetup.7 -e -s winget`.

### Output

```
dist\Stofree\Stofree.exe          ONEDIR: exe + _internal\ (Python, Qt, assets)   <- what the installer packages
dist\onefile\Stofree.exe          ONEFILE (only with -OneFile): one self-extracting exe
installer-output\Stofree-Setup.exe  the installation wizard
build\                            PyInstaller work files and self-test reports
```

`build\`, `dist\` and `installer-output\` are git-ignored; do not commit binaries.

| Source file | Purpose |
|---|---|
| `packaging/Stofree.spec` | PyInstaller spec (windowed, no console, bundles `assets\`, icon, version info, never requests admin). `STOFREE_BUILD_MODE=onedir` (default) or `onefile` |
| `packaging/version_info.txt` | Windows version resource: product *Stofree*, *Windows Disk Space Analyzer*, `Stofree.exe` |
| `installer/Stofree.iss` | Inno Setup 7 script |
| `installer/TERMS_AND_CONDITIONS.txt` | licence text shown in the wizard (**draft - needs legal review**) |
| `tools/make_installer_images.py` | creates the wizard artwork from `logo.png` (read-only) into `installer/assets/` |
| `scripts/build_windows.ps1` | the build automation |

**ONEDIR vs ONEFILE.** ONEDIR starts faster, is what the installer ships and tends to cause fewer antivirus
false positives. ONEFILE is one file to copy around but unpacks itself to a temporary folder on every launch
(slower start). Both behave identically: neither writes anything to that temporary folder.

### The installer

`Stofree-Setup.exe` shows: Welcome, Licence agreement (you must accept to continue), Destination folder,
Ready to install, Installation progress, and Completion with a **Launch Stofree** checkbox (ticked by default).

- Default folder `C:\Program Files\Stofree` (changeable on the Destination page). Setup first asks whether to install
  *for all users* (needs administrator rights, so Windows shows a UAC prompt) or *for me only* (no admin rights
  needed; installs under `%LOCALAPPDATA%\Programs`).
- Start Menu shortcut **Stofree** and an optional **Stofree** desktop shortcut (ticked by default), both
  pointing at the installed `Stofree.exe` with the install folder as working directory.
- Registered in Windows *Installed apps* with the Stofree icon; upgrades install over the previous version.
- The program is launched from the final page with the normal user's rights, never elevated.
- Uninstall removes the installed program files only. It then **asks** whether to also delete your settings and
  logs in `%LOCALAPPDATA%\Stofree` (default **No**; never deleted in silent mode). Reports you exported are never
  touched.
- Silent install for deployment: `Stofree-Setup.exe /SILENT` (or `/VERYSILENT`), optionally `/DIR="D:\Apps\Stofree"`
  and `/TASKS="!desktopicon"`.

> **Unsigned installer.** The installer and exe are not code-signed, so Windows SmartScreen may show an
> "unknown publisher" warning. Signing needs a code-signing certificate (Inno Setup 7's `SignTool` directive
> supports it) and is not configured.

### Where Stofree keeps its data

| What | Where |
|---|---|
| Program files | the install folder (read-only for normal users; nothing is ever written there) |
| Settings | `%LOCALAPPDATA%\Stofree\settings.ini` (older dev builds used the registry; those values are copied over once) |
| Log | `%LOCALAPPDATA%\Stofree\logs\stofree.log` |
| Reports | only where *you* choose in the Save dialog |

Nothing is written into PyInstaller's temporary extraction folder, the install folder, or the working directory,
and Stofree can be started from any working directory.

### Verifying a packaged build

`Stofree.exe --self-test report.json` runs a headless check inside the *packaged* app and writes a JSON report
(exit code 0 = everything passed): bundled assets present, logo and `Ani.gif` decode, SVG icons render, splash
and main window construct (including Qt Charts), data folder writable and outside the bundle, settings
round-trip, drive detection, a real scan with file/folder/type analysis, CSV + JSON export, and scan
cancellation. `build_windows.ps1` runs it automatically on the exe(s) it builds.

### Release test checklist (manual, on a clean Windows 10/11 machine or VM with no Python)

- [ ] `Stofree-Setup.exe` shows Welcome, Licence (cannot continue until accepted), Destination, Ready, Progress, Finished
- [ ] Changing the destination folder installs there; default is under Program Files
- [ ] Desktop and Start Menu shortcuts start the *installed* Stofree.exe; "Launch Stofree" works (and Stofree is not elevated)
- [ ] Splash animation plays, logo shows, dashboard opens; drives are detected
- [ ] Scan a drive and a folder; **Cancel** stops it and keeps partial results
- [ ] Largest Files, Folder Explorer and File Types show data; CSV and JSON export open correctly
- [ ] Settings survive a restart (`%LOCALAPPDATA%\Stofree\settings.ini` exists)
- [ ] Uninstall via *Installed apps*: program removed, prompt about settings/logs defaults to No, exported reports untouched
- [ ] Reinstall/upgrade over an existing install works
- [ ] Same checks for the ONEFILE exe (run from a folder with spaces in its path)

### What has and has not been verified

The packaging was developed on Linux. **Verified there:** the full `pytest` suite; PyInstaller builds of
`Stofree.spec` in both ONEDIR and ONEFILE modes (Linux target) and the resulting binaries pass `--self-test`
and reach the main window in the normal start-up path; `build_windows.ps1` parses with PowerShell 7 and its
steps 1-5 and failure paths were dry-run against a stand-in `.venv`.
**Not verified (needs Windows):** the actual `Stofree.exe` (icon/version resource embedding, Windows Qt
plugins), `ISCC` compilation of `Stofree.iss`, the installer wizard, shortcuts, uninstall behaviour, SmartScreen
and antivirus behaviour. Do not treat the installer as release-ready until the checklist above has been run.

## Project architecture

```
Stofree/
├── main.py                  entry point (--no-splash)
├── app/
│   ├── launcher.py          splash -> main window sequencing, Windows taskbar identity
│   ├── main_window.py       sidebar (logo + navigation) and stacked pages
│   ├── state.py             shared state: drives, scan result, settings, last-scan info
│   ├── theme.py             dark / light palettes and stylesheet
│   ├── ui/                  dashboard, scanner, largest_files, folder_explorer, file_types,
│   │                        reports, settings, branding (logo/icon), splash, widgets, icons
│   ├── core/                drive_manager, disk_scanner, file_analyzer, folder_analyzer,
│   │                        report_generator  (no GUI imports)
│   ├── workers/             scan_worker (scanning thread), drive_worker (drive detection)
│   ├── selftest.py          headless verification of a packaged build (--self-test)
│   └── utils/               assets, constants, formatters, logger, paths, settings_store
├── assets/branding/         logo.png, darkmode_logo.png, lightmode_logo.png, Ani.gif, stofree.ico
├── assets/icons/            UI icons (SVG)
├── packaging/               Stofree.spec (PyInstaller) + version_info.txt (Windows version resource)
├── installer/               Stofree.iss (Inno Setup 7) + TERMS_AND_CONDITIONS.txt
├── scripts/build_windows.ps1  build automation (exe + installer)
├── tools/                   make_icon.py (ICO), make_installer_images.py (wizard artwork)
└── tests/                   core, GUI-integration, branding/splash and asset tests
```

The internal Python package is still called `app`; only user-facing names changed to Stofree.

## Safety

- Read-only: no deleting, moving, renaming, formatting or modifying - the only files ever written are
  the reports you explicitly save, plus `settings.ini` and a log file in `%LOCALAPPDATA%\Stofree`.
- File contents are never read; only metadata from `os.scandir`.
- Symbolic links, junctions, mount points and other reparse-point **directories** are never followed
  (no loops, no double counting). Link-like files are skipped too.
- Cancelling stops further traversal immediately and keeps the partial results.

## Known limitations

- Sizes are logical file sizes, not "size on disk"; hard links are counted per path.
- Reparse-point directories are skipped by design, so content under e.g. OneDrive folders that Windows
  exposes as reparse points may not be counted.
- Developed and automatically tested on Linux using Qt's headless platform. Windows-specific code
  (drive labels, junction detection, taskbar ID, ICO, the Windows exe and the Inno Setup installer) follows
  documented Windows APIs but has **not** been built or run on Windows by the author of this change - see
  *What has and has not been verified* above. Please run `python -m pytest` and `scripts\build_windows.ps1`
  and the release checklist on your machine.
- Publisher/company metadata is only the existing name "Stofree"; the owner, copyright holder, licence type and
  governing law are placeholders in `installer\TERMS_AND_CONDITIONS.txt` and must be completed and legally reviewed.
- PySide6/Qt (LGPL) and other third-party components carry redistribution obligations that this repository does
  not yet address (no third-party notices file); have this reviewed before public distribution.
- The wordmark and icon were checked visually only in Qt's headless renderer, not on a real Windows
  display or taskbar.

## Future improvements

Treemap view, scan history and comparison, size-on-disk and duplicate detection, an MFT-based fast
scanner for NTFS, localisation, code signing, and automatic update checks.

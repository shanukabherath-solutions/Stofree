"""Static checks on the packaging / installer sources (they cannot be *built* on Linux)."""
import ast
import re
from pathlib import Path

import pytest

from app.utils.constants import APP_NAME, APP_VERSION

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "Stofree.spec"
VERSION_INFO = ROOT / "packaging" / "version_info.txt"
ISS = ROOT / "installer" / "Stofree.iss"
TERMS = ROOT / "installer" / "TERMS_AND_CONDITIONS.txt"
PS1 = ROOT / "scripts" / "build_windows.ps1"


def text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ------------------------------------------------------------------ PyInstaller spec
def test_spec_is_valid_python_and_configured_for_a_windowed_stofree_exe():
    src = text(SPEC)
    ast.parse(src)
    assert 'name="Stofree"' in src                       # -> Stofree.exe
    assert "console=False" in src                        # no console window
    assert "uac_admin=False" in src                      # never asks for elevation
    assert "stofree.ico" in src and "version_info.txt" in src
    assert '(str(ROOT / "assets"), "assets")' in src     # logo.png, Ani.gif, icons
    assert "COLLECT(" in src and "STOFREE_BUILD_MODE" in src
    assert "onedir" in src and "onefile" in src


def test_gitignore_keeps_spec_but_ignores_build_output():
    lines = [ln.strip() for ln in text(ROOT / ".gitignore").splitlines()]
    assert "*.spec" not in lines
    for must in ("/build/", "/dist/", "/installer-output/"):
        assert must in lines


# ------------------------------------------------------------------ versions and metadata
def test_version_resource_matches_app_version():
    vi = text(VERSION_INFO)
    quad = ", ".join(APP_VERSION.split(".")) + ", 0"
    assert f"filevers=({quad})" in vi and f"prodvers=({quad})" in vi
    assert f"StringStruct('FileVersion', '{APP_VERSION}')" in vi
    assert f"StringStruct('ProductVersion', '{APP_VERSION}')" in vi
    assert f"StringStruct('ProductName', '{APP_NAME}')" in vi
    assert "StringStruct('OriginalFilename', 'Stofree.exe')" in vi
    assert "Windows Disk Space Analyzer" in vi


def test_inno_fallback_version_matches_app_version():
    assert f'#define AppVersion "{APP_VERSION}"' in text(ISS)


def test_no_invented_publisher_or_copyright_details():
    assert "StringStruct('LegalCopyright'" not in text(VERSION_INFO)
    assert not re.search(r"^AppCopyright=", text(ISS), re.M)
    assert '#define AppPublisher   "Stofree"' in text(ISS)        # existing project/org name only


# ------------------------------------------------------------------ Inno Setup script
def iss_setup_value(name: str) -> str:
    m = re.search(rf"^{name}=(.*)$", text(ISS), re.M)
    assert m, f"[Setup] directive {name} missing"
    return m.group(1).strip()


@pytest.mark.parametrize("name,expected", [
    ("OutputBaseFilename", "Stofree-Setup"),
    ("LicenseFile", "TERMS_AND_CONDITIONS.txt"),
    ("DefaultDirName", r"{autopf}\{#AppName}"),
    ("DisableWelcomePage", "no"),            # Inno skips the Welcome page unless this is "no"
    ("DisableDirPage", "no"),
    ("DisableReadyPage", "no"),
    ("DisableFinishedPage", "no"),
    ("SetupArchitecture", "x64"),            # Inno Setup 7: installers are 32-bit unless set
    ("ArchitecturesInstallIn64BitMode", "x64compatible"),
    ("PrivilegesRequired", "admin"),
    ("PrivilegesRequiredOverridesAllowed", "dialog"),
    ("OutputDir", r"..\installer-output"),
    ("SetupIconFile", r"..\assets\branding\stofree.ico"),
    ("UninstallDisplayIcon", r"{app}\{#AppExeName}"),
])
def test_inno_setup_directives(name, expected):
    assert iss_setup_value(name) == expected


def test_inno_packages_whole_onedir_folder_not_just_the_exe():
    assert re.search(r'Source: "\.\.\\dist\\Stofree\\\*";.*recursesubdirs.*createallsubdirs', text(ISS))


def test_inno_shortcuts_tasks_and_launch_option():
    t = text(ISS)
    # desktop shortcut task is ticked by default (no "unchecked" flag)
    task = re.search(r'^Name: "desktopicon";.*$', t, re.M).group(0)
    assert "unchecked" not in task
    icons = re.findall(r"^Name: \"\{auto(programs|desktop)\}\\\{#AppName\}\".*$", t, re.M)
    assert sorted(icons) == ["desktop", "programs"]
    for line in re.findall(r"^Name: \"\{auto(?:programs|desktop)\}.*$", t, re.M):
        assert r'Filename: "{app}\{#AppExeName}"' in line and 'WorkingDir: "{app}"' in line
    run = re.search(r"^\[Run\]\n(?:;.*\n)*(Filename:.*)$", t, re.M).group(1)
    assert "postinstall" in run and "skipifsilent" in run and "unchecked" not in run
    assert "runasoriginaluser" in run, "Stofree must not be launched elevated by Setup"


def test_inno_uninstaller_never_deletes_user_data_silently():
    t = text(ISS)
    assert "[UninstallDelete]" not in t                           # no unconditional deletion
    assert "UninstallSilent" in t and "MB_DEFBUTTON2" in t and "IDNO" in t
    assert r"{localappdata}\{#AppName}" in t


def test_installer_sources_are_ascii_and_referenced_files_exist():
    for f in (ISS, TERMS, PS1):
        f.read_bytes().decode("ascii")                            # Inno 7 rejects invalid bytes
    assert (ROOT / "assets" / "branding" / "stofree.ico").is_file()
    assert (ROOT / "tools" / "make_installer_images.py").is_file()
    t = text(ISS)
    for name in re.findall(r"assets\\(wizard_[a-z0-9_x]+\.png)", t):
        assert name in text(ROOT / "tools" / "make_installer_images.py") or re.match(
            r"wizard_(large_\d+x\d+|small_\d+)\.png", name)


# ------------------------------------------------------------------ Terms and Conditions
@pytest.mark.parametrize("heading", [
    "SOFTWARE USAGE", "OWNERSHIP AND INTELLECTUAL PROPERTY", "RESTRICTIONS ON REDISTRIBUTION",
    "USER RESPONSIBILITY", "WARRANTY DISCLAIMER", "LIMITATION OF LIABILITY",
    "SOFTWARE UPDATES", "UNINSTALLATION",
])
def test_terms_contain_required_sections(heading):
    assert heading in text(TERMS)


def test_terms_flag_legal_review_and_make_no_unfounded_claims():
    t = " ".join(text(TERMS).split())                              # undo hard line wrapping
    assert "LEGAL REVIEW REQUIRED" in t and "TO BE COMPLETED" in t
    assert "has not been reviewed by a lawyer" in t
    assert "has not been certified" in t                          # explicit non-claim
    for forbidden in ("GDPR-compliant", "fully compliant", "guarantee", "ISO 27001", "is certified", "are certified"):
        assert forbidden not in t
    assert "%LOCALAPPDATA%\\Stofree" in t                         # real data location
    assert "no network, upload, telemetry" in t                   # matches app code (no network code)


def test_app_has_no_network_code_matching_the_privacy_statement():
    bad = re.compile(r"\b(socket|urllib|urllib3|requests|http\.client|httpx|aiohttp|QtNetwork|QNetwork\w*)\b")
    hits = [str(p.relative_to(ROOT)) for p in list((ROOT / "app").rglob("*.py")) + [ROOT / "main.py"]
            if bad.search(text(p)) and p.name != "test_packaging.py"]
    assert not hits, f"network-related code found (update TERMS section 9 if intentional): {hits}"


# ------------------------------------------------------------------ build script
def test_build_script_has_required_steps_and_options():
    t = text(PS1)
    for needle in ("3.12", ".venv", "PyInstaller", "ISCC.exe", "Inno Setup 7", "Stofree-Setup.exe",
                   "-OneFile", "SkipInstaller", "--self-test", "exit 1", "STOFREE_BUILD_MODE",
                   "/DAppVersion="):
        assert needle in t.replace("[switch]$OneFile", "-OneFile"), needle

"""Asset loading, original-artwork integrity and packaging-path handling."""
import hashlib
import re
import shutil
import sys
from pathlib import Path

import pytest

from app.utils import assets

ROOT = Path(__file__).resolve().parent.parent
# SHA-256 of the artwork exactly as supplied. If these fail, the originals were altered.
ORIGINAL_SHA256 = {
    "logo.png": "d8c66a013ddd2f0d18102bec74652b1919ceec7aafaa239b3e6cf3d1e8f9cf14",
    "darkmode_logo.png": "97fe8450056233ebccc16e3d98826660a7390f0399bb9a8490c27ebbb7d0caa9",
    "lightmode_logo.png": "dad8df05da357c4021774ca212874d88cdc4c406fc0ddfddd66328798064897e",
    "Ani.gif": "54833c4581da31a826cad317d0f4f93c17dc606fb9a7d67f1c4880918d3726d3",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("name,expected", ORIGINAL_SHA256.items())
def test_branding_files_are_present_and_unmodified(name, expected):
    assert sha256(ROOT / "assets" / "branding" / name) == expected


def test_asset_paths_resolve_relative_to_project(monkeypatch):
    monkeypatch.delenv("STOFREE_ASSETS", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert assets.base_dir() == ROOT
    assert assets.branding_path("logo.png") == ROOT / "assets" / "branding" / "logo.png"
    assert assets.branding_path("Ani.gif").is_file()


def test_missing_asset_returns_none_not_exception():
    assert assets.branding_path("does_not_exist.png") is None
    assert assets.existing_asset("nope", "nothing.svg") is None


def test_pyinstaller_frozen_layout_is_used(tmp_path, monkeypatch):
    """Simulate a PyInstaller bundle: assets are found below sys._MEIPASS."""
    bundle = tmp_path / "_MEI12345"
    shutil.copytree(ROOT / "assets", bundle / "assets")
    monkeypatch.delenv("STOFREE_ASSETS", raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    assert assets.base_dir() == bundle
    assert assets.branding_path("logo.png") == bundle / "assets" / "branding" / "logo.png"
    assert assets.branding_path("Ani.gif").is_file()
    assert assets.asset_path("icons", "drive.svg").is_file()


def test_environment_override(tmp_path, monkeypatch):
    (tmp_path / "assets" / "branding").mkdir(parents=True)
    monkeypatch.setenv("STOFREE_ASSETS", str(tmp_path))
    assert assets.base_dir() == tmp_path
    assert assets.branding_path("logo.png") is None          # empty override folder


def test_loaders_handle_missing_and_corrupt_images(qapp, tmp_path, monkeypatch):
    (tmp_path / "assets" / "branding").mkdir(parents=True)
    (tmp_path / "assets" / "branding" / "logo.png").write_bytes(b"this is not a png")
    monkeypatch.setenv("STOFREE_ASSETS", str(tmp_path))
    assets.load_pixmap.cache_clear()
    try:
        assert assets.load_logo() is None                      # corrupt -> None
        assert assets.load_pixmap("missing.png") is None       # missing -> None
        assert assets.logo_aspect_ratio() == pytest.approx(1.0)          # safe default
    finally:
        assets.load_pixmap.cache_clear()


def test_logo_roles_load_with_alpha(qapp):
    assets.load_pixmap.cache_clear()
    main = assets.load_logo()                                   # logo.png: square emblem
    assert main is not None and (main.width(), main.height()) == (2000, 2000)
    assert main.hasAlphaChannel()
    dark, light = assets.load_themed_logo(True), assets.load_themed_logo(False)
    assert (dark.width(), dark.height()) == (2000, 473) == (light.width(), light.height())
    assert dark.hasAlphaChannel() and light.hasAlphaChannel()
    assert dark.toImage() != light.toImage()                    # genuinely different artwork


def test_theme_to_logo_file_mapping():
    assert assets.themed_logo_file(True) == "darkmode_logo.png"
    assert assets.themed_logo_file(False) == "lightmode_logo.png"
    assert assets.LOGO_FILE == "logo.png"


def test_no_hardcoded_absolute_paths_in_source():
    bad = re.compile(r"(?:[A-Za-z]:\\\\Users|[A-Za-z]:\\Users|/home/|/Users/|/mnt/)")
    offenders = []
    for py in list((ROOT / "app").rglob("*.py")) + [ROOT / "main.py"]:
        for n, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if bad.search(line):
                offenders.append(f"{py.relative_to(ROOT)}:{n}: {line.strip()}")
    assert not offenders, "\n".join(offenders)


def test_ico_is_multi_resolution_and_packaging_includes_assets():
    PIL = pytest.importorskip("PIL.Image")
    ico = ROOT / "assets" / "branding" / "stofree.ico"
    with PIL.open(ico) as im:
        sizes = set(im.info["sizes"])
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= sizes
    spec = (ROOT / "packaging" / "stofree.spec").read_text(encoding="utf-8")
    assert '"assets"' in spec and "stofree.ico" in spec and 'name="Stofree"' in spec

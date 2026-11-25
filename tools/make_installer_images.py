"""Generate the Inno Setup wizard images from the supplied logo.png.

    pip install pillow
    python tools/make_installer_images.py

The original PNG is only *read*. The emblem (empty transparent margins trimmed, proportions
kept) is centred on a white background, because logo.png is designed for light backgrounds.
Output goes to installer/assets/ (git-ignored; scripts/build_windows.ps1 regenerates it):

    wizard_large_<w>x<h>.png   Welcome / Finished pages   (Inno recommends 164x314 @100%)
    wizard_small_<n>.png       header of the other pages  (square; 58 @100%)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "branding" / "logo.png"
OUT = ROOT / "installer" / "assets"
LARGE = ((164, 314), (246, 459), (328, 604))      # 100%, 150%, 200% DPI
SMALL = (58, 87, 116)                              # 100%, 150%, 200% DPI
MARGIN = 0.06                                      # fraction of the canvas left empty on each side


def emblem() -> Image.Image:
    with Image.open(SRC) as im:
        logo = im.convert("RGBA")
    bbox = logo.getchannel("A").getbbox()
    return logo.crop(bbox) if bbox else logo


def compose(art: Image.Image, size: tuple[int, int]) -> Image.Image:
    w, h = size
    box = (w * (1 - 2 * MARGIN), h * (1 - 2 * MARGIN))
    scale = min(box[0] / art.width, box[1] / art.height)          # one scale -> no distortion
    nw, nh = max(1, round(art.width * scale)), max(1, round(art.height * scale))
    scaled = art.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", size, (255, 255, 255, 255))
    canvas.alpha_composite(scaled, ((w - nw) // 2, (h - nh) // 2))
    return canvas.convert("RGB")


def main() -> int:
    if not SRC.is_file():
        print(f"Missing {SRC}", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    art = emblem()
    for size in LARGE:
        compose(art, size).save(OUT / f"wizard_large_{size[0]}x{size[1]}.png")
    for n in SMALL:
        compose(art, (n, n)).save(OUT / f"wizard_small_{n}.png")
    print(f"Wrote {len(LARGE) + len(SMALL)} wizard images to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

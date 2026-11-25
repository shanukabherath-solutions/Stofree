"""Generate assets/branding/stofree.ico (multi-resolution) from the supplied logo.png.

The original PNG is only *read*; it is never modified. The ICO uses the same composition as
the runtime application icon (app/ui/branding.py): the emblem with its empty transparent
margins trimmed, kept proportional and transparent, centred with a small margin.

    pip install pillow
    python tools/make_icon.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "branding" / "logo.png"
DST = ROOT / "assets" / "branding" / "stofree.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)
MARGIN = 0.04            # keep identical to ICON_MARGIN in app/ui/branding.py


def render(emblem: Image.Image, size: int) -> Image.Image:
    inner = size * (1 - 2 * MARGIN)
    scale = inner / max(emblem.width, emblem.height)               # one scale: no distortion
    w, h = max(1, round(emblem.width * scale)), max(1, round(emblem.height * scale))
    scaled = emblem.resize((w, h), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(scaled, ((size - w) // 2, (size - h) // 2))
    return canvas


def main() -> int:
    if not SRC.is_file():
        print(f"Missing {SRC}", file=sys.stderr)
        return 1
    with Image.open(SRC) as im:
        logo = im.convert("RGBA")
    bbox = logo.getchannel("A").getbbox()                            # trim empty margins only
    emblem = logo.crop(bbox) if bbox else logo
    images = [render(emblem, s) for s in SIZES]
    images[-1].save(DST, format="ICO", sizes=[(s, s) for s in SIZES], append_images=images[:-1])
    print(f"Wrote {DST} with sizes {SIZES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

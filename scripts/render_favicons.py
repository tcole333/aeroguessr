#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pillow==13.0.0", "resvg-py==0.5.0"]
# ///
"""Render the raster favicons in frontend/public/ from favicon.svg there.

Usage: uv run scripts/render_favicons.py   (again whenever favicon.svg changes)
Any runner that reads PEP 723 inline script metadata works, such as `pipx run`.

- favicon.ico (32x32) is for browsers without SVG favicons, and for clients that fetch
  /favicon.ico without reading the page.
- apple-touch-icon.png (180x180) is the iOS home-screen icon. iOS fills transparent pixels
  with black, so the plane sits on the theme's cream, --retro-bg in frontend/src/index.css.

With the pinned versions, a re-run reproduces the committed files byte for byte on macOS
arm64. Other platforms may write different bytes for the same picture, through a different
zlib for example.
"""

import io
from pathlib import Path

import resvg_py
from PIL import Image

PUBLIC = Path(__file__).resolve().parent.parent / "frontend" / "public"
CREAM = (245, 240, 225)
TOUCH_ICON_SIZE = 180
# The 24-unit icon drawn at 144 px leaves a margin of about a sixth around the plane.
TOUCH_ICON_DRAWING_SIZE = 144


def render(size: int) -> Image.Image:
    png = resvg_py.svg_to_bytes(svg_path=str(PUBLIC / "favicon.svg"), width=size, height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def main() -> None:
    render(32).save(PUBLIC / "favicon.ico", sizes=[(32, 32)])

    # Centre the plane's own outline: the icon's grid puts it half a unit left of centre.
    drawing = render(TOUCH_ICON_DRAWING_SIZE)
    plane = drawing.crop(drawing.getbbox())
    touch_icon = Image.new("RGB", (TOUCH_ICON_SIZE, TOUCH_ICON_SIZE), CREAM)
    corner = ((TOUCH_ICON_SIZE - plane.width) // 2, (TOUCH_ICON_SIZE - plane.height) // 2)
    touch_icon.paste(plane, corner, plane)
    touch_icon.save(PUBLIC / "apple-touch-icon.png", optimize=True)

    print(f"Wrote favicon.ico and apple-touch-icon.png in {PUBLIC}")


if __name__ == "__main__":
    main()

"""The helper's icon in the Mac's forms, made from fwchelper/helper.ico once and committed:
installer/helper.icns for the application bundle (installer/build_mac.py puts it in) and
fwchelper/helper-menubar.png for the menu bar (fwchelper/mac.py shows it at 18 points, as a
template: the glyph alone, which the Mac colours for a dark or a light bar).

    python installer/icons.py          needs Pillow; run again when helper.ico changes
"""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HELPER = HERE.parent
ICO = HELPER / "fwchelper" / "helper.ico"
ICNS = HERE / "helper.icns"
MENUBAR = HELPER / "fwchelper" / "helper-menubar.png"
SIZES = [(16, 16), (32, 32), (64, 64), (128, 128), (256, 256)]
MENUBAR_PX = 64


def template(ico, px: int = MENUBAR_PX):
    """The menu bar's image: the glyph alone, black on a clear ground, which the Mac draws white on a
    dark bar and black on a light one (a "template" image; fwchelper/mac.py marks it so). Until 1.7.1
    the image was the whole icon, an opaque navy square with a small gold glyph: on the dark menu
    bar most Macs have it could not be seen, and players reported the helper running with no icon
    (9 Nov 2026). The glyph is every pixel that is not the icon's ground colour, taken at the
    icon's full size and scaled down, so its edges are smooth."""
    from PIL import Image, ImageChops
    big = ico.convert("RGB")
    ground = big.getpixel((2, 2))                                   # the icon's corner: its ground colour
    far = ImageChops.difference(big, Image.new("RGB", big.size, ground)).convert("L")
    mask = far.point(lambda v: 255 if v > 28 else 0)                # the anvil and the infinity; the shadow round them is ground
    box = mask.getbbox()
    side = max(box[2] - box[0], box[3] - box[1])
    pad = side // 12
    square = Image.new("L", (side + 2 * pad, side + 2 * pad), 0)
    square.paste(mask.crop(box), (pad + (side - (box[2] - box[0])) // 2, pad + (side - (box[3] - box[1])) // 2))
    alpha = square.resize((px, px), Image.LANCZOS)
    out = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    out.putalpha(alpha)
    return out


def main() -> int:
    """Write helper.icns and the menu bar's template image from helper.ico (needs Pillow); 0 when done."""
    from PIL import Image
    ico = Image.open(ICO)
    ico.convert("RGBA").save(ICNS, sizes=SIZES)
    ico.size = max(ico.info.get("sizes", [(256, 256)]))             # the largest picture the .ico holds
    ico.load()
    template(ico).save(MENUBAR)
    print(f"{ICNS.name} {ICNS.stat().st_size} bytes, {MENUBAR.name} {MENUBAR.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())

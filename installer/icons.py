"""The helper's icon in the Mac's forms, made from fwchelper/helper.ico once and committed:
installer/helper.icns for the application bundle (installer/build_mac.py puts it in) and
fwchelper/helper-menubar.png for the menu bar (fwchelper/mac.py shows it at 18 points).

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


def main() -> int:
    from PIL import Image
    ico = Image.open(ICO)
    ico.convert("RGBA").save(ICNS, sizes=SIZES)
    ico.size = (MENUBAR_PX, MENUBAR_PX)
    ico.load()
    ico.convert("RGBA").save(MENUBAR)
    print(f"{ICNS.name} {ICNS.stat().st_size} bytes, {MENUBAR.name} {MENUBAR.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())

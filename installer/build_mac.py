"""Build the helper's Mac application, ForeverWowCraft Helper.app, and the disk image that
carries it, ForeverWowCraft-Helper-<version>.dmg.

    python3 installer/build_mac.py                 from the helper's folder (or anywhere: the paths are its own)
    python3 installer/build_mac.py --out DIR       where the .dmg goes (default: dist/ beside the helper, or the
                                                   core's dist/ when the helper sits in the core's checkout)
    python3 installer/build_mac.py --stage-only    lay the application out, make no disk image
    python3 installer/build_mac.py --no-python     lay it out without Python (a test of the layout)

What goes in: the helper's files (fwch.py, fwchelper/, addon/, README.md, LICENSE; not the
tests, not this folder, nothing the helper writes; build.py says which) under
Contents/Resources/helper, a Python of its own under Contents/Resources/python (a standalone
build from python-build-standalone, which runs from wherever it is put, checked against its
hash like the Windows build's; the test suite, IDLE and Tk are left out, 30 MB that nothing
here uses), with PyObjC installed into it for the menu bar (installer/build.py's embed.py
fetches; the Windows helper is standard library alone, the Mac's menu bar is not), the icon
as an .icns, and Contents/MacOS/ForeverWowCraft Helper, a script that starts that Python on
fwch.py app (installer/helper.icns is the icon, made from fwchelper/helper.ico by installer/icons.py).
Info.plist names the bundle (com.foreverwowcraft.helper), the version, and
LSUIElement, which keeps the app out of the Dock: it is an icon in the menu bar and nothing
else. The disk image holds the application and a link to Applications, to drag it there.

The application is not signed: the project's business entity signs and notarizes it once it
has an Apple Developer membership (docs/signing.md in the core). Until then Gatekeeper asks
the user to allow it (System Settings > Privacy & Security, Open Anyway). The disk image is
made on a Mac (hdiutil); the layout can be staged anywhere, which the tests do."""
from __future__ import annotations
import argparse
import io
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HELPER = HERE.parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402  - the helper's files and the version, as the Windows build has them
import embed  # noqa: E402  - fetch(): a download checked against its hash, kept in the cache

NAME = build.NAME                                        # "ForeverWowCraft Helper"
APP = f"{NAME}.app"
BUNDLE_ID = "com.foreverwowcraft.helper"
PYTHON_VERSION = "3.14.10"
PYTHON_BUILD = "20261026"                                # python-build-standalone's release
PYTHON_URL = (f"https://github.com/astral-sh/python-build-standalone/releases/download/{PYTHON_BUILD}/"
              f"cpython-{PYTHON_VERSION}+{PYTHON_BUILD}-x86_64-apple-darwin-install_only_stripped.tar.gz")
PYTHON_SHA256 = "2fd8becd48cf0ff5f0a15df3c0db7cae7aa708dcaacf901bd30d6cdd6229370b"
PYTHON_EXE = "bin/python3.14"
PYOBJC = ("pyobjc-core==13.0", "pyobjc-framework-Cocoa==13.0")
# of Python's tree, what the helper has no use for: the test suite, IDLE, Tk and its libraries
PYTHON_LEAVE_OUT = ("lib/python3.14/test", "lib/python3.14/idlelib", "lib/python3.14/tkinter", "lib/python3.14/turtledemo",
                    "lib/python3.14/lib-dynload/_tkinter.cpython-314-darwin.so", "lib/tcl8", "lib/tcl8.6", "lib/tk8.6",
                    "lib/libtcl8.6.dylib", "lib/libtk8.6.dylib", "lib/itcl4.2.4", "lib/thread2.8.9", "lib/tdbc1.1.7",
                    "lib/tdbcmysql1.1.7", "lib/tdbcodbc1.1.7", "lib/tdbcpostgres1.1.7", "lib/sqlite3.45.3", "bin/idle3", "bin/idle3.14",
                    "share")

LAUNCHER = """#!/bin/sh
# ForeverWowCraft Helper: the Python inside this application, on the helper's fwch.py app.
here="$(cd "$(dirname "$0")/.." && pwd)"
exec "$here/Resources/python/{exe}" "$here/Resources/helper/fwch.py" app
"""


def info_plist(ver: str) -> dict:
    """What the bundle says of itself. LSUIElement: an agent, no Dock icon. NSHighResolutionCapable:
    drawn sharp on a Retina screen."""
    return {"CFBundleName": NAME, "CFBundleDisplayName": NAME, "CFBundleIdentifier": BUNDLE_ID, "CFBundleExecutable": NAME,
            "CFBundlePackageType": "APPL", "CFBundleIconFile": "helper", "CFBundleShortVersionString": ver, "CFBundleVersion": ver,
            "CFBundleInfoDictionaryVersion": "6.0", "LSMinimumSystemVersion": "11.0", "LSUIElement": True,
            "NSHighResolutionCapable": True, "NSHumanReadableCopyright": "ForeverWowCraft: MIT licence. Python: PSF licence."}


def launcher() -> str:
    return LAUNCHER.format(exe=PYTHON_EXE)


def python_tree(cache: Path, into: Path) -> None:
    """The standalone Python, fetched and checked, unpacked under `into` without what the
    helper has no use for, and PyObjC installed into it."""
    data = embed.fetch(PYTHON_URL, PYTHON_SHA256, cache)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        members = []
        for m in tar.getmembers():
            rel = m.name.split("/", 1)[1] if "/" in m.name else ""           # the archive's one folder, python/
            if not rel or rel.startswith(PYTHON_LEAVE_OUT) or rel.rstrip("/") in PYTHON_LEAVE_OUT:
                continue
            m.name = rel
            members.append(m)
        tar.extractall(into, members=members, filter="data")
    python = into / PYTHON_EXE
    python.chmod(python.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    env = dict(os.environ, PIP_DISABLE_PIP_VERSION_CHECK="1", PYTHONDONTWRITEBYTECODE="1")
    run([str(python), "-m", "pip", "install", "--quiet", "--no-compile", "--no-warn-script-location", *PYOBJC], env=env)
    for p in list(into.rglob("__pycache__")):
        shutil.rmtree(p, ignore_errors=True)


def stage(where: Path, cache: Path, ver: str, python: bool = True) -> Path:
    """The application bundle laid out under `where`; returns its path."""
    app = where / APP
    if app.exists():
        shutil.rmtree(app)
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    resources = contents / "Resources"
    resources.mkdir()
    with open(contents / "Info.plist", "wb") as f:
        plistlib.dump(info_plist(ver), f)
    (contents / "PkgInfo").write_text("APPL????", encoding="ascii")
    exe = contents / "MacOS" / NAME
    exe.write_text(launcher(), encoding="utf-8", newline="\n")
    exe.chmod(0o755)
    shutil.copyfile(HERE / "helper.icns", resources / "helper.icns")       # the .ico as an .icns, made once with Pillow (installer/icons.py)
    helper = resources / "helper"
    for rel in build.helper_files():
        dst = helper / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(HELPER / rel, dst)
    if python:
        python_tree(cache, resources / "python")
    return app


def dmg(app: Path, out: Path, ver: str) -> Path:
    """The disk image: the application and a link to Applications, compressed."""
    work = out / "dmg-root"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    shutil.copytree(app, work / app.name, symlinks=True)
    (work / "Applications").symlink_to("/Applications")
    target = out / f"ForeverWowCraft-Helper-{ver}.dmg"
    target.unlink(missing_ok=True)
    run(["hdiutil", "create", "-volname", NAME, "-srcfolder", str(work), "-ov", "-format", "UDZO", "-quiet", str(target)])
    shutil.rmtree(work)
    return target


def run(cmd: list[str], env: dict | None = None) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    if r.returncode:
        raise SystemExit(f"{Path(cmd[0]).name} failed ({r.returncode})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    core = HELPER.parent if (HELPER.parent / "fwc.py").exists() else None
    ap.add_argument("--out", type=Path, default=(core or HELPER) / "dist", help="where the .dmg goes")
    ap.add_argument("--cache", type=Path, help="where Python is kept between builds (default: <out>/cache)")
    ap.add_argument("--stage-only", action="store_true", help="lay the application out; make no disk image")
    ap.add_argument("--no-python", action="store_true", help="lay it out without Python (a test of the layout)")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    ver = build.version()
    app = stage(a.out / "mac", a.cache or a.out / "cache", ver, python=not a.no_python)
    print(f"staged {app}")
    if a.stage_only or a.no_python:
        return 0
    if sys.platform != "darwin":
        raise SystemExit("the disk image is made on a Mac (hdiutil)")
    image = dmg(app, a.out, ver)
    print(f"{image}  {image.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())

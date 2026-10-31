"""Python for a build that needs nothing installed: python.org's embeddable build (the
interpreter and the standard library, no installer, PSF licence; its LICENSE.txt rides along).
The helper is standard library only, so it is all the helper needs. The archive is checked
against its hash before anything of it is used, and kept in a cache folder for the next build.
Used by the installer (build.py) and by the core's tools/make_dist.py for the zip."""
from __future__ import annotations
import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

PYTHON_VERSION = "3.12.10"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
PYTHON_SHA256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
# the interpreter's path file: the embeddable build imports only from its own folder, and
# the helper's package is one up
PYTHON_PTH = "python312.zip\n.\n..\n"


def fetch(url: str, sha256: str, cache: Path, limit: int = 64 * 1024 * 1024) -> bytes:
    """A file by its address, downloaded once into `cache` and checked against its hash."""
    path = cache / url.rsplit("/", 1)[1]
    if not path.exists():
        print(f"downloading {url} ...", file=sys.stderr)
        req = urllib.request.Request(url, headers={"User-Agent": "ForeverWowCraft-build"})
        with urllib.request.urlopen(req, timeout=300) as r:
            data = r.read(limit)
        cache.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != sha256:
        path.unlink()
        raise SystemExit(f"{path.name}: sha256 {digest}, expected {sha256}: not used (downloaded again next time)")
    return data


def python_embed(cache: Path) -> bytes:
    return fetch(PYTHON_URL, PYTHON_SHA256, cache)


def python_files(cache: Path):
    """(name, bytes) of Python's files, flat, the path file ours."""
    with zipfile.ZipFile(io.BytesIO(python_embed(cache))) as src:
        for info in src.infolist():
            if info.is_dir() or "/" in info.filename or "\\" in info.filename:
                continue                                   # the archive is flat; anything else is not expected
            yield info.filename, (PYTHON_PTH.encode("ascii") if info.filename.endswith("._pth") else src.read(info))

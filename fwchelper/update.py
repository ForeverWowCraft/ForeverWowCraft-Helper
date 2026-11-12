"""Whether a newer helper is out, and getting it.

The newest release's address (settings.UPDATE_CHECK_URL, GitHub's .../releases/latest) answers
with a redirect to the release's tag, v1.5.5: that is the version, asked for with one request a
day and no API or key. The installer of the newest release has a fixed name (settings.UPDATE_URL);
it is downloaded into the state folder and opened as Windows opens an .msi: the installer closes
the running helper, puts the new one over it, and starts it again at the end (installer/helper.wxs).
A download by the helper carries no mark of the web, so SmartScreen has nothing to say; the
installer is still unsigned (docs/signing.md in the core), so the first bytes are checked to be
an installer's before it is opened, and before one is installed by itself (fwchelper/app.py,
since 1.6.0) its SHA-256 is checked against the one GitHub publishes for the release's asset
(settings.UPDATE_API, `digest`): a download that does not match is not installed. On the Mac the newest release is a disk image, .dmg
(installer/build_mac.py), checked by the trailer every disk image ends with; opened, it shows
the new helper to drag over the one in Applications."""
from __future__ import annotations
import hashlib
import json
import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__, settings

MSI_MAGIC = b"\xd0\xcf\x11\xe0"           # an .msi is an OLE compound file
DMG_TRAILER = b"koly"                        # a .dmg ends with a 512-byte trailer that starts so


class UpdateError(Exception):
    """A newer helper could not be had: the download failed, or what came is not an installer."""
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _headers() -> dict:
    return {"User-Agent": f"{settings.NAME}-helper/{__version__}"}


def version_tuple(version: str) -> tuple:
    """'1.5.4' -> (1, 5, 4); what is not a number is left out."""
    return tuple(int(x) for x in re.findall(r"\d+", version)[:4]) or (0,)


def newer(a: str, b: str) -> bool:
    """Whether version a is newer than version b."""
    return version_tuple(a) > version_tuple(b)


def latest(url: str | None = None, timeout: float | None = None) -> str | None:
    """The newest release's version, from where its address redirects to: '/releases/tag/v1.5.5'
    is 1.5.5. None when that cannot be told (no connection, no redirect, no tag in it)."""
    url = url or settings.env("UPDATE_URL") or settings.UPDATE_CHECK_URL
    req = urllib.request.Request(url, method="HEAD", headers=_headers())
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout or settings.PIPE_TIMEOUT) as r:
            location = r.headers.get("Location") or ""
    except urllib.error.HTTPError as e:
        if e.code not in (301, 302, 303, 307, 308):
            return None
        location = (e.headers.get("Location") if e.headers else None) or ""
    except (urllib.error.URLError, OSError, ValueError):
        return None
    found = re.search(r"/tag/v?(\d+(?:\.\d+)+)", location)
    return found.group(1) if found else None


def check() -> str | None:
    """The newer helper's version when one is out, else None."""
    found = latest()
    return found if found and newer(found, __version__) else None


def digest(version: str, url: str | None = None, timeout: float | None = None, file: str | None = None) -> str | None:
    """The SHA-256 GitHub publishes for the newest release's installer (settings.UPDATE_FILE:
    the platform's, or `file`), as hex. None when the release's page cannot be read, is not
    this version's, or publishes none: then nothing is installed by itself."""
    file = file or settings.UPDATE_FILE
    url = url or settings.env("UPDATE_API") or settings.UPDATE_API
    req = urllib.request.Request(url, headers=dict(_headers(), Accept="application/vnd.github+json"))
    try:
        with urllib.request.urlopen(req, timeout=timeout or settings.PIPE_TIMEOUT) as r:
            doc = json.loads(r.read(4_000_000).decode("utf-8", errors="replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not isinstance(doc, dict) or version_tuple(str(doc.get("tag_name") or "")) != version_tuple(version):
        return None
    for asset in doc.get("assets") or []:
        if isinstance(asset, dict) and asset.get("name") == file:
            said = str(asset.get("digest") or "")
            if said.startswith("sha256:") and re.fullmatch(r"[0-9a-f]{64}", said[7:]):
                return said[7:]
    return None


def sha256(path: Path) -> str:
    """The file's SHA-256 in hex, read a megabyte at a time."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verified(path: Path, expected: str) -> bool:
    """Whether the file's SHA-256 is `expected` (hex, any case)."""
    try:
        return sha256(path) == expected.lower()
    except OSError:
        return False


def is_installer(path: Path, kind: str) -> bool:
    """Whether the file is what an .msi starts with, or what a .dmg ends with."""
    try:
        with open(path, "rb") as f:
            if kind == "dmg":
                f.seek(0, 2)
                size = f.tell()
                if size < 512:
                    return False
                f.seek(size - 512)
                return f.read(4) == DMG_TRAILER
            return f.read(4) == MSI_MAGIC
    except OSError:
        return False


def download(version: str, url: str | None = None, into: Path | None = None, timeout: float | None = None) -> Path:
    """The newest release's installer, into the state folder (or `into`), named by the version:
    the platform's kind (settings.UPDATE_KIND), or the kind the address given names. Raises
    UpdateError when it cannot be had or is not an installer."""
    into = into or settings.STATE / "updates"
    into.mkdir(parents=True, exist_ok=True)
    kind = (url or "").rsplit(".", 1)[-1] if (url or "").endswith((".msi", ".dmg")) else settings.UPDATE_KIND
    target = into / f"{settings.NAME}-Helper-{version}.{kind}"
    part = target.with_suffix(".part")
    req = urllib.request.Request(url or settings.UPDATE_URL, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout or settings.PIPE_TIMEOUT) as r, open(part, "wb") as f:
            shutil.copyfileobj(r, f)
    except (urllib.error.URLError, OSError) as e:
        part.unlink(missing_ok=True)
        raise UpdateError(f"could not download the installer: {e}") from e
    if not is_installer(part, kind):
        part.unlink(missing_ok=True)
        raise UpdateError("what was downloaded is not an installer")
    part.replace(target)
    return target

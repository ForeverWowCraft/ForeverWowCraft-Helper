"""Whether a newer helper is out, and getting it.

The newest release's address (settings.UPDATE_CHECK_URL, GitHub's .../releases/latest) answers
with a redirect to the release's tag, v1.5.5: that is the version, asked for with one request a
day and no API or key. The installer of the newest release has a fixed name (settings.UPDATE_URL);
it is downloaded into the state folder and opened as Windows opens an .msi: the installer closes
the running helper, puts the new one over it, and starts it again at the end (installer/helper.wxs).
A download by the helper carries no mark of the web, so SmartScreen has nothing to say; the
installer is still unsigned (docs/signing.md in the core), so the first bytes are checked to be
an installer's before it is opened."""
from __future__ import annotations
import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__, settings

MSI_MAGIC = b"\xd0\xcf\x11\xe0"           # an .msi is an OLE compound file


class UpdateError(Exception):
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


def download(version: str, url: str | None = None, into: Path | None = None, timeout: float | None = None) -> Path:
    """The newest release's installer, into the state folder (or `into`), named by the version.
    Raises UpdateError when it cannot be had or is not an installer."""
    into = into or settings.STATE / "updates"
    into.mkdir(parents=True, exist_ok=True)
    target = into / f"{settings.NAME}-Helper-{version}.msi"
    part = target.with_suffix(".part")
    req = urllib.request.Request(url or settings.UPDATE_URL, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout or settings.PIPE_TIMEOUT) as r, open(part, "wb") as f:
            shutil.copyfileobj(r, f)
    except (urllib.error.URLError, OSError) as e:
        part.unlink(missing_ok=True)
        raise UpdateError(f"could not download the installer: {e}") from e
    with open(part, "rb") as f:
        head = f.read(4)
    if head != MSI_MAGIC:
        part.unlink(missing_ok=True)
        raise UpdateError("what was downloaded is not an installer")
    part.replace(target)
    return target

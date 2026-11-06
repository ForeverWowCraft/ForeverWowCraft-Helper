"""A newer helper: told from where the newest release's address redirects, and its installer downloaded."""
import http.server
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fwchelper import __version__, update  # noqa: E402


class _Releases(http.server.BaseHTTPRequestHandler):
    """A GitHub of sorts: /releases/latest redirects to the newest tag; /nowhere does not; the installer, and a page that is not one."""

    def _answer(self, head=False):
        if self.path == "/releases/latest":
            self.send_response(302)
            self.send_header("Location", "https://github.com/ForeverWowCraft/ForeverWowCraft-Helper/releases/tag/v9.9.9")
            self.end_headers()
        elif self.path == "/nowhere":
            self.send_response(200)
            self.end_headers()
        elif self.path == "/ForeverWowCraft-Helper.msi":
            body = update.MSI_MAGIC + b"\0" * 500
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head:
                self.wfile.write(body)
        elif self.path in ("/releases/api", "/releases/api-old", "/releases/api-none"):
            import hashlib
            import json
            tag = "v1.0.0" if self.path.endswith("-old") else "v9.9.9"
            assets = [] if self.path.endswith("-none") else [{"name": "other.zip", "digest": "sha256:" + "0" * 64},
                                                                {"name": "ForeverWowCraft-Helper.msi", "digest": "sha256:" + hashlib.sha256(update.MSI_MAGIC + b"\0" * 500).hexdigest()}]
            body = json.dumps({"tag_name": tag, "assets": assets}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head:
                self.wfile.write(body)
        elif self.path == "/page.msi":
            body = b"<html>not an installer</html>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head:
                self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_HEAD(self):
        self._answer(head=True)

    def do_GET(self):
        self._answer()

    def log_message(self, *a):
        pass


def _server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Releases)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_versions_compare_as_numbers():
    assert update.version_tuple("1.5.4") == (1, 5, 4) and update.version_tuple("v1.10.0") == (1, 10, 0) and update.version_tuple("x") == (0,)
    assert update.newer("1.10.0", "1.9.9") and update.newer("1.5.5", "1.5.4") and not update.newer("1.5.4", "1.5.4") and not update.newer("1.5.3", "1.5.4")


def test_the_newest_version_is_where_the_latest_release_redirects_to():
    srv, url = _server()
    try:
        assert update.latest(url + "/releases/latest", timeout=5) == "9.9.9"
        assert update.latest(url + "/nowhere", timeout=5) is None                      # no redirect: cannot tell
        assert update.latest(url + "/missing", timeout=5) is None
        assert update.latest("http://127.0.0.1:9/releases/latest", timeout=1) is None    # nothing listening: cannot tell, quietly
        os.environ["FWC_UPDATE_URL"] = url + "/releases/latest"
        try:
            assert update.check() == "9.9.9" and update.newer("9.9.9", __version__)
        finally:
            del os.environ["FWC_UPDATE_URL"]
    finally:
        srv.shutdown()


def test_the_installer_is_downloaded_and_checked_to_be_one():
    srv, url = _server()
    into = Path(tempfile.mkdtemp())
    try:
        path = update.download("9.9.9", url + "/ForeverWowCraft-Helper.msi", into, timeout=5)
        assert path == into / "ForeverWowCraft-Helper-9.9.9.msi" and path.read_bytes()[:4] == update.MSI_MAGIC and path.stat().st_size == 504
        for bad in ("/page.msi", "/missing"):
            try:
                update.download("9.9.9", url + bad, into, timeout=5)
                assert False, bad
            except update.UpdateError:
                pass
        assert sorted(p.name for p in into.iterdir()) == ["ForeverWowCraft-Helper-9.9.9.msi"]     # nothing half-downloaded left behind
    finally:
        srv.shutdown()


def test_the_digest_github_publishes_is_read_and_the_download_checked_against_it():
    srv, url = _server()
    into = Path(tempfile.mkdtemp())
    try:
        expected = update.digest("9.9.9", url + "/releases/api", timeout=5, file="ForeverWowCraft-Helper.msi")   # the test release is Windows' (on a Mac the platform's file is the .dmg)
        assert expected and len(expected) == 64
        assert update.digest("9.9.9", url + "/releases/api-old", timeout=5) is None          # another version's page
        assert update.digest("9.9.9", url + "/releases/api-none", timeout=5) is None         # no installer among the assets
        assert update.digest("9.9.9", url + "/nowhere", timeout=5) is None                   # not JSON
        assert update.digest("9.9.9", "http://127.0.0.1:9/", timeout=1) is None               # nothing listening
        path = update.download("9.9.9", url + "/ForeverWowCraft-Helper.msi", into, timeout=5)
        assert update.verified(path, expected) and update.verified(path, expected.upper()) and not update.verified(path, "0" * 64)
        assert not update.verified(into / "missing.msi", expected)
    finally:
        srv.shutdown()


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)

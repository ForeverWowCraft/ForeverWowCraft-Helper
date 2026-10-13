"""A helper that was given nothing registers itself, and keeps what it was given."""
import http.server
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fwchelper import cli, fresh, luatable, pipe, settings  # noqa: E402
from fwchelper.scan import ScanData, ScanItem  # noqa: E402


class Service(http.server.BaseHTTPRequestHandler):
    """As much of the pipe as a helper talks to."""
    tokens: dict = {}          # token -> name
    seen: list = []            # (method, path, name)
    too_soon = False
    registering = True
    newest = 1789999500        # the newest scan of Stonespine (Horde) the pipe holds
    fresh_for = 0              # seconds a scan stays fresh for the 409: 0 takes every scan

    def log_message(self, *a):
        pass

    def answer(self, status, body, headers=()):
        data = json.dumps(body).encode()
        self.send_response(status)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_any(self):
        cls = type(self)
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        token = (self.headers.get("Authorization") or "").replace("Bearer ", "")
        name = cls.tokens.get(token)
        cls.seen.append((self.command, self.path, name))
        if self.path == "/v1/fresh":
            return self.answer(200, {"generated": 1790000500, "fresh": 600, "houses": {"Stonespine|Horde": {"newest": cls.newest}}})
        if self.path == "/v1/register":
            if not cls.registering:
                return self.answer(429, {"error": "too many registrations from here today"}, [("Retry-After", "3600")])
            n = len(cls.tokens) + 1
            cls.tokens[f"token-{n}"] = f"h-{n}"
            return self.answer(201, {"name": f"h-{n}", "token": f"token-{n}", "trust": "public"})
        if name is None:
            return self.answer(401, {"error": "a token is needed"})
        if self.path == "/v1/me":
            return self.answer(200, {"name": name, "trust": "public"})
        if self.path == "/v1/scans" and cls.too_soon:
            return self.answer(429, {"error": "one scan of an auction house every 300 seconds; the next in 240"}, [("Retry-After", "240")])
        if self.path == "/v1/scans" and cls.fresh_for:
            return self.answer(409, {"error": "not needed: the auction house was scanned 100 s before this one", "fresh": True,
                                     "newest": cls.newest, "wanted_from": cls.newest + cls.fresh_for}, [("Retry-After", "500")])
        if self.path == "/v1/scans":
            return self.answer(201, {"id": 7, "new": True, "trust": "public"})
        return self.answer(404, {"error": "not found"})

    do_GET = do_POST = do_PUT = handle_any


def _service():
    Service.tokens, Service.seen, Service.too_soon, Service.registering = {}, [], False, True
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Service)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _fresh_pc():
    """Nothing saved, nothing sent before. Returns what to call to put things back."""
    kept = (settings.saved, settings.STATE, {k: os.environ.pop(k) for k in list(os.environ) if k.startswith(("FWC_", "FC_"))})
    settings.saved = lambda name: os.environ.get("FWC_" + name)
    settings.STATE = Path(tempfile.mkdtemp())

    def back():
        settings.saved, settings.STATE = kept[0], kept[1]
        os.environ.update(kept[2])
    return back


def test_it_registers_once_and_keeps_its_name():
    srv, url = _service()
    back = _fresh_pc()
    try:
        p = pipe.Pipe(url)
        assert p.token is None and p.registers                       # nothing yet, and nothing asked of anyone
        assert p.me() == {"name": "h-1", "trust": "public"} and (p.name, p.token) == ("h-1", "token-1")
        assert [s[:2] for s in Service.seen] == [("POST", "/v1/register"), ("GET", "/v1/me")]
        kept = json.loads((settings.STATE / "identity.json").read_text(encoding="utf-8"))
        assert kept[url]["name"] == "h-1" and kept[url]["token"] == "token-1"
        again = pipe.Pipe(url)                                       # the next run
        assert (again.name, again.token) == ("h-1", "token-1") and again.me()["name"] == "h-1"
        assert sum(1 for s in Service.seen if s[1] == "/v1/register") == 1
        assert pipe.Pipe(url + "/other").token is None               # a token is for the pipe that gave it
    finally:
        back()
        srv.shutdown()


def test_a_token_given_by_hand_is_used_as_it_is():
    srv, url = _service()
    back = _fresh_pc()
    try:
        Service.tokens["by-hand"] = "scanner-1"
        os.environ["FWC_PIPE_TOKEN"] = "by-hand"
        p = pipe.Pipe(url)
        assert not p.registers and p.me()["name"] == "scanner-1"
        os.environ["FWC_PIPE_TOKEN"] = "mistyped"
        try:
            pipe.Pipe(url).me()
            raise AssertionError("a wrong token was taken")
        except pipe.PipeError as e:
            assert "401" in str(e)
        assert not any(s[1] == "/v1/register" for s in Service.seen)          # it does not quietly become someone else
        assert not (settings.STATE / "identity.json").exists()
    finally:
        back()
        srv.shutdown()


def test_a_token_the_service_forgot_is_replaced():
    srv, url = _service()
    back = _fresh_pc()
    try:
        assert pipe.Pipe(url).me()["name"] == "h-1"
        Service.tokens.clear()                                        # the service was set up anew
        assert pipe.Pipe(url).me()["name"] == "h-1" and Service.tokens == {"token-1": "h-1"}
        assert [s[1] for s in Service.seen].count("/v1/register") == 2
    finally:
        back()
        srv.shutdown()


def test_sent_too_soon_is_said_and_tried_again_later():
    srv, url = _service()
    back = _fresh_pc()
    try:
        os.environ["FWC_PIPE_URL"] = url
        folder = Path(tempfile.mkdtemp())
        sd = ScanData({4358: ScanItem(4358, "Rough Dynamite", [(79, 20)], True, 1790000000, {"full": True})}, "Stonespine", folder / "s.json",
                      faction="Horde")
        (folder / "s.json").write_bytes(pipe.pack(pipe.scan_document(sd)))
        p = pipe.Pipe()
        Service.too_soon = True
        try:
            p.send_scan(pipe.scan_document(sd))
            raise AssertionError("taken")
        except pipe.TooSoon as e:
            assert e.wait == 240 and "every 300 seconds" in str(e)
        assert cli.send_once(p, folder / "s.json") is False
        assert not (settings.STATE / "sent.json").exists()            # not noted as sent: the next look sends it
        Service.too_soon = False
        assert cli.send_once(p, folder / "s.json") is True and cli.send_once(p, folder / "s.json") is False
    finally:
        back()
        srv.shutdown()


def test_a_scan_the_pipe_does_not_need_is_not_sent_and_not_tried_again():
    srv, url = _service()
    back = _fresh_pc()
    try:
        os.environ["FWC_PIPE_URL"] = url
        os.environ["FWC_WOW_DIR"] = tempfile.mkdtemp()                       # no game here: Fresh.lua goes to the kept copy only
        folder = Path(tempfile.mkdtemp())
        sd = ScanData({4358: ScanItem(4358, "Rough Dynamite", [(79, 20)], True, 1790000000, {"full": True})}, "Stonespine", folder / "s.json",
                      faction="Horde")
        (folder / "s.json").write_bytes(pipe.pack(pipe.scan_document(sd)))
        p = pipe.Pipe()
        # the pipe says not needed: nothing is kept there, and the helper notes the scan as dealt with
        Service.fresh_for = 600
        try:
            p.send_scan(pipe.scan_document(sd))
            raise AssertionError("taken")
        except pipe.NotNeeded as e:
            assert e.newest == 1789999500 and e.wanted_from == 1790000100 and "not needed" in str(e)
        assert cli.send_once(p, folder / "s.json") is False
        assert (settings.STATE / "sent.json").exists() and cli.send_once(p, folder / "s.json") is False
        assert [s for s in Service.seen if s[1] == "/v1/scans"] and len([s for s in Service.seen if s[1] == "/v1/scans"]) == 2
        # what the pipe said lately spares the upload: a scan under `fresh` newer than the newest known is not sent at all
        Service.fresh_for = 0
        told = p.fresh()
        assert told["houses"]["Stonespine|Horde"]["newest"] == 1789999500
        assert fresh.not_needed(told, "Stonespine", "Horde", 1790000000) == 1789999500 and fresh.not_needed(told, "Stonespine", "Horde", 1790001000) is None
        assert fresh.not_needed(told, "Elsewhere", "Horde", 1790000000) is None and fresh.not_needed(None, "Stonespine", "Horde", 0) is None
        before = len(Service.seen)
        assert cli.send_once(p, folder / "s.json", again=True, fresh=told) is True             # --again sends regardless
        (folder / "s.json").write_bytes(pipe.pack(pipe.scan_document(ScanData(sd.items, "Stonespine", folder / "s.json", faction="Horde"))))
        assert cli.send_once(p, folder / "s.json", fresh=told) is False                        # already sent, by the mark
        assert len([s for s in Service.seen[before:] if s[1] == "/v1/scans"]) == 1
        # Fresh.lua for the addon: by realm, then faction, the newest scan
        text = fresh.fresh_text(told)
        assert '["Stonespine"]' in text and '["Horde"]' in text
        parsed = luatable.parse(text)["FWCS_FRESH"]
        assert parsed["fresh"] == 600 and parsed["houses"]["Stonespine"]["Horde"] == {"newest": 1789999500}
        written = fresh.write(told)
        assert written == [settings.STATE / "Fresh.lua"] and luatable.parse(written[0].read_text(encoding="utf-8"))["FWCS_FRESH"]["written"] > 0
        assert cli.freshen(p, quiet=True) == told
    finally:
        Service.fresh_for = 0
        back()
        srv.shutdown()


def test_when_nobody_is_registered():
    srv, url = _service()
    back = _fresh_pc()
    try:
        Service.registering = False
        try:
            pipe.Pipe(url).me()
            raise AssertionError("registered")
        except pipe.TooSoon as e:
            assert e.wait == 3600
        assert not (settings.STATE / "identity.json").exists()
    finally:
        back()
        srv.shutdown()


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)

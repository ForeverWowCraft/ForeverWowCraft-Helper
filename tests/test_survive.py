"""A document the site or the pipe should never serve does not stop the helper's work thread: the
watch goes on, the update check (the app's tick) is still reached at every round, and the routes the
addon has are not lost. Each bad document here was one that ended the watch before 1.8.0."""
import contextlib
import http.server
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fwchelper import cli, fresh, luatable, pipe, plans, settings, tray  # noqa: E402
from test_plans import _site, document  # noqa: E402
from test_register import Service, _fresh_pc, _service  # noqa: E402

DEEP = "[" * 100000 + "]" * 100000


def test_an_id_is_ascii_digits_and_a_string_has_no_lone_surrogate():
    doc = document()
    doc["items"]["²"] = "two"                                     # "²": str.isdigit says yes, int() says no
    assert plans.check_plans(doc) == "items is not {item id: name}"
    doc = document()
    doc["items"]["1" * 5000] = "long"                                  # more digits than int() reads by default
    assert plans.check_plans(doc) == "items is not {item id: name}"
    assert plans.lua({"²": 1, "12": 2}) == '{\n ["²"]=1,\n [12]=2,\n}'
    text = plans.lua({"a": "Linen\ud800 Cloth"})
    assert text == '{\n ["a"]="Linen Cloth",\n}' and text.encode("utf-8")


def test_json_nested_too_deep_is_the_modules_own_error():
    # how deep Python's json follows differs between versions (3.14 on the Mac reads all of DEEP): where it gives up
    # it raises RecursionError, stood in for here so that every Python takes the same path
    def too_deep(*a, **k):
        raise RecursionError("maximum recursion depth exceeded while decoding a JSON array")
    kept = json.loads
    json.loads = too_deep
    site, srv, root = _site({}, [])
    try:
        for data in (DEEP.encode(), __import__("gzip").compress(DEEP.encode())):
            try:
                pipe.unpack(data)
                raise AssertionError("no error")
            except pipe.PipeError as e:
                assert "nested too deep" in str(e)
        (root / "data" / "deep.json").write_text(DEEP, encoding="utf-8")
        try:
            plans.get(site + "/data/deep.json")
            raise AssertionError("no error")
        except plans.PlansError as e:
            assert "not JSON" in str(e) and e.kind == "reach"
    finally:
        json.loads = kept
        srv.shutdown()
        srv.server_close()
    # and as this Python has it: read, or the module's own error, never a RecursionError
    try:
        assert isinstance(pipe.unpack(DEEP.encode()), list)
    except pipe.PipeError:
        pass


def test_the_freshness_with_a_time_that_is_no_number_is_left_out():
    told = {"fresh": "soon", "houses": {"Stonespine|Horde": {"newest": "x"}, "Other|Alliance": {"newest": 1789999000}, "Odd|Horde": ["x"]}}
    assert fresh.for_addon(told)["houses"] == {"Other": {"Alliance": {"newest": 1789999000}}}
    assert fresh.for_addon(told)["fresh"] == 600
    assert fresh.not_needed(told, "Stonespine", "Horde", 1790000000) is None
    assert fresh.not_needed(told, "Odd", "Horde", 1790000000) is None
    assert fresh.not_needed(told, "Other", "Alliance", 1789999100) == 1789999000
    assert "FWCS_FRESH" in fresh.fresh_text(told)


class BadFresh(Service):
    """The test pipe, with a /v1/fresh whose times are not numbers."""

    def handle_any(self):
        if self.path == "/v1/fresh":
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            return self.answer(200, {"generated": "x", "fresh": 600, "houses": {"Stonespine|Horde": {"newest": "x"}}})
        return Service.handle_any(self)

    do_GET = do_POST = do_PUT = handle_any


def _bad_fresh():
    Service.tokens, Service.seen, Service.too_soon, Service.registering = {}, [], False, True
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), BadFresh)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _watch_a_while(seconds: float = 1.5) -> tuple[int, bool, str]:
    """Run the watch on its own thread for a while, as the app does: (rounds whose tick, where the app looks for
    an update, was reached; whether the watch was still running when told to stop; what it printed)."""
    ticks = []
    stop, wake = threading.Event(), threading.Event()
    log = settings.STATE / "watch.log"
    out, kept_out = tray.Log(log), sys.stdout
    sys.stdout = out
    try:
        t = threading.Thread(target=lambda: cli.watch(pipe.Pipe(), None, None, None, interval=0.05, stop=stop, wake=wake,
                                                      asks={}, tick=lambda: ticks.append(1)), daemon=True)
        t.start()
        time.sleep(seconds)
        running = t.is_alive()
        stop.set()
        wake.set()
        t.join(10)
    finally:
        sys.stdout = kept_out
    return len(ticks), running, log.read_text(encoding="utf-8") if log.exists() else ""


def _scenario(doc_text: str | None, listed: list, pipe_service=_service):
    """A pipe, a site serving `listed` (houses.json) and `doc_text` as the house's ingame.json, a game folder and a
    Plans.lua kept from before (the routes of old--horde). Returns (ticks, running, log, the kept Plans.lua's text)."""
    srv, url = pipe_service()
    back = _fresh_pc()
    site, site_srv, root = _site({}, listed)
    if doc_text is not None:
        (root / "data" / "stonespine--horde").mkdir()
        (root / "data" / "stonespine--horde" / "ingame.json").write_text(doc_text, encoding="utf-8")
    game = Path(tempfile.mkdtemp()) / "World of Warcraft"
    (game / "_forever_" / "Interface" / "AddOns").mkdir(parents=True)
    os.environ["FWC_PIPE_URL"], os.environ["FWC_SITE_URL"], os.environ["FWC_WOW_DIR"] = url, site, str(game)
    try:
        settings.STATE.mkdir(parents=True, exist_ok=True)
        plans.kept_file().write_text(plans.plans_text([document(house="old--horde", generated=5)], site), encoding="utf-8")
        ticks, running, log = _watch_a_while()
        return ticks, running, log, plans.kept_file().read_text(encoding="utf-8")
    finally:
        back()
        srv.shutdown()
        site_srv.shutdown()
        site_srv.server_close()


def _house(**kw) -> dict:
    return dict({"key": "stonespine--horde", "realm": "Stonespine", "faction": "Horde", "realms": ["Stonespine"],
                 "generated": int(time.time()), "ingame": True}, **kw)


def _ok(ticks, running, log):
    assert running, log                                    # the watch did not end
    assert ticks >= 3, (ticks, log)                        # rounds after the bad one: the update check is still reached


def test_the_watch_goes_on_after_bad_documents():
    doc = document()
    doc["items"]["²"] = "two"
    ticks, running, log, kept = _scenario(json.dumps(doc), [_house()])
    _ok(ticks, running, log)
    assert "routes not fetched:" in log and "items is not" in log
    assert set(luatable.parse(kept)["FWCS_PLANS"]) == {"old--horde"}             # the routes the addon had stay
    # a lone surrogate in a name: written without it, the file whole
    doc = document()
    doc["items"]["2589"] = "Linen\ud800 Cloth"
    ticks, running, log, kept = _scenario(json.dumps(doc), [_house()])
    _ok(ticks, running, log)
    assert luatable.parse(kept)["FWCS_PLANS"]["stonespine--horde"]["items"][2589] == "Linen Cloth"
    # JSON nested deeper than Python follows
    ticks, running, log, kept = _scenario(DEEP, [_house()])
    _ok(ticks, running, log)
    assert "routes not fetched:" in log and set(luatable.parse(kept)["FWCS_PLANS"]) == {"old--horde"}
    # houses.json with a time that is a string: the house is fetched as one never seen
    ticks, running, log, kept = _scenario(json.dumps(document()), [_house(generated="x")])
    _ok(ticks, running, log)
    assert "stonespine--horde" in luatable.parse(kept)["FWCS_PLANS"]
    # a faction that is a list: that house is no house
    ticks, running, log, kept = _scenario(json.dumps(document()), [_house(faction=["Horde"])])
    _ok(ticks, running, log)
    assert "failed:" not in log and "FWCS_PLANS_WRITTEN" in kept
    # the pipe's freshness with a time that is not a number
    ticks, running, log, kept = _scenario(json.dumps(document()), [_house()], pipe_service=_bad_fresh)
    _ok(ticks, running, log)
    assert "failed:" not in log


def test_any_error_in_a_step_is_said_and_the_watch_goes_on():
    def boom(*a, **k):
        raise RuntimeError("nobody foresaw this")
    kept = plans.refresh, fresh.write, cli.send_vendors_once
    plans.refresh, fresh.write, cli.send_vendors_once = boom, boom, boom
    try:
        ticks, running, log, _ = _scenario(json.dumps(document()), [_house()])
    finally:
        plans.refresh, fresh.write, cli.send_vendors_once = kept
    _ok(ticks, running, log)
    for what in ("routes", "freshness", "vendors"):
        assert f"{what} failed: RuntimeError: nobody foresaw this" in log, log
    assert "Traceback" in log


def test_the_first_run_goes_on_after_any_error_in_a_step():
    srv, url = _service()
    back = _fresh_pc()
    game = Path(tempfile.mkdtemp()) / "World of Warcraft"
    (game / "_forever_" / "Interface" / "AddOns").mkdir(parents=True)
    os.environ["FWC_PIPE_URL"], os.environ["FWC_WOW_DIR"], os.environ["FWC_SITE_URL"] = url, str(game), url

    def boom(*a, **k):
        raise RuntimeError("nobody foresaw this")
    kept = cli.lists, cli.plans, cli.freshen, cli.startup_dir
    cli.lists, cli.plans, cli.freshen = boom, boom, boom
    cli.startup_dir = lambda: Path(tempfile.mkdtemp())
    try:
        from test_app import FakeWin, _app
        app = _app(FakeWin())
        with contextlib.redirect_stdout(app.log):
            p = app.first_run()
        text = (settings.STATE / "helper.log").read_text(encoding="utf-8")
        assert p is not None and "This helper sends as h-1" in text
        for what in ("lists", "routes", "freshness"):
            assert f"{what} failed: RuntimeError: nobody foresaw this" in text
    finally:
        cli.lists, cli.plans, cli.freshen, cli.startup_dir = kept
        back()
        srv.shutdown()


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)

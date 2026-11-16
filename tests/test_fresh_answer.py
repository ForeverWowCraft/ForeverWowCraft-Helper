"""Since 1.8.4 the helper asks the pipe no freshness by itself (GET /v1/fresh was most of a helper's
requests to it): it learns when a house was last scanned from the pipe's answer to each scan it sends,
201 or 409, and keeps it in Fresh.lua beside the other houses it learned of. The start asks no name
(GET /v1/me) and no freshness, and the lists once a day at most. `python fwch.py fresh` still asks."""
import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fwchelper import cli, fresh, luatable, pipe, plans, settings  # noqa: E402
from fwchelper.scan import ScanData, ScanItem  # noqa: E402
from test_register import Service, _fresh_pc, _service  # noqa: E402


def _setup():
    """A test pipe and a PC with nothing saved, no game (Fresh.lua goes to the kept copy only). Returns (url, put back)."""
    srv, url = _service()
    back = _fresh_pc()
    os.environ["FWC_PIPE_URL"], os.environ["FWC_SITE_URL"] = url, url           # the test pipe serves no site: routes not fetched
    os.environ["FWC_WOW_DIR"] = tempfile.mkdtemp()
    kept = Service.newest, Service.fresh_for, settings.OLD_STATE
    settings.OLD_STATE = Path(tempfile.mkdtemp()) / "state"           # no older install's state to carry over

    def done():
        Service.newest, Service.fresh_for, Service.scan_reply, settings.OLD_STATE = kept[0], kept[1], None, kept[2]
        back()
        srv.shutdown()
    return url, done


def _asked() -> dict:
    """The requests made of the pipe so far, by path (the test pipe also stands in for a site that serves nothing)."""
    return {path: n for path, n in Service.counts.items() if path.startswith("/v1/")}


def _scan_file(scanned_at: int, realm: str = "Stonespine", faction: str = "Horde") -> Path:
    """A scan file of one house, its newest item read at `scanned_at`."""
    folder = Path(tempfile.mkdtemp())
    sd = ScanData({4358: ScanItem(4358, "Rough Dynamite", [(79, 20)], True, scanned_at, {"full": True})}, realm, folder / "s.json",
                  faction=faction)
    (folder / "s.json").write_bytes(pipe.pack(pipe.scan_document(sd)))
    return folder / "s.json"


def _held() -> dict:
    """Fresh.lua as the addon reads it, through the tests' Lua table reader."""
    return luatable.parse(fresh.kept_file().read_text(encoding="utf-8"))["FWCS_FRESH"]


def _watch(rounds: int, path: Path | None = None) -> tuple[bool, str]:
    """Run the watch on its own thread for `rounds` rounds, as the app does: (whether it was still running, what it printed)."""
    ticks, stop, wake, said = [], threading.Event(), threading.Event(), io.StringIO()

    def tick():
        ticks.append(1)
        if len(ticks) >= rounds:
            stop.set()
            wake.set()
    with contextlib.redirect_stdout(said):
        t = threading.Thread(target=lambda: cli.watch(pipe.Pipe(), path, None, None, interval=0.01, stop=stop, wake=wake, asks={}, tick=tick),
                             daemon=True)
        t.start()
        t.join(30)
    return len(ticks) >= rounds and not t.is_alive(), said.getvalue()


def test_the_watch_asks_no_freshness():
    url, done = _setup()
    kept = dict(plans.INTERVALS)
    try:
        plans.INTERVALS["fresh_every"] = 60          # even a site that says to look every minute: a 1.8.4 helper does not look
        finished, said = _watch(25)
        assert finished, said
        assert Service.counts["/v1/fresh"] == 0, Service.counts
        assert _asked() == {}, Service.counts                                                      # nothing to send: nothing asked of the pipe
    finally:
        plans.INTERVALS.clear()
        plans.INTERVALS.update(kept)
        done()


def test_a_taken_scan_is_the_houses_newest_and_other_houses_are_kept():
    url, done = _setup()
    try:
        now = int(time.time())
        fresh.write({"fresh": 900, "houses": {"Other|Alliance": {"newest": now - 100}, "Gone|Horde": {"newest": now - 100000}}})
        assert cli.send_once(pipe.Pipe(), _scan_file(now - 50)) is True
        assert Service.counts["/v1/scans"] == 1 and Service.counts["/v1/fresh"] == 0
        held = _held()
        assert held["houses"]["Stonespine"]["Horde"] == {"newest": now - 50}                      # the scan just taken
        assert held["houses"]["Other"]["Alliance"] == {"newest": now - 100}                       # another house, kept
        assert "Gone" not in held["houses"]                                                        # no longer fresh: dropped
        assert held["fresh"] == 900 and held["written"] >= now                                    # the last value known; written now
        # a scan stamped ahead of this computer's clock counts as now, as the pipe keeps it
        (settings.STATE / "sent.json").unlink()
        assert cli.send_once(pipe.Pipe(), _scan_file(now + 300, "Ahead", "Alliance")) is True
        assert _held()["houses"]["Ahead"]["Alliance"]["newest"] <= int(time.time())
    finally:
        done()


def test_a_scan_not_needed_notes_the_newest_the_pipe_holds():
    url, done = _setup()
    try:
        now = int(time.time())
        Service.newest, Service.fresh_for = now - 100, 1200
        fresh.write({"fresh": 600, "houses": {"Other|Alliance": {"newest": now - 30}}})
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            assert cli.send_once(pipe.Pipe(), _scan_file(now - 50)) is False
        assert "nothing sent, and nothing needs doing." in said.getvalue()
        assert (settings.STATE / "sent.json").exists()                                            # dealt with, as before
        held = _held()
        assert held["houses"]["Stonespine"]["Horde"] == {"newest": now - 100}                     # the 409's newest
        assert held["fresh"] == 1200                                                              # by its wanted_from
        assert held["houses"]["Other"]["Alliance"] == {"newest": now - 30}
    finally:
        done()


def test_a_house_fresh_by_what_was_learned_is_not_sent():
    url, done = _setup()
    try:
        now = int(time.time())
        assert fresh.learn("Stonespine", "Horde", now - 100) is not None
        path = _scan_file(now - 50)
        finished, said = _watch(10, path)
        assert finished, said
        assert Service.counts["/v1/scans"] == 0 and Service.counts["/v1/fresh"] == 0, Service.counts
        assert "not needed: Stonespine" in said and "nothing sent" in said, said
        assert json.loads((settings.STATE / "sent.json").read_text(encoding="utf-8"))                   # marked as dealt with
        # without what was learned, the scan is simply sent: the pipe decides
        (settings.STATE / "sent.json").unlink()
        fresh.kept_file().unlink()
        assert cli.send_once(pipe.Pipe(), path, fresh=fresh.known()) is True and Service.counts["/v1/scans"] == 1
    finally:
        done()


BAD_REPLIES = [
    (201, ["x"]), (201, "taken"), (201, {"id": 7, "new": "yes"}), (201, None),
    (409, {"fresh": True, "newest": "x", "wanted_from": 5}), (409, {"fresh": True, "newest": True}),
    (409, {"fresh": True, "newest": -5}), (409, {"fresh": True, "newest": 10 ** 12}), (409, {"fresh": True, "newest": 1.5e9}),
    (409, {"fresh": True, "newest": [1], "wanted_from": {"a": 1}}),
]


def test_an_answer_that_is_nonsense_writes_nothing_and_the_watch_goes_on():
    url, done = _setup()
    try:
        now = int(time.time())
        fresh.write({"fresh": 600, "houses": {"Other|Alliance": {"newest": now - 30}}})
        before = fresh.kept_file().read_text(encoding="utf-8")
        for reply in BAD_REPLIES:
            Service.scan_reply = reply
            sent = settings.STATE / "sent.json"
            sent.unlink(missing_ok=True)
            with contextlib.redirect_stdout(io.StringIO()):
                cli.send_once(pipe.Pipe(), _scan_file(now - 50))                                  # no error
            assert fresh.kept_file().read_text(encoding="utf-8") == before, reply
        # a 409 whose newest is a time but whose wanted_from is not: the newest, with the seconds last known
        Service.scan_reply = (409, {"fresh": True, "newest": now - 20, "wanted_from": "soon"})
        (settings.STATE / "sent.json").unlink()
        with contextlib.redirect_stdout(io.StringIO()):
            assert cli.send_once(pipe.Pipe(), _scan_file(now - 10)) is False
        assert _held()["houses"]["Stonespine"]["Horde"] == {"newest": now - 20} and _held()["fresh"] == 600
        # and the watch, sending into answers like these, goes on
        fresh.write({"fresh": 600, "houses": {}})
        for reply in BAD_REPLIES[:2] + BAD_REPLIES[4:6]:
            Service.scan_reply = reply
            (settings.STATE / "sent.json").unlink(missing_ok=True)
            finished, said = _watch(8, _scan_file(now - 5))
            assert finished, (reply, said)
            assert _held()["houses"] == {}, reply
    finally:
        done()


def test_the_start_asks_no_name_and_no_freshness_and_the_lists_once_a_day():
    url, done = _setup()
    game = Path(tempfile.mkdtemp()) / "World of Warcraft"
    (game / "_forever_" / "Interface" / "AddOns").mkdir(parents=True)
    os.environ["FWC_WOW_DIR"] = str(game)
    kept = cli.startup_dir
    cli.startup_dir = lambda: Path(tempfile.mkdtemp())
    try:
        from test_app import FakeWin, _app

        def start() -> str:
            app = _app(FakeWin())
            with contextlib.redirect_stdout(app.log):
                app.first_run()
            assert app.status.name == "h-1"
            return (settings.STATE / "helper.log").read_text(encoding="utf-8")
        text = start()
        assert _asked() == {"/v1/register": 1, "/v1/lists": 1}, Service.counts                     # until 1.8.4 also /v1/me and /v1/fresh twice
        assert "This helper sends as h-1." in text
        text = start()                                                                             # started again the same day
        assert _asked() == {"/v1/register": 1, "/v1/lists": 1}, Service.counts
        assert text.count("This helper sends as h-1.") == 2                                       # the name from identity.json
        (settings.STATE / "looked.json").write_text(json.dumps({"lists": time.time() - settings.LISTS_EVERY - 1}), encoding="utf-8")
        start()                                                                                    # a day on
        assert Service.counts["/v1/lists"] == 2 and Service.counts["/v1/me"] == 0 and Service.counts["/v1/fresh"] == 0
        (settings.STATE / "looked.json").write_text("not json", encoding="utf-8")
        start()                                                                                    # a note that cannot be read: asked
        assert Service.counts["/v1/lists"] == 3
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["lists"])                                                                    # by hand: at once
        assert Service.counts["/v1/lists"] == 4
    finally:
        cli.startup_dir = kept
        done()


def test_fwch_fresh_still_asks_the_pipe():
    url, done = _setup()
    try:
        now = int(time.time())
        Service.newest = now - 60
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            cli.main(["fresh"])
        assert Service.counts["/v1/fresh"] == 1
        assert _held()["houses"]["Stonespine"]["Horde"] == {"newest": now - 60} and "Stonespine" in said.getvalue()
        assert fresh.known()["houses"] == {"Stonespine|Horde": {"newest": now - 60}}
    finally:
        done()


def test_the_old_knob_is_still_read():
    assert plans.hints({"helper": {"plans_every": 600, "fresh_every": 7200}}) == {"plans_every": 600, "fresh_every": 7200}
    kept = dict(plans.INTERVALS)
    try:
        plans.INTERVALS.clear()
        assert plans.fresh_every() == settings.FRESH_EVERY == 1800
        plans.INTERVALS.update(plans.hints({"helper": {"fresh_every": 7200}}))
        assert plans.fresh_every() == 7200
    finally:
        plans.INTERVALS.clear()
        plans.INTERVALS.update(kept)


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)

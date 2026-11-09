import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fwchelper import pipe, scan  # noqa: E402
from fwchelper.scan import ScanData, ScanItem  # noqa: E402


def _scan():
    return ScanData({
        4358: ScanItem(4358, "Rough Dynamite", [(79, 20), (80, 5), (80, 5), (99, 1)], True, 1790000100, {"full": True}),
        2840: ScanItem(2840, "Copper Bar", [], True, 1790000100, {"full": True}),              # nothing listed: a fact too
        118: ScanItem(118, "Minor Healing Potion", [(40, 1)], True, 1790000900, {}),            # from a later per-item scan
        999: ScanItem(999, "Skipped", [], False, 1790000100, {"reason": "timeout"}),
    }, "Test Realm", Path("scan.lua"), history={4358: [(1789990000, 90, 40)]}, faction="Horde")


def test_a_scan_as_a_document():
    doc = pipe.scan_document(_scan())
    assert doc["format"] == "fwc-scan/1" and doc["realm"] == "Test Realm" and doc["scanned_at"] == 1790000900
    assert doc["faction"] == "Horde"
    assert set(doc["items"]) == {"118", "2840", "4358"}                  # the item the addon skipped is left out
    assert doc["items"]["4358"] == {"t": 1790000100, "name": "Rough Dynamite", "full": 1, "l": [[79, 20, 1], [80, 5, 2], [99, 1, 1]]}
    assert doc["items"]["2840"]["l"] == [] and "full" not in doc["items"]["118"]
    assert pipe.check_scan(doc) is None
    assert "history" not in json.dumps(doc)                              # one scan, not what came before it


def test_a_document_as_a_scan_again():
    sd = _scan()
    back = pipe.scan_from_document(pipe.unpack(pipe.pack(pipe.scan_document(sd))))
    assert (back.realm, back.faction, back.dataset) == ("Test Realm", "Horde", "Test Realm (Horde)") and set(back.items) == {118, 2840, 4358}
    older = dict(pipe.scan_document(sd))
    del older["faction"]                                                 # from a helper that did not say
    assert pipe.check_scan(older) is None and pipe.scan_from_document(older).dataset == "Test Realm"
    for iid, it in back.items.items():
        assert (it.listings, it.scanned_at, it.name, it.complete) == (sd.items[iid].listings, sd.items[iid].scanned_at, sd.items[iid].name, True)
    assert back.items[4358].extra == {"full": True} and back.items[118].extra == {} and back.newest == 1790000900


def test_a_stack_for_under_a_copper_a_unit_costs_a_copper_a_unit():
    # the addon (before 0.6.1) wrote a unit price of 0 for a stack of 20 at 10c; such a listing is
    # sent as a copper, and one that arrives as 0 (from an older helper) is read as a copper
    sd = _scan()
    sd.items[4358].listings = [(0, 20), (0, 20), (79, 20)]
    doc = pipe.scan_document(sd)
    assert doc["items"]["4358"]["l"] == [[1, 20, 2], [79, 20, 1]] and pipe.check_scan(doc) is None
    old = dict(doc, items=dict(doc["items"], **{"4358": {"t": 1790000100, "l": [[0, 20, 2], [79, 20, 1]]}}))
    assert pipe.check_scan(old) is None
    assert pipe.scan_from_document(old).items[4358].listings == [(1, 20), (1, 20), (79, 20)]
    for rung in ([-1, 20, 1], [0, 0, 1], [0, 20, 0]):
        assert "unit price" in pipe.check_scan(dict(doc, items={"4358": {"t": 1, "l": [rung]}})), rung


def test_the_time_an_auction_has_left_travels_with_it():
    sd = _scan()
    sd.items[4358].listings = [(79, 20), (79, 20), (80, 5), (99, 1)]
    sd.items[4358].left = [4, 1, 4, 0]                                   # two alike but for the time left; one the addon did not say
    doc = pipe.scan_document(sd)
    assert doc["items"]["4358"]["l"] == [[79, 20, 1, 1], [79, 20, 1, 4], [80, 5, 1, 4], [99, 1, 1]]
    assert doc["items"]["118"]["l"] == [[40, 1, 1]]                      # an item whose listings never said
    assert pipe.check_scan(doc) is None
    back = pipe.scan_from_document(pipe.unpack(pipe.pack(doc)))
    assert back.items[4358].listings == [(79, 20), (79, 20), (80, 5), (99, 1)] and back.items[4358].left == [1, 4, 4, 0]
    assert back.items[118].left == [] and back.items[118].bands == [0]
    for rung in ([79, 20, 1, 0], [79, 20, 1, 5], [79, 20, 1, 4, 4]):
        assert "time left" in pipe.check_scan(dict(doc, items={"4358": {"t": 1, "l": [rung]}})), rung


def test_packing_is_small_and_always_the_same():
    doc = pipe.scan_document(_scan())
    packed = pipe.pack(doc)
    assert packed[:2] == b"\x1f\x8b" and pipe.unpack(packed) == doc and pipe.unpack(json.dumps(doc).encode()) == doc
    assert pipe.pack(json.loads(json.dumps(doc))) == packed and len(pipe.digest(packed)) == 64


def test_what_is_not_a_document_is_refused():
    good = pipe.scan_document(_scan())
    for change, why in (({"format": "fwc-scan/9"}, "not a fwc-scan/1"), ({"realm": " "}, "no realm"), ({"items": {}}, "no items"),
                        ({"faction": "Sideways"}, "faction"), ({"faction": None}, "faction"),
                        ({"items": {"x": {"t": 1, "l": []}}}, "not an item"), ({"items": {"1": {"t": "now", "l": []}}}, "not an item"),
                        ({"items": {"1": {"t": 1, "l": [[79, 20]]}}}, "unit price"), ({"items": {"1": {"t": 1, "l": [[79, 0, 1]]}}}, "unit price")):
        assert why in pipe.check_scan(dict(good, **change)), change
    assert pipe.check_scan([]) and pipe.check_scan(None)
    try:
        pipe.scan_from_document({"format": "fwc-scan/1"})
        raise AssertionError("accepted")
    except pipe.PipeError:
        pass


def test_what_the_core_reads_of_a_scan_is_checked_and_bounded():
    # 9 Nov 2026: a scan without scanned_at stopped the core's pull; everything the core reads of
    # a scan is checked now, as the pipe checks it, and a rung is held to the game's bounds
    good = pipe.scan_document(_scan())
    rows = lambda *rungs: {"items": {"1": {"t": 1, "l": list(rungs)}}}   # noqa: E731
    for change, why in (({"scanned_at": None}, "scanned_at"), ({"scanned_at": "1790000900"}, "scanned_at"), ({"scanned_at": True}, "scanned_at"),
                        ({"scanned_at": -1}, "scanned_at"), ({"realm": "x" * 81}, "no realm"), ({"helper": 7}, "helper"),
                        ({"realm_names": ["Test Realm"]}, "realm_names"), ({"realm_names": {"TestRealm": 1}}, "realm_names"),
                        ({"connected": "TestRealm"}, "connected"), ({"connected": [None]}, "connected"),
                        ({"items": {"²": {"t": 1, "l": []}}}, "not an item"), ({"items": {"1" * 11: {"t": 1, "l": []}}}, "not an item"),
                        ({"items": {"1": {"t": True, "l": []}}}, "not an item"), ({"items": {"1": {"t": 1, "l": [], "name": 5}}}, "its name"),
                        ({"items": {"1": {"t": 1, "l": [], "full": "yes"}}}, "its name"),
                        (rows([pipe.MAX_PRICE + 1, 1, 1]), "unit price"), (rows([1, pipe.MAX_STACK + 1, 1]), "unit price"),
                        (rows([1, 1, pipe.MAX_AUCTIONS + 1]), "unit price"), (rows([True, 1, 1]), "unit price"),
                        ({"items": {str(i): {"t": 1, "l": []} for i in range(pipe.MAX_ITEMS + 1)}}, "too many items")):
        assert why in (pipe.check_scan(dict(good, **change)) or ""), change
    assert pipe.check_scan(dict(good, **rows([pipe.MAX_PRICE, pipe.MAX_STACK, pipe.MAX_AUCTIONS, 4]))) is None
    # what Forever's houses hold (9 Nov 2026): units listed at 99,999,999,999 copper, stacks of 10000, 5,937 alike
    assert pipe.check_scan(dict(good, **rows([99999999999, 10000, 5937, 4]))) is None
    for price in (2 ** 53, 10 ** 300):                                   # past what a client could have read
        assert "unit price" in pipe.check_scan(dict(good, **rows([price, 1, 1]))), price
    del good["scanned_at"]
    assert "scanned_at" in pipe.check_scan(good)
    # a document from every helper there has been: without faction, rungs of three, no realm_names
    old = {"format": "fwc-scan/1", "realm": "Test Realm", "scanned_at": 1790000100, "helper": "0.5.0",
           "items": {"4358": {"t": 1790000100, "name": "Rough Dynamite", "full": 1, "l": [[0, 20, 2], [79, 20, 1]]}}}
    assert pipe.check_scan(old) is None
    # a house as the core keeps it: who each row is from, and whether it is unverified
    kept = dict(old, helper=None, items={"4358": dict(old["items"]["4358"], by="h-abc", u=1)})
    assert pipe.check_scan(kept) is None


def test_a_scan_file_may_be_a_document():
    folder = Path(tempfile.mkdtemp())
    doc = pipe.scan_document(_scan())
    (folder / "packed.json.gz").write_bytes(pipe.pack(doc))
    (folder / "plain.json").write_text(json.dumps(doc), encoding="utf-8")
    for name in ("packed.json.gz", "plain.json"):
        sd = scan.load_scan(folder / name)
        assert sd.dataset == "Test Realm (Horde)" and sd.items[4358].total == 31 and sd.path.name == name
        assert scan.load_scan(folder / name, "Test Realm", "horde").faction == "Horde"
        for realm, faction in (("Test Realm", "Alliance"), ("Elsewhere", None)):
            try:
                scan.load_scan(folder / name, realm, faction)
                raise AssertionError("found an auction house that is not in the file")
            except SystemExit:
                pass


def test_lists():
    doc = pipe.lists_document({"FWC Alchemy": [(4358, "Rough Dynamite"), (118, "Minor Healing Potion")]})
    assert doc["format"] == "fwc-lists/1" and doc["queue"] == {"FWC Alchemy": [[4358, "Rough Dynamite"], [118, "Minor Healing Potion"]]}
    assert pipe.check_lists(doc) is None and pipe.check_lists(pipe.unpack(pipe.pack(doc))) is None
    assert "not a fwc-lists/1" in pipe.check_lists({"format": "x"})
    assert "FWC Alchemy" in pipe.check_lists(dict(doc, queue={"FWC Alchemy": [["4358", "x"]]}))


def test_where_the_pipe_is():
    import os
    kept = {k: os.environ.pop(k, None) for k in ("FWC_PIPE_URL", "FC_PIPE_URL", "FWC_PIPE_TOKEN", "FC_PIPE_TOKEN")}
    saved, pipe.settings.saved = pipe.settings.saved, lambda name: os.environ.get("FWC_" + name)
    state, pipe.settings.STATE = pipe.settings.STATE, Path(tempfile.mkdtemp())
    url, pipe.settings.PIPE_URL = pipe.settings.PIPE_URL, "https://built-in.test"
    try:
        assert pipe.Pipe().url == "https://built-in.test"                 # the one the helper comes with
        os.environ["FWC_PIPE_URL"] = "https://named.test/"
        assert pipe.Pipe().url == "https://named.test"                    # another one, named in the settings
        assert pipe.Pipe("https://given.test/", "t").url == "https://given.test"
        pipe.settings.PIPE_URL = ""
        del os.environ["FWC_PIPE_URL"]
        try:
            pipe.Pipe()
            raise AssertionError("made a pipe to nowhere")
        except pipe.PipeError as e:
            assert "FWC_PIPE_URL" in str(e)
    finally:
        pipe.settings.saved, pipe.settings.STATE, pipe.settings.PIPE_URL = saved, state, url
        os.environ.pop("FWC_PIPE_URL", None)
        os.environ.update({k: v for k, v in kept.items() if v})


def test_the_scans_listed_come_in_pages_and_all_are_fetched():
    asked = []

    class Paged(pipe.Pipe):
        def __init__(self):
            self.url = "https://paged.test"
        def ask(self, method, path, body=None, **kw):
            asked.append(path)
            after = int(path.split("after=")[1].split("&")[0])
            limit = int(path.split("limit=")[1].split("&")[0])
            rows = [{"id": i} for i in range(after + 1, 1203)]           # 1202 scans in all
            return {"scans": rows[:limit]}

    rows = Paged().scans(after=0)
    assert [r["id"] for r in rows] == list(range(1, 1203)) and len(asked) == 3     # 500, 500, 202
    assert "limit=500" in asked[0] and "after=500&" in asked[1] and "after=1000&" in asked[2]
    assert Paged().scans(after=1200) == [{"id": 1201}, {"id": 1202}]
    assert Paged().scans(after=1202) == []



def test_the_core_state_goes_as_a_zip_and_comes_back_as_bytes():
    seen = []

    class Remembering(pipe.Pipe):
        def __init__(self):
            self.url, self.token, self.registers = "https://state.test", "core", False
            self.kept = None
        def request(self, method, path, body=None, packed=True, content_type="application/json"):
            seen.append((method, path, packed, content_type))
            if method == "PUT":
                self.kept = body
                return 200, b'{"bytes": %d}' % len(body)
            if self.kept is None:
                return 404, b'{"error": "no state yet"}'
            return 200, self.kept

    p = Remembering()
    assert p.state() is None
    assert p.set_state(b"PK\x03\x04 a zip") == {"bytes": 10}
    assert p.state() == b"PK\x03\x04 a zip"                                     # bytes as they were, never unpacked
    assert seen[1] == ("PUT", "/v1/state", False, "application/zip")             # not gzipped on the way: a zip already
    assert seen[0][2:] == (True, "application/json")                             # what every other call sends

class _Clock:
    """Time that passes only when slept, and the sleeps."""
    def __init__(self):
        self.now, self.slept = 1000.0, []
    def sleep(self, s):
        self.slept.append(round(s, 3))
        self.now += s
    def clock(self):
        return self.now


def _paced(answers, pace, clock):
    """A Pipe whose requests answer `answers` in turn (status, Retry-After), each taking 0.2 s."""
    started = []

    class Answering(pipe.Pipe):
        def __init__(self):
            self.url, self.token, self.registers, self.pace = "https://paced.test", "core", False, pace
        def _request(self, method, path, body, packed, content_type):
            started.append(clock.now)
            status, self.retry_after = answers.pop(0) if answers else (200, 0)
            clock.now += 0.2
            return status, b"{}"
    return Answering(), started


def _faked(clock):
    kept = pipe._sleep, pipe._clock
    pipe._sleep, pipe._clock = clock.sleep, clock.clock
    return kept


def test_the_cores_requests_keep_a_pace_and_a_helpers_do_not():
    clock = _Clock()
    kept = _faked(clock)
    try:
        p, started = _paced([], pipe.CORE_PACE, clock)
        for i in range(40):
            p.scan(i + 1)
        gaps = [b - a for a, b in zip(started, started[1:])]
        assert min(gaps) >= pipe.CORE_PACE - 1e-9
        # a steady pace: never more than 8 in any 10 s
        assert max(sum(1 for t in started if s <= t < s + 10) for s in started) <= 8
        h, quick = _paced([], 0.0, clock)
        clock.slept.clear()
        for i in range(10):
            h.me()
        assert clock.slept == [] and len(quick) == 10
    finally:
        pipe._sleep, pipe._clock = kept


def test_only_the_cores_token_is_paced():
    saved = pipe.settings.saved
    try:
        pipe.settings.saved = lambda name: {"PIPE_CORE_TOKEN": "the-core"}.get(name)
        assert pipe.Pipe(url="https://p.test", token="the-core").pace == pipe.CORE_PACE
        assert pipe.Pipe(url="https://p.test", token="a-scanner").pace == 0
        assert pipe.Pipe(url="https://p.test", register=False).pace == 0          # a helper: no token given
        assert pipe.Pipe(url="https://p.test", token="a-scanner", pace=2).pace == 2
        pipe.settings.saved = lambda name: None                                  # no core token set anywhere
        assert pipe.Pipe(url="https://p.test", token="").pace == 0
    finally:
        pipe.settings.saved = saved


def test_a_429_is_waited_out_a_few_times_then_answered():
    clock = _Clock()
    kept = _faked(clock)
    try:
        p, started = _paced([(429, 0), (429, 30), (200, 0)], pipe.CORE_PACE, clock)
        assert p.request("GET", "/v1/scans/1") == (200, b"{}")
        assert len(started) == 3 and clock.slept == [pipe.RULE_WAIT, 30]       # the least wait, then what Retry-After said

        clock.slept.clear()
        p, started = _paced([(429, 7200)] * 10, pipe.CORE_PACE, clock)
        try:
            p.scan(1)
        except pipe.TooSoon:
            pass
        else:
            raise AssertionError("a 429 that does not end is the caller's")
        assert len(started) == pipe.RULE_TRIES + 1 and max(clock.slept) == pipe.RULE_WAIT_MOST

        clock.slept.clear()
        h, started = _paced([(429, 60)], 0.0, clock)                            # a helper: told at once, as before
        assert h.request("POST", "/v1/scans", b"") == (429, b"{}") and clock.slept == [] and len(started) == 1
    finally:
        pipe._sleep, pipe._clock = kept


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)

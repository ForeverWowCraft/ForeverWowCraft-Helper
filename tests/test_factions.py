"""An auction house is a realm and a faction: what the addon saves is read that way."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fwchelper import cli, pipe, scan  # noqa: E402

FILE = """
FWCS_DB = {
["Stonespine|Horde"] = {
[4358] = { ["name"] = "Rough Dynamite", ["t"] = 1790000000, ["complete"] = true, ["full"] = true, ["l"] = { { 79, 20 }, { 80, 5 } } },
[2840] = { ["name"] = "Copper Bar", ["t"] = 1790000000, ["complete"] = true, ["full"] = true, ["l"] = { } },
["__history"] = { [4358] = { { 1789990000, 90, 40 } } },
},
["Stonespine|Alliance"] = {
[4358] = { ["name"] = "Rough Dynamite", ["t"] = 1790003000, ["complete"] = true, ["full"] = true, ["l"] = { { 120, 5 } } },
},
["Stonespine"] = {
[4358] = { ["name"] = "Rough Dynamite", ["t"] = 1789000000, ["complete"] = true, ["l"] = { { 50, 1 } } },
[118] = { ["name"] = "Minor Healing Potion", ["t"] = 1789000000, ["complete"] = true, ["l"] = { } },
[119] = { ["name"] = "More", ["t"] = 1789000000, ["complete"] = true, ["l"] = { } },
},
["Elsewhere|Horde"] = {
[4358] = { ["name"] = "Rough Dynamite", ["t"] = 1790001000, ["complete"] = true, ["l"] = { { 60, 1 } } },
},
["__ui"] = { ["lastFull"] = 1790003000 },
}
"""


def _file():
    p = Path(tempfile.mkdtemp()) / "ForeverWowCraftScanner.lua"
    p.write_text(FILE, encoding="utf-8")
    return p


def test_names():
    assert scan.split_key("Stonespine|Horde") == ("Stonespine", "Horde") and scan.split_key("Stonespine") == ("Stonespine", "")
    assert scan.dataset_name("Stonespine", "Horde") == "Stonespine (Horde)" and scan.dataset_name("Stonespine") == "Stonespine"
    assert scan.faction_named("horde") == "Horde" and scan.faction_named(" ALLIANCE ") == "Alliance"
    assert scan.faction_named(None) is None and scan.faction_named("unknown") == ""
    try:
        scan.faction_named("sideways")
        raise AssertionError("a faction nobody has heard of")
    except SystemExit:
        pass


def test_what_a_file_holds():
    assert scan.datasets(_file()) == [("Stonespine", "Alliance", 1, 1790003000), ("Elsewhere", "Horde", 1, 1790001000),
                                      ("Stonespine", "Horde", 2, 1790000000), ("Stonespine", "", 3, 1789000000)]


def test_each_auction_house_is_read_by_itself():
    p = _file()
    horde = scan.load_scan(p, "Stonespine", "Horde")
    assert (horde.realm, horde.faction, horde.dataset) == ("Stonespine", "Horde", "Stonespine (Horde)")
    assert set(horde.items) == {2840, 4358} and horde.items[4358].listings == [(79, 20), (80, 5)] and list(horde.history) == [4358]
    assert scan.load_scan(p, "Stonespine", "alliance").items[4358].listings == [(120, 5)]
    before = scan.load_scan(p, "Stonespine", "unknown")                 # from before the addon knew the faction
    assert (before.faction, before.dataset, set(before.items)) == ("", "Stonespine", {118, 119, 4358})
    # left open: the one scanned most recently, not the one with most items
    assert scan.load_scan(p).dataset == "Stonespine (Alliance)"
    assert scan.load_scan(p, faction="Horde").dataset == "Elsewhere (Horde)"
    assert scan.load_scan(p, "Elsewhere").dataset == "Elsewhere (Horde)"
    for realm, faction in (("Elsewhere", "Alliance"), ("Nowhere", None)):
        try:
            scan.load_scan(p, realm, faction)
            raise AssertionError("found an auction house that is not in the file")
        except SystemExit as e:
            assert "Stonespine (Horde)" in str(e)


def test_every_auction_house_of_a_file_is_sent():
    sent = []

    class Service:
        url = "test"

        def send_scan(self, doc):
            sent.append((doc["realm"], doc["faction"], sorted(doc["items"])))
            return {"id": len(sent), "new": True}

    kept, cli.settings.STATE = cli.settings.STATE, Path(tempfile.mkdtemp())
    try:
        p = _file()
        assert cli.send_once(Service(), p) is True
        assert sorted(sent) == [("Elsewhere", "Horde", ["4358"]), ("Stonespine", "", ["118", "119", "4358"]),
                                ("Stonespine", "Alliance", ["4358"]), ("Stonespine", "Horde", ["2840", "4358"])]
        assert cli.send_once(Service(), p) is False and len(sent) == 4          # nothing changed: nothing sent again
        p.write_text(FILE.replace("{ 120, 5 }", "{ 125, 5 }"), encoding="utf-8")  # the Alliance one was scanned again
        assert cli.send_once(Service(), p) is True and sent[4:] == [("Stonespine", "Alliance", ["4358"])]
        assert cli.send_once(Service(), p, "Stonespine", "Horde", again=True) is True and sent[5][:2] == ("Stonespine", "Horde")

        # an update of the helper changes the document (its version, what else it says), not what was scanned: nothing is sent again
        version, pipe.__version__ = pipe.__version__, "9.9.9"
        try:
            assert pipe.scan_document(scan.load_scan(p, "Stonespine", "Horde"))["helper"] == "9.9.9"
            assert cli.send_once(Service(), p) is False and len(sent) == 6
        finally:
            pipe.__version__ = version
        doc = pipe.scan_document(scan.load_scan(p, "Stonespine", "Horde"))
        assert pipe.mark(doc) == pipe.mark(dict(doc, helper="0.1", realm_names={"Stonespine": "Stonespine"}, scanned_at=0))
        assert pipe.mark(doc) != pipe.mark(dict(doc, faction="Alliance")) and pipe.mark(doc) != pipe.mark(dict(doc, items={}))

        class Picky(Service):                     # the service refuses one auction house: the others still go
            def send_scan(self, doc):
                if doc["faction"] == "Horde":
                    raise pipe.PipeError("POST /v1/scans: 400 item 4358: [0, 20, 1] is not [unit price, stack size, auctions]")
                return super().send_scan(doc)
        del sent[:]
        try:
            cli.send_once(Picky(), p, again=True)
            raise AssertionError("no word of the refusal")
        except cli.Refused as e:
            assert str(e) == "2 auction houses not sent" and len(e.errors) == 2
        assert sorted(f for _, f, _ in sent) == ["", "Alliance"]
    finally:
        cli.settings.STATE = kept
    assert all(pipe.check_scan({"format": "fwc-scan/1", "realm": r, "faction": f, "items": {i: {"t": 1, "l": []} for i in ids}}) is None
               for r, f, ids in sent)


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)

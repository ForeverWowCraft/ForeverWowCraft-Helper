"""The vendors the addon met, read from its saved file and sent to the pipe (fwchelper/scan.py
vendors, fwchelper/pipe.py vendors_document, fwchelper/cli.py send_vendors_once)."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fwchelper import cli, pipe, scan, settings  # noqa: E402

SAVED = """
FWCS_DB = {
	["__vendors"] = {
		[3579] = {
			["name"] = "Tharynn Bouden",
			["map"] = 1453,
			["x"] = 0.5,
			["y"] = 0.6,
			["t"] = 1790000000,
			["faction"] = "Horde",
			["build"] = "70790",
			["items"] = {
				[2320] = { ["price"] = 10, ["stack"] = 1, ["n"] = -1, ["usable"] = true, ["t"] = 1790000000 },
				[6270] = { ["price"] = 0, ["stack"] = 1, ["n"] = 1, ["usable"] = false, ["t"] = 1790000000, ["cost"] = { [250000] = 45 } },
			},
		},
	},
}
"""


def _saved() -> Path:
    f = Path(tempfile.mkdtemp()) / "ForeverWowCraftScanner.lua"
    f.write_text(SAVED, encoding="utf-8")
    return f


class FakePipe:
    def __init__(self):
        self.sent = []

    def send_vendors(self, doc):
        problem = pipe.check_vendors(doc)
        assert problem is None, problem
        self.sent.append(doc)
        return {"vendors": len(doc["vendors"]), "new": True}


def test_the_vendors_met_are_read_and_make_a_document_the_pipe_takes():
    seen = scan.vendors(_saved())
    assert list(seen) == [3579] and seen[3579]["name"] == "Tharynn Bouden" and seen[3579]["faction"] == "Horde"
    assert seen[3579]["items"][2320] == {"price": 10, "stack": 1, "n": -1, "usable": True, "t": 1790000000}
    assert seen[3579]["items"][6270]["cost"] == {250000: 45} and seen[3579]["items"][6270]["usable"] is False
    doc = pipe.vendors_document(seen)
    assert doc["format"] == pipe.VENDORS_FORMAT and pipe.check_vendors(doc) is None
    assert "3579" in doc["vendors"] and "2320" in doc["vendors"]["3579"]["items"]           # keys as strings, as JSON has them
    assert "character" not in json.dumps(doc) and "Thrallson" not in json.dumps(doc)
    # what is not a sightings document is said
    assert pipe.check_vendors({"format": "fwc-scan/1"}).startswith("not a fwc-vendors/1")
    assert pipe.check_vendors({"format": pipe.VENDORS_FORMAT, "vendors": {}}) == "no vendors"
    bad = pipe.vendors_document(seen)
    bad["vendors"]["3579"]["x"] = 7
    assert pipe.check_vendors(bad) == "vendor 3579: not on its map"
    assert pipe.mark_vendors(doc) == pipe.mark_vendors(dict(doc, helper="other"))         # the helper's version is not what changed


def test_the_sightings_are_sent_when_they_changed():
    kept = settings.STATE
    settings.STATE = Path(tempfile.mkdtemp())
    try:
        f, p = _saved(), FakePipe()
        assert cli.send_vendors_once(p, f) is True and len(p.sent) == 1
        assert cli.send_vendors_once(p, f) is False and len(p.sent) == 1                   # the same again: not sent
        f.write_text(SAVED.replace('["n"] = 1,', '["n"] = 0,'), encoding="utf-8")        # a ware sold out: changed
        assert cli.send_vendors_once(p, f) is True and len(p.sent) == 2
        assert json.loads((settings.STATE / "sent.json").read_text(encoding="utf-8"))["__vendors"] == pipe.mark_vendors(p.sent[-1])
        f.write_text("FWCS_DB = {}", encoding="utf-8")
        assert cli.send_vendors_once(p, f) is False                                         # nothing met: nothing sent
    finally:
        settings.STATE = kept


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)

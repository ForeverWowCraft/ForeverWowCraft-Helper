"""The vendors the addon met, read from its saved file and sent to the pipe (fwchelper/scan.py
vendors, fwchelper/pipe.py vendors_document, fwchelper/cli.py send_vendors_once)."""
import json
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
	["__recipes"] = {
		[250389] = { ["l"] = 45, ["t"] = 1790000200 },
		[7288] = { ["l"] = 1, ["t"] = 1790000200 },
		[250390] = { ["l"] = 1, ["t"] = 1790000300, ["tip"] = { 5, -- [1]
			45, -- [2]
		}, ["made"] = 99001, ["madel"] = 35 },
		[250391] = { ["l"] = 1, ["t"] = 1790000300, ["tip"] = { 5, 45 }, ["made"] = 99002 },
		[250392] = { ["l"] = 1, ["t"] = 1790000300, ["tip"] = { 5 }, ["made"] = true, ["madel"] = 35 },
		["bad"] = { ["l"] = 45, ["t"] = 1790000200 },
	},
	["__trainers"] = {
		[3363] = {
			["name"] = "Drakk Stonehand",
			["map"] = 1453,
			["x"] = 0.4,
			["y"] = 0.7,
			["t"] = 1790000100,
			["faction"] = "Horde",
			["build"] = "70790",
			["skill"] = "Leatherworking",
			["teaches"] = {
				["Embossed Leather Gloves"] = 45,
				["Journeyman Leatherworker"] = 50,
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
    # the trainers met, in the same document (since 1.6.12): each service and the skill it asks for
    met = scan.trainers(_saved())
    assert list(met) == [3363] and met[3363]["skill"] == "Leatherworking" and met[3363]["teaches"] == {"Embossed Leather Gloves": 45, "Journeyman Leatherworker": 50}
    both = pipe.vendors_document(seen, met)
    assert pipe.check_vendors(both) is None and both["trainers"]["3363"]["teaches"]["Embossed Leather Gloves"] == 45 and doc["trainers"] == {}
    assert pipe.check_vendors(pipe.vendors_document({}, met)) is None                     # trainers alone are a document
    named = pipe.vendors_document({"Gloria Femmel": dict(seen[3579], name="Gloria Femmel")}, {"Thuwd": dict(met[3363], name="Thuwd")})
    assert pipe.check_vendors(named) is None and "Gloria Femmel" in named["vendors"]        # a name for a key where the client gave no id (1.6.14)
    assert pipe.check_vendors({"format": pipe.VENDORS_FORMAT, "vendors": {"": seen[3579]}}) == "vendor '' is not a vendor"
    assert pipe.mark_vendors(both) != pipe.mark_vendors(doc)                              # a trainer seen is a change
    bad = pipe.vendors_document(seen, met)
    bad["trainers"]["3363"]["teaches"]["Embossed Leather Gloves"] = "45"
    assert pipe.check_vendors(bad) == "trainer 3363: 'Embossed Leather Gloves' is not a service"
    bad["trainers"]["3363"]["skill"] = ""
    assert pipe.check_vendors(bad) == "trainer 3363: no skill"
    # the recipe scrolls looked at, with the character level each asks for (since 1.6.22: a hotfix the tables lack);
    # 7288's level 1 is a row an addon before 1.7.4 kept for a scroll asking none (1.7.4 lets such rows go at login), read as it is
    # and ignored by the core, which takes no level of 1 or below
    # since 1.7.5 a scroll the player hovered has its tooltip's "Requires Level" lines [line, level, ...], the made item and
    # that item's item-data level beside its own item-data level ("level", as it has always been); a malformed field is dropped
    asked = scan.recipes(_saved())
    assert asked == {250389: {"level": 45, "t": 1790000200}, 7288: {"level": 1, "t": 1790000200},
                     250390: {"level": 1, "t": 1790000300, "tip": [5, 45], "made": 99001, "made_level": 35},
                     250391: {"level": 1, "t": 1790000300, "tip": [5, 45], "made": 99002},
                     250392: {"level": 1, "t": 1790000300}}
    full = pipe.vendors_document(seen, met, asked)
    assert pipe.check_vendors(full) is None and full["recipes"] == {"250389": {"level": 45, "t": 1790000200}, "7288": {"level": 1, "t": 1790000200},
                                                                    "250390": {"level": 1, "t": 1790000300, "tip": [5, 45], "made": 99001, "made_level": 35},
                                                                    "250391": {"level": 1, "t": 1790000300, "tip": [5, 45], "made": 99002},
                                                                    "250392": {"level": 1, "t": 1790000300}}
    bad = pipe.vendors_document(seen, met, asked)
    bad["recipes"]["250390"]["tip"] = [5, 45, 6]
    assert pipe.check_vendors(bad) == "recipe '250390': its tip, made or made_level is not what it should be"
    bad["recipes"]["250390"]["tip"] = [5, 45]
    bad["recipes"]["250390"]["made"] = True
    assert pipe.check_vendors(bad) == "recipe '250390': its tip, made or made_level is not what it should be"
    assert pipe.check_vendors(pipe.vendors_document({}, {}, asked)) is None               # the scrolls alone are a document
    assert pipe.mark_vendors(full) != pipe.mark_vendors(both) and both["recipes"] == {}
    bad = pipe.vendors_document(seen, met, asked)
    bad["recipes"]["250389"]["level"] = "45"
    assert pipe.check_vendors(bad) == "recipe '250389': not a level"
    bad["recipes"] = {"x": {"level": 45, "t": 1}}
    assert pipe.check_vendors(bad) == "recipe 'x': not a level"


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
        f.write_text(SAVED.replace('["__vendors"]', '["__was"]'), encoding="utf-8")       # trainers met, no vendor: sent all the same
        assert cli.send_vendors_once(p, f) is True and p.sent[-1]["vendors"] == {} and "3363" in p.sent[-1]["trainers"]
        f.write_text("FWCS_DB = {}", encoding="utf-8")
        assert cli.send_vendors_once(p, f) is False                                         # nothing met: nothing sent
    finally:
        settings.STATE = kept


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)

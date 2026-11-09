"""The routes for the addon: the document the site has, whose houses are fetched, Plans.lua, and
that nothing of what a character has is sent."""
import functools
import http.server
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

HELPER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HELPER))

from fwchelper import cli, luatable, pipe, plans, scan, settings  # noqa: E402

NOW = int(time.time())


def document(house="stonespine--horde", realm="Stonespine", faction="Horde", generated=NOW) -> dict:
    """A small fwc-plans/1 document: tailoring 1 to 60 with bolts made on the way, a short
    enchanting route, and tailoring again for an enchanter (the shirts disenchanted)."""
    bolt, cloth, thread, shirt, vest, dye, dust = 2996, 2589, 2320, 2576, 2568, 2324, 10940
    tailoring = {
                "profession": "tailoring", "skill_line": 197, "variant": "trainer", "start": 1, "target": 60,
                "net": -5000, "spent": 7000, "sold": 2000, "gaps": [],
                "steps": [
                    {"from": 1, "to": 41, "recipe": "Bolt of Linen Cloth", "spell": 2963, "crafts": 40, "uses": [[cloth, 2]],
                     "makes": [bolt, 1], "per": [1] * 40, "buy": [cloth], "craft": []},
                    {"from": 41, "to": 51, "recipe": "White Linen Shirt", "spell": 2393, "crafts": 10,
                     "uses": [[bolt, 1], [thread, 1], [dye, 1]], "makes": [shirt, 1], "per": [1] * 10, "buy": [thread, dye], "craft": []},
                    {"from": 51, "to": 60, "recipe": "Brown Linen Vest", "spell": 2385, "crafts": 12,
                     "uses": [[bolt, 3], [thread, 1]], "makes": [vest, 1], "per": [1.333] * 9, "buy": [thread, cloth], "craft": [bolt]}],
                "made": {str(bolt): [1, [[cloth, 2]], 2963]},
                "buy": {str(cloth): [30, "ah"], str(thread): [10, "vendor"], str(dye): [25, "vendor"]},     # a third number: a vendor's price beside a cheaper house
                "sell": {str(shirt): 40.5, str(vest): 120}, "disenchant": []}
    enchanter = dict(tailoring, companions=["enchanting"], sell={str(shirt): 60, str(vest): 120}, disenchant=[shirt], sold=2400)
    enchanting = {"profession": "enchanting", "skill_line": 333, "variant": "trainer", "start": 1, "target": 60,
                  "net": -3000, "spent": 3000, "sold": 0, "gaps": [],
                  "steps": [{"from": 1, "to": 60, "recipe": "Enchant Bracer - Minor Health", "spell": 7418, "crafts": 59,
                             "uses": [[dust, 1]], "per": [1] * 59, "buy": [dust], "craft": []}],
                  "made": {}, "buy": {str(dust): [50, "ah"]}, "sell": {}, "disenchant": []}
    return {"format": "fwc-plans/1", "house": house, "realm": realm, "faction": faction, "realms": [realm, realm.replace(" ", "")],
            "scanned_at": NOW - 600, "generated": generated,
            "items": {str(bolt): "Bolt of Linen Cloth", str(cloth): "Linen Cloth", str(thread): "Coarse Thread",
                      str(shirt): "White Linen Shirt", str(vest): 'Brown "Linen" Vest', str(dye): "Bleach", str(dust): "Strange Dust"},
            "variants": [["trainer", "Trainer recipes only"]],
            "plans": {"tailoring-trainer": tailoring, "enchanting-trainer": enchanting,
                      "cooking-trainer": dict(enchanting, profession="cooking", skill_line=185, net=-2000, spent=2000)},
            "also": {"tailoring-trainer+enchanting": enchanter}}


SAVED = '''
FWCS_DB = {
	["Stonespine|Horde"] = {
		[2589] = {
			["name"] = "Linen Cloth",
			["t"] = %d,
			["complete"] = true,
			["l"] = {
				{
					30, -- [1]
					20, -- [2]
				}, -- [1]
			},
		},
	},
	["__chars"] = {
		["Stonespine|Thrallson"] = {
			["name"] = "Thrallson",
			["realm"] = "Stonespine",
			["house"] = "Stonespine",
			["faction"] = "Horde",
			["t"] = %d,
			["items"] = {
				[2996] = {
					5, -- [1]
					12, -- [2]
				},
			},
			["skills"] = {
				[197] = 44,
			},
		},
		["ClassicBetaPvE|Bankalt"] = {
			["name"] = "Bankalt",
			["realm"] = "Classic Beta PvE 2",
			["house"] = "ClassicBetaPvE",
			["faction"] = "Alliance",
			["t"] = 5,
			["items"] = {
			},
		},
	},
}
''' % (NOW - 60, NOW - 30)


def _saved() -> Path:
    f = Path(tempfile.mkdtemp()) / "ForeverWowCraftScanner.lua"
    f.write_text(SAVED, encoding="utf-8")
    return f


def test_the_document_is_checked():
    assert plans.check_plans(document()) is None
    three = document()                                                     # a vendor's price beside the house's (7 Nov 2026)
    three["plans"]["tailoring-trainer"]["buy"]["2589"] = [30, "ah", 45]
    assert plans.check_plans(three) is None
    three["plans"]["tailoring-trainer"]["buy"]["2589"] = [30, "ah", "45"]
    assert "buy[2589]" in plans.check_plans(three)
    assert plans.check_plans({"format": "fwc-scan/1"}) == "not a fwc-plans/1 document"
    bad = document()
    bad["plans"]["tailoring-trainer"]["steps"][0]["per"] = [1, 1]                # not one for each skill point
    assert "per" in plans.check_plans(bad)
    bad = document()
    bad["plans"]["tailoring-trainer"]["steps"][1]["uses"].append([99999, 1])    # an item without a name
    assert "names an item" in plans.check_plans(bad)
    bad = document()
    bad["faction"] = "Pirates"
    assert "faction" in plans.check_plans(bad)


def test_plans_lua_holds_the_document_for_the_addon():
    text = plans.plans_text([document(realm="Classic Beta PvE", house="classicbetapve--horde")], "https://example.test", written=NOW)
    parsed = luatable.parse(text)
    assert parsed["FWCS_PLANS_WRITTEN"] == NOW and "FWCS_DEV" not in parsed             # nothing in the file shows the bar (1.5.6)
    held = parsed["FWCS_PLANS"]["classicbetapve--horde"]
    assert held["realms"] == ["classicbetapve"] and held["faction"] == "Horde"       # realms as the addon compares them
    assert held["items"][2568] == 'Brown "Linen" Vest'                                # by number, quotes kept
    plan = held["plans"]["tailoring-trainer"]
    assert plan["steps"][2]["uses"] == [[2996, 3], [2320, 1]] and plan["steps"][2]["craft"] == [2996]
    assert plan["made"][2996] == [1, [[2589, 2]], 2963] and plan["buy"][2589] == [30, "ah"] and plan["sell"][2576] == 40.5
    assert plan["steps"][0]["craft"] == {} and plan["gaps"] == {}                     # empty lists: the addon walks them with ipairs
    # nothing in a document can become code or a UI escape in the game
    assert plans.lua('a "name"\\ with |cffff0000colour|r\x00and\x07control') == '"a \\"name\\"\\\\ with ||cffff0000colour||randcontrol"'
    assert plans.lua({"1": 2.5, "x": [None, True]}) == "{\n [1]=2.5,\n [\"x\"]={nil,true},\n}"
    try:
        plans.lua(float("nan"))
        raise AssertionError("nan was written")
    except ValueError:
        pass
    also = held["also"]["tailoring-trainer+enchanting"]
    assert also["companions"] == ["enchanting"] and also["disenchant"] == [2576] and also["sell"][2576] == 60
    assert plans.check_plans(document()) is None
    bad = document()
    bad["also"]["tailoring-trainer+enchanting"]["companions"] = "enchanting"
    assert "companions" in plans.check_plans(bad)


def test_the_characters_say_whose_routes_to_fetch():
    f = _saved()
    chars = plans.characters(f)
    assert [c["name"] for c in chars] == ["Thrallson", "Bankalt"]                     # the last played first
    assert chars[0]["items"] == {2996: [5, 12]} and chars[0]["skills"] == {197: 44}
    want = plans.wanted([f])
    assert {(plans.spelt(r), f) for r, f in want} == {("stonespine", "Horde"), ("classicbetapve2", "Alliance"), ("classicbetapve", "Alliance")}
    assert ("Stonespine", "Horde") in want                                            # as the game shows it too, for the site's rules
    houses = [{"key": "stonespine--horde", "realm": "Stonespine", "faction": "Horde", "realms": ["Stonespine"]},
              {"key": "stonespine--alliance", "realm": "Stonespine", "faction": "Alliance", "realms": ["Stonespine"]},
              # a house of connected realms, named by the first: the character on the second is of it
              {"key": "classicbetapve--alliance", "realm": "Classic Beta PvE", "faction": "Alliance",
               "realms": ["Classic Beta PvE", "Classic Beta PvE 2", "ClassicBetaPvE", "ClassicBetaPvE2"]},
              {"key": "other--horde", "realm": "Other", "faction": "Horde", "realms": ["Other"]}]
    houses = [dict(h, ingame=True) for h in houses]
    assert [h["key"] for h in plans.choose(houses, want)] == ["stonespine--horde", "classicbetapve--alliance"]
    # nobody seen yet: everything when the site has few houses, nothing when it has many
    assert len(plans.choose(houses, set())) == 4
    assert plans.choose(houses * 3, set()) == []
    # no character seen yet (a first install): the houses of the client's region, where they are few (the blank /fwc
    # window players reported, 9 Nov 2026); a region the site has no house of changes nothing
    many = [dict(houses[0], key=f"us{r.lower().replace(' ', '')}--{f.lower()}", realm=f"US {r}", faction=f) for r in ("PvE", "PvP", "RP", "RP PvP") for f in ("Alliance", "Horde")] \
        + [dict(houses[0], key=f"eu{r.lower()}--{f.lower()}", realm=f"EU {r}", faction=f) for r in ("PvE", "PvP", "RP") for f in ("Alliance", "Horde")]
    assert plans.choose(many, set()) == [] and len(plans.choose(many, set(), "US")) == 8 and len(plans.choose(many, set(), "eu")) == 6
    assert plans.choose(many, set(), "KR") == [] and {h["realm"] for h in plans.choose(many, set(), "US")} == {"US PvE", "US PvP", "US RP", "US RP PvP"}
    assert [h["key"] for h in plans.choose(houses, want, "US")] == ["stonespine--horde", "classicbetapve--alliance"]     # characters seen: theirs alone
    assert plans.choose([dict(houses[0], ingame=False)], set()) == []                 # a house without routes for the addon
    assert plans.choose([{k: v for k, v in houses[0].items() if k != "ingame"}], want) == []      # a site from before it had any
    # a realm nobody has scanned from is of the house its name says, by the site's rules (6 Nov 2026)
    rules = [["^CAMWOW (?:US|AU)\\d+ Realm \\d+ (PvE|PvP|RP PvP|RP)$", "US \\1"], ["^CAMWOW (EU|TW|KR)\\d+ Realm \\d+ (PvE|PvP|RP PvP|RP)$", "\\1 \\2"]]
    us = {"key": "uspve--alliance", "realm": "US PvE", "faction": "Alliance", "realms": ["CAMWOW US1 Realm 1 PvE", "USPvE"], "rules": rules, "ingame": True}
    new = {("CAMWOW AU1 Realm 9 PvE", "Alliance"), ("camwowau1realm9pve", "Alliance"), ("CAMWOW US1 Realm 4 PvP", "Alliance"),
           ("CAMWOW US1 Realm 9 PvE", "Horde")}
    assert plans.by_rule(us, new) == ["CAMWOW AU1 Realm 9 PvE"] and plans.choose([us], new) == [us]
    assert plans.choose([dict(us, rules=[])], new) == [] and plans.choose([dict(us, rules=[["(", "x"], "no"])], new) == []
    assert plans.ruled("CAMWOW EU4 Realm 2 PvP", rules) == "EU PvP" and plans.ruled("Stonespine", rules) is None


def test_the_clients_region_is_read_from_the_games_own_settings():
    import os
    import tempfile
    root = Path(tempfile.mkdtemp())
    kept = os.environ.get("FWC_WOW_DIR")
    os.environ["FWC_WOW_DIR"] = str(root)
    try:
        assert scan.portal() is None                                             # no file
        wtf = root / scan.flavor() / "WTF"
        wtf.mkdir(parents=True)
        (wtf / "Config.wtf").write_text('SET agentUID "wowf"\nSET portal "US"\nSET lastCharacterIndex "2"\n', encoding="utf-8")
        assert scan.portal() == "US"
        (wtf / "Config.wtf").write_text('SET portal "eu"\n', encoding="utf-8")
        assert scan.portal() == "EU"
        (wtf / "Config.wtf").write_text('SET agentUID "wowf"\n', encoding="utf-8")
        assert scan.portal() is None                                             # no such line
    finally:
        if kept is None:
            os.environ.pop("FWC_WOW_DIR", None)
        else:
            os.environ["FWC_WOW_DIR"] = kept


def test_a_realm_nobody_scanned_from_gets_its_house_by_the_sites_rules():
    doc = document(realm="Rock", house="rock--horde")
    listed = [{"key": "rock--horde", "realm": "Rock", "faction": "Horde", "realms": ["Rock"], "generated": NOW, "ingame": True}]
    site, srv, root = _site({"rock--horde": doc}, listed, rules=[["^Stone(spine)$", "Rock"]])     # Thrallson is on Stonespine
    game = Path(tempfile.mkdtemp())
    (game / scan.ADDON_NAME).mkdir()
    (game / scan.PLANS_ADDON).mkdir()
    saved = _saved()
    kept = settings.STATE, scan.addons_dir, scan.find_saved_variables
    settings.STATE, scan.addons_dir, scan.find_saved_variables = Path(tempfile.mkdtemp()) / "state", (lambda: game), (lambda: [saved])
    try:
        docs, written = plans.refresh(site)
        assert [d["house"] for d in docs] == ["rock--horde"]
        held = luatable.parse(written[0].read_text(encoding="utf-8"))["FWCS_PLANS"]["rock--horde"]
        assert "stonespine" in held["realms"]                     # as the addon compares: it finds the character's house in game
    finally:
        settings.STATE, scan.addons_dir, scan.find_saved_variables = kept
        srv.shutdown()


def test_the_site_says_how_often_the_watch_looks():
    kept = dict(plans.INTERVALS)
    try:
        plans.INTERVALS.clear()                                    # nothing fetched yet: the helper's own
        assert (plans.plans_every(), plans.fresh_every()) == (settings.PLANS_EVERY, settings.FRESH_EVERY)
        assert plans.hints({"houses": []}) == {} and plans.hints(None) == {} and plans.hints({"helper": 5}) == {}
        plans.INTERVALS.update(plans.hints({"helper": {"plans_every": 900, "fresh_every": 3600}}))
        assert (plans.plans_every(), plans.fresh_every()) == (900, 3600)
        assert plans.hints({"helper": {"plans_every": 5, "fresh_every": 10 ** 9}}) == {"plans_every": 60, "fresh_every": 86400}
        for wrong in ("600", 600.0, None, True, False, [600]):    # whole seconds only
            assert plans.hints({"helper": {"plans_every": wrong, "fresh_every": wrong}}) == {}
        plans.INTERVALS.clear()
        plans.INTERVALS.update(plans.hints({"helper": {"plans_every": 1200, "fresh_every": "x"}}))
        assert (plans.plans_every(), plans.fresh_every()) == (1200, settings.FRESH_EVERY)
    finally:
        plans.INTERVALS.clear()
        plans.INTERVALS.update(kept)


def test_nothing_a_character_has_is_sent():
    doc = pipe.scan_document(scan.load_scan(_saved()))
    sent = json.dumps(doc)
    assert doc["items"].keys() == {"2589"}
    assert "Thrallson" not in sent and "__chars" not in sent and "2996" not in sent and "skills" not in sent


def _site(docs: dict, houses: list, rules: list | None = None) -> tuple[str, http.server.ThreadingHTTPServer]:
    root = Path(tempfile.mkdtemp())
    (root / "data").mkdir()
    (root / "data" / "houses.json").write_text(json.dumps({"houses": houses, **({"rules": rules} if rules else {})}), encoding="utf-8")
    for key, doc in docs.items():
        (root / "data" / key).mkdir()
        (root / "data" / key / "ingame.json").write_text(json.dumps(doc), encoding="utf-8")

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv, root


def test_routes_are_fetched_written_and_kept():
    doc = document()
    listed = [{"key": "stonespine--horde", "realm": "Stonespine", "faction": "Horde", "realms": ["Stonespine"], "generated": NOW, "ingame": True},
              {"key": "other--horde", "realm": "Other", "faction": "Horde", "realms": ["Other"], "generated": NOW, "ingame": True}]
    site, srv, root = _site({"stonespine--horde": doc}, listed)
    game = Path(tempfile.mkdtemp())
    (game / scan.ADDON_NAME).mkdir()
    (game / scan.PLANS_ADDON).mkdir()
    saved = _saved()
    kept = settings.STATE, scan.addons_dir, scan.find_saved_variables, plans.site_url
    settings.STATE, scan.addons_dir, scan.find_saved_variables = Path(tempfile.mkdtemp()) / "state", (lambda: game), (lambda: [saved])
    try:
        docs, written = plans.refresh(site)
        assert [d["house"] for d in docs] == ["stonespine--horde"]                    # the character's house, not the other
        assert written == [settings.STATE / "Plans.lua", game / scan.PLANS_ADDON / "Plans.lua"]
        assert luatable.parse(written[1].read_text(encoding="utf-8"))["FWCS_PLANS"]["stonespine--horde"]["items"][2589] == "Linen Cloth"
        # nothing new: nothing fetched or written, but the stamp moves, so the addon sees the helper runs
        old = NOW - 3600
        for f in written:
            f.write_text(plans._STAMP.sub(f"FWCS_PLANS_WRITTEN = {old}", f.read_text(encoding="utf-8")), encoding="utf-8")
        assert plans.refresh(site) == ([], [])
        assert all(luatable.parse(f.read_text(encoding="utf-8"))["FWCS_PLANS_WRITTEN"] >= NOW for f in written)
        # installing the addon again does not lose the routes
        assert "stonespine--horde" not in (settings.ROOT / "addon" / scan.ADDON_NAME / "Plans.lua").read_text(encoding="utf-8")
        scan.install_addon(game)
        assert "stonespine--horde" in (game / scan.PLANS_ADDON / "Plans.lua").read_text(encoding="utf-8")
        # a newer build of the site is fetched
        listed[0]["generated"] = NOW + 60
        (root / "data" / "houses.json").write_text(json.dumps({"houses": listed}), encoding="utf-8")
        assert len(plans.refresh(site)[1]) == 2 and plans.stamps() == {"stonespine--horde": NOW + 60}
        # a site that is not there is a line in a loop, and an error when asked for by hand
        # a document the site should never serve is refused, not written
        (root / "data" / "stonespine--horde" / "ingame.json").write_text('{"format": "fwc-plans/1", "net": NaN}', encoding="utf-8")
        listed[0]["generated"] = NOW + 120
        (root / "data" / "houses.json").write_text(json.dumps({"houses": listed}), encoding="utf-8")
        try:
            plans.refresh(site)
            raise AssertionError("NaN was taken")
        except plans.PlansError as e:
            assert "not JSON" in str(e)
        srv.shutdown()
        srv.server_close()
        plans.site_url = lambda: site
        assert cli.plans(quiet=True, again=True) is False
        try:
            cli.plans(again=True)
            raise AssertionError("no error")
        except SystemExit as e:
            assert "could not be reached" in str(e)
    finally:
        settings.STATE, scan.addons_dir, scan.find_saved_variables, plans.site_url = kept


def test_a_helper_older_than_the_site_asks_is_told_to_update():
    kept = plans.get
    try:
        doc = document()
        doc["needs_helper"] = "1.1.0"                      # what the site writes now: this helper reads it
        plans.get = lambda url: doc
        assert plans.fetch({"key": "stonespine--horde"})["house"] == "stonespine--horde"
        doc["needs_helper"] = "99.0.0"                     # a site from the future: update, not "not usable"
        try:
            plans.fetch({"key": "stonespine--horde"})
            raise AssertionError("no error")
        except plans.PlansError as e:
            assert "need helper 99.0.0 or newer" in str(e) and "update the helper" in str(e)
        # what 1.0.x would say of today's document: its `made` rows carry the spell
        assert plans.version_tuple("1.1.0") > plans.version_tuple("1.0.0") and plans.version_tuple(plans.__version__) >= (1, 1, 0)
    finally:
        plans.get = kept


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)

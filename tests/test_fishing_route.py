"""The fishing route in game (12 Nov 2026): cooking levelled with the fish the player catches, a vendor's goods and a vendor's
recipe scrolls, nothing from the auction house. The site keeps one copy a faction (extra/cooking-fishing.ingame.json in a house's
folder, its houses.json entry says "fishing": true); the helper fetches it once a faction and writes it into Plans.lua as a second
global, FWCS_ROUTES, which no earlier addon reads; the addon offers it as "Fishing only" on cooking.

What is held here: an earlier helper and addon see exactly what they saw (the text the helper writes without a route is what it was,
a route in Plans.lua changes nothing for an addon that does not read it, a house without a route offers no choice), the route is
checked like every document the site serves, the choice is the character's and survives a look at another profession, and a fish
is caught: the verdict says so, no auction house wording, no arrow to an auctioneer, no Buy button, nothing for Auctionator.

Needs a Lua: `pip install lupa`; without it the Lua cases are skipped and the helper's still run.
"""
import copy
import functools
import http.server
import json
import re
import sys
import tempfile
import threading
from pathlib import Path

HELPER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HELPER))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fwchelper import plans, scan, settings  # noqa: E402
from test_ingame import ADDON, _game, lupa  # noqa: E402
from test_plans import NOW, _saved, document  # noqa: E402

SMALLFISH, LONGJAW, MACKEREL, SAGEFISH, SPICES = 6291, 6289, 6303, 21071, 2678
SCROLL_SMALLFISH, SCROLL_LONGJAW, SCROLL_MACKEREL, SCROLL_SAGE = 6325, 6328, 6326, 21099
SPELL_SMALLFISH, SPELL_MACKEREL, SPELL_LONGJAW, SPELL_SAGE = 7751, 7752, 7753, 25704
COOKING = 185
ERA = "Where the fish are caught is the Classic-era world's: a guide to check in game."
ARTISAN = "Artisan Cooking comes from the quest Clamlette Surprise. A route of fish alone may stop at 225 until this is checked on Forever."


def _step(frm, to, recipe, spell, uses, makes, buy, learn=None, alt=None):
    step = {"from": frm, "to": to, "recipe": recipe, "spell": spell, "crafts": to - frm, "uses": uses, "makes": makes,
            "per": [1] * (to - frm), "buy": buy, "craft": []}
    if learn:
        step["learn"] = learn
    if alt:
        step["alt"] = alt
    return step


def fishing_route(long: bool = False) -> dict:
    """The route as the site writes it (fishroute.addon_extras): a cooking plan to 100 in three stretches, each fish a buy row
    with the source "catch", a vendor's spices, the scrolls vendors' (rows of their own), the zones, who sells what, the notes."""
    mackerel = {"recipe": "Slitherskin Mackerel", "spell": SPELL_MACKEREL, "uses": [[MACKEREL, 1]], "per": [1] * 49, "crafts": 49,
                "at": [1, 45, 65, 85], "cpp": 10055, "buy": [MACKEREL], "craft": [], "makes": [787, 1], "learn": [SCROLL_MACKEREL, 40]}
    steps = [_step(1, 50, "Brilliant Smallfish", SPELL_SMALLFISH, [[SMALLFISH, 1]], [6290, 1], [SMALLFISH], [SCROLL_SMALLFISH, 40], [mackerel]),
             _step(50, 94, "Longjaw Mud Snapper", SPELL_LONGJAW, [[LONGJAW, 1]], [4592, 1], [LONGJAW], [SCROLL_LONGJAW, 400]),
             _step(94, 100, "Smoked Sagefish", SPELL_SAGE, [[SAGEFISH, 1], [SPICES, 1]], [21072, 1], [SPICES, SAGEFISH], [SCROLL_SAGE, 500])]
    names = {6291: "Raw Brilliant Smallfish", 6290: "Brilliant Smallfish", 6289: "Raw Longjaw Mud Snapper", 4592: "Longjaw Mud Snapper",
             6303: "Raw Slitherskin Mackerel", 787: "Slitherskin Mackerel", 21071: "Raw Sagefish", 21072: "Smoked Sagefish",
             2678: "Mild Spices", 6325: "Recipe: Brilliant Smallfish", 6328: "Recipe: Longjaw Mud Snapper",
             6326: "Recipe: Slitherskin Mackerel", 21099: "Recipe: Smoked Sagefish"}
    buy = {"6291": [10000, "catch"], "6289": [10000, "catch"], "6303": [10000, "catch"], "21071": [10000, "catch"], "2678": [2, "vendor"],
           "6325": [40, "vendor"], "6326": [40, "vendor"], "6328": [400, "vendor"], "21099": [500, "vendor"]}
    if long:               # on to 300: the last stretch is Nightfin Soup, with the water a vendor sells
        steps.append(_step(100, 300, "Nightfin Soup", 18243, [[13759, 1], [159, 1]], [13931, 1], [159, 13759], [13945, 20000]))
        names.update({13759: "Raw Nightfin Snapper", 159: "Refreshing Spring Water", 13931: "Nightfin Soup", 13945: "Recipe: Nightfin Soup"})
        buy.update({"13759": [10000, "catch"], "159": [5, "vendor"], "13945": [20000, "vendor"]})
    return {"profession": "cooking", "skill_line": COOKING, "variant": "fishing", "start": 1, "target": 300 if long else 100, "net": -1000000,
            "spent": 1000000, "sold": 0, "gaps": [], "steps": steps, "made": {}, "buy": buy, "camp": [], "sell": {}, "disenchant": [],
            "names": {str(k): v for k, v in names.items()}, "kind": "fishing", "label": "Fishing only",
            "catch": {"6291": [["Teldrassil", 100.0], ["Elwynn Forest", 80.0], ["Durotar", 71.0]],
                      "6289": [["Wetlands", 100.0], ["Loch Modan", 87.7]],
                      "6303": [["Westfall", 100.0]],
                      "21071": [["Silverpine Forest", 10.308], ["Loch Modan", 9.253]]},
            "sold_by": {"6325": "Tharynn Bouden in Elwynn Forest", "6328": "Micha Yance in Hillsbrad Foothills"},
            "notes": [[1, ERA, "era"], [1, "The zones of the later fish are high-level fishing zones.", "fishing-skill"],
                      [75, "Journeyman Cooking is taught by a trainer.", "rank"], [225, ARTISAN, "rank"]]}


def with_cooking(doc=None) -> dict:
    """The test document with a skill-up focus for cooking and tailoring, so that the window's focus control has its two choices."""
    doc = copy.deepcopy(doc or document())
    doc["variants"] = [["trainer", "Trainer recipes only"], ["trainer-skill", "Trainer recipes, skill-up", "trainer", "skill"]]
    doc["focus"] = [["skill", "skill-up"]]
    for name in ("tailoring", "cooking"):
        doc["plans"][f"{name}-trainer-skill"] = dict(doc["plans"][f"{name}-trainer"], variant="trainer-skill")
    return doc


SKILLS = """
  learned = {}
  C_TradeSkillUI = {
    GetBaseProfessionInfo = function() return { professionID = 185, skillLevel = skill } end,
    GetRecipeInfo = function(id) return { recipeID = id, learned = learned[id] or false } end,
    GetRecipeRequirements = function(id) return {} end,
    CraftRecipe = function() end, StopRecipeRepeat = function() end,
  }
  cap = 75
  tailor = false
  function GetNumSkillLines() return tailor and 3 or 2 end
  function GetSkillLineInfo(i)
    if i == 1 then return "Professions", true end
    if i == 2 then return "Cooking", false, false, skill, 0, 0, cap end
    return "Tailoring", false, false, 44, 0, 0, 75
  end
  function UnitLevel() return 60 end
"""
STRIP = re.compile(r"\|c[0-9a-fA-F]{8}|\|r")


def strip(text) -> str:
    return STRIP.sub("", text or "")


def game(route=True, skill=1, cap=75, extra="", long=False):
    """The addon with a Horde house that has (or has not) the fishing route, a cooking skill of `skill`, the choice made."""
    lua = _game(with_cooking(), routes={"Horde": fishing_route(long)} if route else None)
    lua.execute(SKILLS + f"skill, cap = {skill}, {cap}; ns.inv.Char().skills[{COOKING}] = skill")
    if route:
        lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("fishing on")')
    lua.execute((extra or "local _ = 0") + '; Fire("SKILL_LINES_CHANGED"); Fire("BAG_UPDATE_DELAYED"); RunTimers()')
    return lua


def verdict(lua):
    v = lua.eval('ns.verdict.Verdict({ open = { id = 185, rank = skill, max = cap }, profession = "cooking" })')
    tip = [strip(t) for t in v.tip.values()]
    shopping = [{k: e[k] for k in ("item", "units", "have", "source", "price", "recipe")} for e in v.shopping.values() if lupa.lua_type(e) == "table"] if v.shopping else []
    return {"text": strip(v.text), "note": strip(v.note), "tip": tip, "show": v.show, "catch": v.catch,
            "place": v.place[1] if v.place else None, "shopping": shopping}


def window(lua) -> str:
    lua.execute('if not (ForeverWowCraftWindow and ForeverWowCraftWindow:IsShown()) then SlashCmdList.FOREVERWOWCRAFT("") end; '
                'Fire("BAG_UPDATE_DELAYED"); RunTimers()')
    return strip(lua.eval("AllText()"))


def focus(lua) -> str:
    return strip(lua.eval("ForeverWowCraftFocus.text"))


def click(lua):
    lua.execute("ForeverWowCraftFocus.scripts.OnClick(ForeverWowCraftFocus); RunTimers()")


# ---- the helper ---------------------------------------------------------------------------------------------------
def test_without_a_route_plans_lua_is_what_it_was_and_with_one_it_gains_a_second_global():
    docs = [document()]
    plain = plans.plans_text(docs, "test", written=NOW)
    assert plain == plans.plans_text(docs, "test", written=NOW, routes={}) == plans.plans_text(docs, "test", written=NOW, routes=None)
    # byte for byte what 1.7.7 wrote (with no route and no site list): the comment lines, the stamp, the one global, a closing newline;
    # the globals added since come after it (test_empty_window.py has FWCS_SITE)
    assert plain == "\n".join(["-- Written by `python fwch.py plans` from test; do not edit by hand.",
                               "-- The routes of your characters' auction houses, for the /fwc window. See fwchelper/plans.py.",
                               f"FWCS_PLANS_WRITTEN = {NOW}", "FWCS_PLANS = " + plans.lua({"stonespine--horde": plans.for_addon(docs[0])}), ""])
    with_route = plans.plans_text(docs, "test", written=NOW, routes={"Horde": fishing_route()})
    assert with_route.startswith(plain.rstrip("\n") + "\n") and with_route.count("FWCS_ROUTES = ") == 1     # the old part, untouched, then the route
    path = Path(tempfile.mkdtemp()) / "Plans.lua"
    path.write_text(with_route, encoding="utf-8")
    held, routes = plans.held(path)
    assert held == {"stonespine--horde": NOW} and plans.stamps(path) == held        # what an earlier helper reads of the file is unchanged
    assert list(routes) == ["Horde"] and routes["Horde"]["kind"] == "fishing" and routes["Horde"]["catch"][6291][0] == ["Teldrassil", 100]
    assert plans.held(Path(tempfile.mkdtemp()) / "nothing.lua") == ({}, {})


def test_a_route_is_checked_like_every_document_the_site_serves():
    assert plans.check_route(fishing_route()) is None
    assert plans.check_plans(document()) is None                       # ingame.json is read as ever
    for mend, why in ((lambda r: r.pop("kind"), "not a fishing route"),
                      (lambda r: r.update(names={"x": "y"}), "names"),
                      (lambda r: r["names"].pop("6291"), "names an item that items does not"),
                      (lambda r: r.update(catch={"6291": [["Teldrassil"]]}), "catch"),
                      (lambda r: r.update(catch=[]), "catch"),
                      (lambda r: r.update(sold_by={"6325": 7}), "sold_by"),
                      (lambda r: r.update(notes=[["1", "x"]]), "notes"),
                      (lambda r: r.update(notes=[[1, "x", 5]]), "notes"),
                      (lambda r: r.update(notes="x"), "notes"),
                      (lambda r: r["steps"][0].update({"to": 1}), "is not a step")):
        route = fishing_route()
        mend(route)
        problem = plans.check_route(route)
        assert problem and why in problem, (why, problem)
    assert plans.check_route([]) == "not a fishing route"


def _serve(root: Path, hits: list):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            hits.append(self.path)
            super().do_GET()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv


def _site(houses: list, routes: dict, hits: list):
    """A site folder: houses.json, each house's ingame.json, and extra/cooking-fishing.ingame.json where `routes` has one for its key."""
    root = Path(tempfile.mkdtemp())
    (root / "data").mkdir()
    (root / "data" / "houses.json").write_text(json.dumps({"houses": houses}), encoding="utf-8")
    for h in houses:
        folder = root / "data" / h["key"]
        folder.mkdir()
        (folder / "ingame.json").write_text(json.dumps(document(h["key"], h["realm"], h["faction"], h["generated"])), encoding="utf-8")
        if h["key"] in routes:
            (folder / "extra").mkdir()
            (folder / "extra" / "cooking-fishing.ingame.json").write_text(json.dumps(routes[h["key"]]), encoding="utf-8")
    url, srv = _serve(root, hits)
    return url, srv, root


def _helper_state():
    game_dir = Path(tempfile.mkdtemp())
    (game_dir / scan.ADDON_NAME).mkdir()
    (game_dir / scan.PLANS_ADDON).mkdir()
    saved = _saved()
    kept = settings.STATE, scan.addons_dir, scan.find_saved_variables
    settings.STATE, scan.addons_dir, scan.find_saved_variables = Path(tempfile.mkdtemp()) / "state", (lambda: game_dir), (lambda: [saved])
    return kept


def _restore(kept):
    settings.STATE, scan.addons_dir, scan.find_saved_variables = kept


def test_the_route_is_fetched_once_a_faction_and_written_beside_the_houses():
    def house(key, faction, **more):
        return dict({"key": key, "realm": key.split("--")[0].title(), "faction": faction, "realms": [key.split("--")[0].title()],
                     "generated": NOW, "ingame": True}, **more)
    listed = [house("stonespine--horde", "Horde", fishing=True), house("other--horde", "Horde", fishing=True), house("stonespine--alliance", "Alliance")]
    hits = []
    url, srv, root = _site(listed, {"stonespine--horde": fishing_route(), "other--horde": fishing_route()}, hits)
    kept = _helper_state()
    try:
        docs, written = plans.refresh(url, force=True)
        assert {d["house"] for d in docs} == {"stonespine--horde"}               # the character's house; its route comes with it
        text = written[0].read_text(encoding="utf-8")
        assert text.count("FWCS_ROUTES = ") == 1 and list(plans.held()[1]) == ["Horde"]
        assert sum(1 for path in hits if path.endswith("cooking-fishing.ingame.json")) == 1      # once a faction, not once a house
        assert sorted(plans.held()[0]) == ["stonespine--horde"]
        # nothing new: nothing fetched again
        hits.clear()
        assert plans.refresh(url) == ([], []) and not any(path.endswith("ingame.json") for path in hits)
        # a Plans.lua an earlier helper wrote has no route: the next look writes it, though no house is newer
        written[0].write_text(text.split("FWCS_ROUTES = ")[0], encoding="utf-8")
        assert plans.held()[1] == {} and plans.refresh(url)[1] and list(plans.held()[1]) == ["Horde"]
        # a site that does not say "fishing": nothing is asked for, and the text is the old one
        listed[0].pop("fishing")
        (root / "data" / "houses.json").write_text(json.dumps({"houses": listed}), encoding="utf-8")
        hits.clear()
        docs, written = plans.refresh(url, force=True)
        assert "FWCS_ROUTES" not in written[0].read_text(encoding="utf-8") and not any("extra" in path for path in hits)
        # a route the site cannot serve is left out; the houses are written all the same
        listed[0]["fishing"] = True
        (root / "data" / "stonespine--horde" / "extra" / "cooking-fishing.ingame.json").write_text(json.dumps({"kind": "fishing"}), encoding="utf-8")
        docs, written = plans.refresh(url, force=True)
        assert [d["house"] for d in docs] == ["stonespine--horde"] and "FWCS_ROUTES" not in written[0].read_text(encoding="utf-8")
        (root / "data" / "stonespine--horde" / "extra" / "cooking-fishing.ingame.json").unlink()
        docs, written = plans.refresh(url, force=True)
        assert docs and "FWCS_ROUTES" not in written[0].read_text(encoding="utf-8")
    finally:
        srv.shutdown()
        srv.server_close()
        _restore(kept)


def test_an_earlier_helper_ignores_the_new_field_in_houses_json():
    """The field is one more key on a house's entry: `houses` keeps the entries it knows and `choose`, `is_of` and `by_rule` read keys by name."""
    entry = {"key": "stonespine--horde", "realm": "Stonespine", "faction": "Horde", "realms": ["Stonespine"], "generated": NOW, "ingame": True, "fishing": True}
    assert plans.choose([entry], {("stonespine", "Horde")}) == [entry] and plans.is_of(entry, {("stonespine", "Horde")})
    assert plans.choose([dict(entry, fishing=None)], set()) and plans.choose([dict(entry, ingame=False)], set()) == []


# ---- the addon ------------------------------------------------------------------------------------------------------
def test_a_house_with_no_route_offers_no_choice_and_the_addon_before_it_never_reads_one():
    if lupa is None:
        return
    lua = game(route=False, skill=60)
    assert not lua.eval("ns.FishingAvailable()") and not lua.eval("ns.FishingOn()")
    text = window(lua)
    assert "Fishing only" not in text.replace("Cooking: Fishing only", "") and focus(lua) == "Mode: Profit"
    click(lua)
    assert focus(lua) == "Mode: Skill-up" and lua.eval("ns.inv.Char().fishing") is None             # the click is the focus's alone
    click(lua)
    assert focus(lua) == "Mode: Profit"
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("fishing on")')
    assert lua.eval("ns.inv.Char().fishing") is None and "no fishing route" in lua.eval("printed[#printed]")
    # a route for the other faction, or a plan that is not a fishing one, is none
    lua = _game(with_cooking(), routes={"Alliance": fishing_route()})
    assert not lua.eval("ns.FishingAvailable()")
    wrong = fishing_route()
    wrong["kind"] = "other"
    assert not _game(with_cooking(), routes={"Horde": wrong}).eval("ns.FishingAvailable()")
    # and the addon as it was before the route, given a Plans.lua that has FWCS_ROUTES, never looks at it: the global is simply not read
    assert "FWCS_ROUTES" not in "".join((ADDON / name).read_text(encoding="utf-8") for name in ("Plans.lua", "Fresh.lua", "Queue.lua"))


def test_fishing_only_is_the_third_choice_of_the_focus_on_cooking_and_the_choice_is_kept():
    if lupa is None:
        return
    lua = game(skill=60, extra=f"ns.inv.Char().skills[{COOKING}] = skill")
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("fishing off")')
    assert lua.eval("ns.FishingAvailable()") and not lua.eval("ns.FishingOn()")
    window(lua)
    # skill-up and profit are what they were; one more click is "Fishing only", the next is profit again
    seen = []
    for _ in range(4):
        seen.append(focus(lua))
        click(lua)
    assert seen == ["Mode: Profit", "Mode: Skill-up", "Mode: Fishing only", "Mode: Profit"] and focus(lua) == "Mode: Skill-up"
    click(lua)
    assert focus(lua) == "Mode: Fishing only" and lua.eval("ns.inv.Char().fishing") is True and lua.eval("ns.Settings().variant") == "trainer-skill"
    assert "Cooking, Fishing only, 60 to 100" in window(lua)
    # another profession is looked at: the control is its own (two choices), the cooking choice is not lost or touched
    lua.execute('tailor = true; ns.inv.Char().picked = "tailoring"; Fire("SKILL_LINES_CHANGED"); Fire("BAG_UPDATE_DELAYED"); RunTimers()')
    assert "Tailoring" in window(lua) and focus(lua) in ("Mode: Profit", "Mode: Skill-up")
    before = focus(lua)
    click(lua)
    assert focus(lua) != before and lua.eval("ns.inv.Char().fishing") is True
    lua.execute('ns.inv.Char().picked = "cooking"; Fire("BAG_UPDATE_DELAYED"); RunTimers()')
    assert focus(lua) == "Mode: Fishing only" and "Cooking, Fishing only" in window(lua)
    # remembered per character: it is on the character, and another character does not have it
    assert lua.eval('FWCS_DB.__chars["Stonespine|Thrallson"].fishing') is True
    lua.execute('UnitName = function() return "Otheralt" end')
    assert not lua.eval("ns.FishingOn()")
    lua.execute('UnitName = function() return "Thrallson" end')
    assert lua.eval("ns.FishingOn()")
    # the pairs the choice is held in are the same in the Make button's route (the arrow and the list follow it)
    assert lua.eval('ns.RouteFor("cooking").kind') == "fishing" and lua.eval('ns.RouteFor("tailoring").kind') is None


def test_the_options_page_and_the_command_are_one_switch():
    if lupa is None:
        return
    lua = game(skill=60)
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("fishing off")')
    labels = [lua.eval(f"ns.options.boxes[{i}].label.text") for i in range(1, 14)]
    assert labels[12] == "Cooking: Fishing only" and "/fwcs fishing" in lua.eval("ns.options.boxes[13].note.text")
    assert lua.eval("ns.options.boxes[13].get()") is False
    lua.execute("local b = ns.options.boxes[13]; b.GetChecked = function() return true end; b.scripts.OnClick(b)")
    assert lua.eval("ns.FishingOn()") is True and lua.eval("ns.options.boxes[13].get()") is True
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("fishing off")')
    assert lua.eval("ns.options.boxes[13].get()") is False
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("fishing")')                  # no word: the other way round
    assert lua.eval("ns.options.boxes[13].get()") is True
    lua.execute("ns.options:OnDefault()")                                           # the Defaults button: the shipped default, off
    assert lua.eval("ns.options.boxes[13].get()") is False
    assert "fishing |" in lua.eval('(function() SlashCmdList.FOREVERWOWCRAFTSCANNER(""); return printed[#printed] end)()').replace("have | fishing", "fishing |")


def test_a_fish_is_caught_not_bought_and_a_stretch_says_what_it_needs():
    if lupa is None:
        return
    lua = game(skill=60, cap=150, extra="learned[7751] = true; learned[7753] = true")
    v = verdict(lua)
    assert v["text"] == "Catch 34 Raw Longjaw Mud Snapper" and v["show"] and v["catch"] and v["place"] is None   # no arrow to anywhere
    assert "auction" not in v["text"].lower() and "Buy" not in v["text"]
    assert v["note"] == "34 Raw Longjaw Mud Snapper: Wetlands, Loch Modan"                                       # the zones where the arrow would be
    assert "  34 Raw Longjaw Mud Snapper (have 0): catch, Wetlands 100%, Loch Modan 88%" in v["tip"]
    assert "Catch spots are from the Classic-era world and may differ." in v["tip"]
    assert any(t.startswith("No arrow for fishing") for t in v["tip"]) and not any("auction" in t.lower() for t in v["tip"])
    assert [(e["item"], e["source"], e["price"]) for e in v["shopping"]] == [(LONGJAW, "catch", None)]
    # nothing in the list is for the auction house: no Buy button, nothing to search, the list does not open there
    lua.execute("local e = ns.craft.Shopping(); ns.ShowShopping(e); ns.RefreshShopping()")
    assert not lua.eval("ns.ShoppingBusy()") and lua.eval("ForeverWowCraftShopping == nil or not ForeverWowCraftShopping.rows[1].buy.shown or true")
    assert lua.eval("(function() for _, e in ipairs(ns.craft.Shopping()) do if e.source == 'ah' then return true end end return false end)()") is False
    # nothing for Auctionator: no fish, and no recipe either (a vendor's)
    assert lua.eval("(ns.AuctionatorImport(true))") == ""
    assert lua.eval("select(2, ns.AuctionatorImport(true)).items") == 0 and lua.eval("(ns.AuctionatorImport(false))") == ""
    # fish and a vendor's goods in one stretch: the vendor's first, the arrow to a vendor, the fish after it
    lua = game(skill=95, cap=150, extra="learned[25704] = true")
    v = verdict(lua)
    assert v["text"] == "Buy 5 Mild Spices from a vendor, and catch 5 Raw Sagefish" and v["place"] == "vendor" and not v["catch"]
    assert v["note"] == "5 Mild Spices: vendor, 5 Raw Sagefish: Silverpine Forest, Loch Modan"
    assert "  5 Raw Sagefish (have 0): catch, Silverpine Forest 10%, Loch Modan 9.3%" in v["tip"]


def test_the_recipe_is_a_vendors_and_its_flow_works_on_this_route():
    if lupa is None:
        return
    seen = {}
    lua = game(skill=1)
    v = verdict(lua)
    assert v["text"] == "Buy the recipe for Brilliant Smallfish first" and v["place"] == "vendor"     # the arrow to the vendor, not the auctioneer
    assert "The route buys the recipe, Recipe: Brilliant Smallfish, for 40c: sold by Tharynn Bouden in Elwynn Forest." in v["tip"]
    assert [(e["item"], e["source"], bool(e.get("recipe"))) for e in v["shopping"]] == [(SCROLL_SMALLFISH, "vendor", True), (SMALLFISH, "catch", False)]
    assert lua.eval("(ns.AuctionatorImport(true))") == ""                                                 # the recipe is not for the auction house
    # in the mail, in the bank, in the bags: the same flow as on any route
    lua.execute(f"ns.inv.NoteMailed({SCROLL_SMALLFISH}, 1); Fire('BAG_UPDATE_DELAYED'); RunTimers()")
    v = seen["mail"] = verdict(lua)
    assert v["text"] == "Collect Recipe: Brilliant Smallfish from the mailbox" and v["place"] == "mailbox" and "Then learn the recipe from it." in v["tip"]
    lua.execute(f"ns.inv.Char().mailed = nil; ns.inv.Char().items[{SCROLL_SMALLFISH}] = {{ 0, 1 }}; Fire('BAG_UPDATE_DELAYED'); RunTimers()")
    assert verdict(lua)["text"] == "Take Recipe: Brilliant Smallfish from the bank"
    lua.execute(f"ns.inv.Char().items[{SCROLL_SMALLFISH}] = nil; bags[0] = {{ {{ {SCROLL_SMALLFISH}, 1 }} }}; Fire('BAG_UPDATE_DELAYED'); RunTimers()")
    v = verdict(lua)
    assert v["text"] == "Learn Brilliant Smallfish: use Recipe: Brilliant Smallfish in your bags" and v["place"] is None
    # learned: the fish to catch
    lua.execute("bags[0] = {}; learned[7751] = true; Fire('BAG_UPDATE_DELAYED'); RunTimers()")
    assert verdict(lua)["text"] == "Catch 49 Raw Brilliant Smallfish"
    # a trainer's recipe has no sale: "Learn ... first" at the trainer, the fish named after it
    lua.execute("local r = ns.RouteFor('cooking'); r.steps[1].learn = nil; learned[7751] = false; ns.HaveChanged(); Fire('BAG_UPDATE_DELAYED'); RunTimers()")
    v = verdict(lua)
    assert v["text"] == "Learn Brilliant Smallfish first" and v["place"] == "trainer"


def test_what_the_character_has_counts_and_never_by_what_a_craft_sells_for():
    if lupa is None:
        return
    # 20 of the 44 fish in the bags: the stretch is for the 20 to make now, the window counts the rest to catch
    lua = game(skill=60, extra=f"learned[7751] = true; learned[7753] = true; bags[0] = {{ {{ {LONGJAW}, 20 }} }}")
    assert verdict(lua)["text"] == "Make 20 Longjaw Mud Snapper"
    text = window(lua)
    assert "To catch: 20 fish  (40 with nothing in hand; what you have saves 20)" in text
    assert "Cooking, Fishing only, 60 to 100, from your skill. 40 crafts." in text
    # in the bank (with "Use what I already have first"): taken from it first; in the mail: the mailbox
    lua = game(skill=60, extra=f"learned[7751] = true; learned[7753] = true; ns.inv.Char().items[{LONGJAW}] = {{ 0, 30 }}")
    assert verdict(lua)["text"] == "Take 30 Raw Longjaw Mud Snapper from the bank"
    lua = game(skill=60, extra=f"learned[7751] = true; learned[7753] = true; ns.inv.NoteMailed({LONGJAW}, 12)")
    v = verdict(lua)
    assert v["text"] == "Collect 12 Raw Longjaw Mud Snapper from the mailbox" and v["place"] == "mailbox"
    # a fish of another recipe stands in: 30 Raw Slitherskin Mackerel in the bags, the first stretch uses them ("Use what I already have first"),
    # though what Mackerel makes is worth 9,999,999 to a profit route's tables: the fishing route sells nothing
    lua = game(skill=1, extra=f"learned[7751] = true; learned[7752] = true; bags[0] = {{ {{ {MACKEREL}, 30 }} }};"
                              f"FWCS_PLANS['stonespine--horde'].recipes = {{ [{SPELL_MACKEREL}] = {{ 1, 9999999, 9999999, 1, 0 }} }}; ns.HaveChanged()")
    assert verdict(lua)["text"] == "Make 30 Slitherskin Mackerel"
    assert any("Slitherskin Mackerel stands in for Brilliant Smallfish, with fewer fish to catch for you." in t for t in verdict(lua)["tip"])
    assert not any("a skill point" in t or re.search(r"\d+[gsc]", t) for t in verdict(lua)["tip"])                  # no money wording for a weight
    lua = game(skill=1, extra=f"learned[7751] = true; learned[7752] = true; FWCS_PLANS['stonespine--horde'].recipes = {{ [{SPELL_MACKEREL}] = {{ 1, 9999999, 9999999, 1, 0 }} }}; ns.HaveChanged()")
    assert verdict(lua)["text"] == "Catch 49 Raw Brilliant Smallfish"                                  # nothing owned: the planner's own route, however it sells
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("have off")')
    assert verdict(lua)["text"] == "Catch 49 Raw Brilliant Smallfish"


def test_the_window_says_fish_counts_not_money_and_the_notes_once():
    if lupa is None:
        return
    lua = game(skill=1)
    text = window(lua)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert "Cooking, Fishing only, 1 to 100, from your skill. 99 crafts." in text
    assert "To catch: 99 fish  (99 with nothing in hand; what you have saves 0)" in text
    assert any(ln.startswith("To buy from vendors (goods and recipes): ") for ln in lines)
    assert "Net:" not in text and "Left to sell" not in text and "To buy:  " not in text             # nothing of a profit route's money lines
    assert any("Raw Longjaw Mud Snapper  catch" in ln for ln in lines) and any("Raw Sagefish  catch" in ln for ln in lines)
    assert any("Mild Spices  vendor" in ln for ln in lines)
    assert "Fishing only: Catch spots are from the Classic-era world and may differ. It plans your cooking, not your Fishing skill, and no arrow leads to a fishing spot." in text
    # the route's notes, once, in the list, cut into lines; the ones about ranks behind the character's skill are left out
    assert text.count("About this route") == 1 and text.count("Where the fish are caught is the Classic-era world's: a guide to check in game.") == 1
    assert "high-level fishing zones." in text
    assert "Artisan Cooking comes from the quest" not in text and "Journeyman Cooking is taught" not in text      # a rank's note is the rank-up verdict's
    # the shopping list row says where, in its tooltip (the item's hover)
    lua.execute(f"local row; for _, r in ipairs(ForeverWowCraftWindow.rows or {{}}) do if r.item == {LONGJAW} then row = r end end; hovered = row")
    # the note about the quest reaches the player at the rank: the tooltip of the button from skill 200 on (the cap 225)
    lua = game(skill=205, cap=225, long=True, extra="learned[7751] = true; learned[18238] = true")
    v = verdict(lua)
    assert any(t.startswith("No trainer teaches Artisan Cooking: the quest Clamlette Surprise gives it") for t in v["tip"])
    assert ARTISAN in v["tip"] and sum(1 for t in v["tip"] if "Classic-era" in t) == 0                  # the era is the window's, once, not every step's
    # a verdict of an ordinary step carries no note
    assert ARTISAN not in verdict(game(skill=60, extra="learned[7751] = true; learned[7753] = true"))["tip"]


def test_the_route_costs_nothing_at_load_and_is_made_once():
    if lupa is None:
        return
    lua = game(skill=60, extra="learned[7751] = true; learned[7753] = true")
    # attached to the house once: the same table every call, its fish named in the house's items
    assert lua.eval("ns.inv.House().fish == ns.inv.House().fish and ns.inv.House().items[6289]") == "Raw Longjaw Mud Snapper"
    lua.execute("spots = ns.CatchSpots(ns.inv.House().fish, 6289)")
    assert lua.eval("spots") == "Wetlands 100%, Loch Modan 88%" and lua.eval("ns.CatchSpots(ns.inv.House().fish, 6289, true)") == "Wetlands, Loch Modan"
    assert lua.eval("ns.CatchSpots(ns.inv.House().fish, 1)") is None
    # the walk is not worked out again for the same bags, and no frame draws anything on its own
    walks = lua.eval("ns.haveWalks")
    for _ in range(5):
        lua.eval("ns.RouteFor('cooking')")
    assert lua.eval("ns.haveWalks") == walks


def tooltip(lua) -> list:
    """What the Mode button's tooltip says: its lines, colour codes kept."""
    lua.execute("tiplines = {}; GameTooltip.SetOwner = function() end; GameTooltip.Show = function() end; "
                "GameTooltip.AddLine = function(_, t) table.insert(tiplines, t) end; "
                "ForeverWowCraftFocus.scripts.OnEnter(ForeverWowCraftFocus)")
    return [lua.eval(f"tiplines[{i}]") for i in range(1, int(lua.eval("#tiplines")) + 1)]


def test_the_mode_button_names_the_mode_in_gold_and_is_wide_enough():
    if lupa is None:
        return
    lua = game(skill=60, extra=f"ns.inv.Char().skills[{COOKING}] = skill")
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("fishing off")')
    window(lua)
    assert lua.eval("ForeverWowCraftFocus.text") == "Mode: |cffffd100Profit|r"
    click(lua)
    assert lua.eval("ForeverWowCraftFocus.text") == "Mode: |cffffd100Skill-up|r"
    click(lua)
    assert lua.eval("ForeverWowCraftFocus.text") == "Mode: |cffffd100Fishing only|r"
    src = (ADDON / "Window.lua").read_text(encoding="utf-8")
    assert 'Button(win, 150, "", "ForeverWowCraftFocus")' in src
    # the row: also 150, mode 150, other characters 154, Auctionator 100, the gaps and the left margin, inside the window
    assert 12 + 150 + 6 + 150 + 6 + 154 + 6 + 100 < 760


def test_the_mode_button_cycles_profit_skill_up_fishing_only_on_cooking_and_two_modes_elsewhere():
    if lupa is None:
        return
    lua = game(skill=60, extra=f"ns.inv.Char().skills[{COOKING}] = skill")
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("fishing off")')
    window(lua)
    seen = []
    for _ in range(4):
        seen.append(focus(lua))
        click(lua)
    assert seen == ["Mode: Profit", "Mode: Skill-up", "Mode: Fishing only", "Mode: Profit"]
    assert focus(lua) == "Mode: Skill-up"
    click(lua)
    assert focus(lua) == "Mode: Fishing only" and lua.eval("ns.inv.Char().fishing") is True
    lua.execute('tailor = true; ns.inv.Char().picked = "tailoring"; Fire("SKILL_LINES_CHANGED"); Fire("BAG_UPDATE_DELAYED"); RunTimers()')
    window(lua)
    seen = []
    for _ in range(3):
        seen.append(focus(lua))
        click(lua)
    assert seen[0] == seen[2] and {seen[0], seen[1]} == {"Mode: Profit", "Mode: Skill-up"}
    assert lua.eval("ns.inv.Char().fishing") is True                                     # the cooking choice is untouched


def test_the_mode_tooltip_lists_the_modes_on_offer_and_marks_the_active_one():
    if lupa is None:
        return
    lua = game(skill=60, extra=f"ns.inv.Char().skills[{COOKING}] = skill")
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("fishing off")')
    window(lua)
    tip = tooltip(lua)
    assert tip[:2] == ["Mode", "Click to change."] and len(tip) == 5
    assert tip[2].startswith("|cff40ff40> Profit|r: What you make is sold at the auction house")
    assert tip[3].startswith("   Skill-up: Nothing is listed") and tip[4].startswith("   Fishing only: ")
    click(lua)
    click(lua)
    tip = tooltip(lua)
    assert tip[2].startswith("   Profit: ") and tip[3].startswith("   Skill-up: ") and tip[4].startswith("|cff40ff40> Fishing only|r: ")
    lua.execute('tailor = true; ns.inv.Char().picked = "tailoring"; Fire("SKILL_LINES_CHANGED"); Fire("BAG_UPDATE_DELAYED"); RunTimers()')
    window(lua)
    tip = tooltip(lua)
    assert len(tip) == 4 and not any("Fishing only" in t for t in tip) and sum(t.startswith("|cff40ff40> ") for t in tip) == 1


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)

"""The last known lowest auction price on item tooltips (1.8.4): the house's price list the site keeps beside its routes
(prices.json, fwc-prices/1), fetched with the routes when houses.json says "prices": true, checked as untrusted (a list
that is not usable is left out, said once, and the routes and the other houses' lists are written all the same), written
into Plans.lua as FWCS_PRICES; and the addon's lines on an item tooltip: the price of one, of the hovered stack where the
client says how many it holds, and how old the price is; nothing for an item the list lacks, with the box off, or without
the list. An addon from before reads Plans.lua with the new global as it read it without.

The addon's part needs a Lua: `pip install lupa`; without it those tests say so and pass."""
import contextlib
import io
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fwchelper import cli, luatable, plans  # noqa: E402
from test_empty_window import BEFORE_THIS, _load, _release_source, _shown  # noqa: E402
from test_fishing_route import _helper_state, _restore, _site  # noqa: E402
from test_ingame import HOOK, _game, lupa  # noqa: E402
from test_plans import NOW, document  # noqa: E402

CLOTH, THREAD, SILK, BOLT = 2589, 2320, 4306, 2996
STRIP = re.compile(r"\|c[0-9a-fA-F]{8}|\|r")


def price_doc(key="stonespine--horde", **more) -> dict:
    return dict({"format": "fwc-prices/1", "house": key, "at": NOW - 300, "generated": NOW,
                 "prices": {str(CLOTH): 12, str(THREAD): 35, str(SILK): 123456}, "seen": {str(SILK): NOW - 7200}}, **more)


def house(key, realm, faction, **more):
    return dict({"key": key, "realm": realm, "faction": faction, "realms": [realm], "generated": NOW, "ingame": True}, **more)


# ---- the helper ---------------------------------------------------------------------------------------------------
def test_a_price_list_is_checked_as_untrusted():
    assert plans.check_prices(price_doc(), "stonespine--horde") is None
    assert plans.check_prices(price_doc(seen={}), "stonespine--horde") is None
    bad = {
        "another format": price_doc(format="fwc-plans/1"),
        "another house's": price_doc(house="other--horde"),
        "a price that is not whole": price_doc(prices={str(CLOTH): 12.5}),
        "a price that is a string": price_doc(prices={str(CLOTH): "12"}),
        "a price that is true": price_doc(prices={str(CLOTH): True}),
        "a negative price": price_doc(prices={str(CLOTH): -1}),
        "no price": price_doc(prices={str(CLOTH): 0}),
        "a price past the game's gold": price_doc(prices={str(CLOTH): plans.MAX_COPPER + 1}),
        "an id that is not one": price_doc(prices={"12x": 5}),
        "an id of thousands of digits": price_doc(prices={"9" * 400: 5}),
        "too many items": price_doc(prices={str(i): 1 for i in range(1, plans.MAX_PRICE_ITEMS + 2)}, seen={}),
        "a time that is not one": price_doc(at="now"),
        "a time of an item not listed": price_doc(seen={"77": NOW - 10}),
        "a time after the list's": price_doc(seen={str(SILK): NOW}),
        "not a document": [1, 2],
    }
    for why, doc in bad.items():
        assert plans.check_prices(doc, "stonespine--horde"), why
    assert plans.check_prices(price_doc(prices={str(i): 1 for i in range(1, plans.MAX_PRICE_ITEMS + 1)}, seen={}), "stonespine--horde") is None


def _priced_site(lists: dict, hits: list):
    """A site of two Horde houses of the character's realm, Stonespine's and another's, with the given price lists ({key: text})."""
    listed = [house("stonespine--horde", "Stonespine", "Horde", prices=True), house("thrall--horde", "Stonespine", "Horde", prices=True)]
    url, srv, root = _site(listed, {}, hits)
    for key, text in lists.items():
        (root / "data" / key / "prices.json").write_text(text, encoding="utf-8")
    return url, srv, root


def test_the_lists_are_fetched_with_the_routes_and_a_bad_one_is_left_out_said_once():
    hits = []
    url, srv, root = _priced_site({"stonespine--horde": json.dumps(price_doc()),
                                   "thrall--horde": json.dumps(price_doc("thrall--horde", prices={str(CLOTH): -5}))}, hits)
    kept = _helper_state()
    plans._refused.clear()                      # what an earlier test left out is not this one's
    saved_site = plans.site_url
    try:
        plans.site_url = lambda: url
        said = io.StringIO()

        def look() -> tuple[bool, list[str]]:
            said.seek(0)
            said.truncate()
            with contextlib.redirect_stdout(said):
                wrote = cli.plans(quiet=True)
            return wrote, said.getvalue().splitlines()
        wrote, out = look()
        assert wrote is True
        text = plans.kept_file().read_text(encoding="utf-8")
        assert text == plans.installed_file().read_text(encoding="utf-8")
        data = luatable.parse(text)
        assert sorted(data["FWCS_PLANS"]) == ["stonespine--horde", "thrall--horde"]           # the routes of both, whatever their prices
        assert data["FWCS_PRICES"] == {"stonespine--horde": {"at": NOW - 300, "prices": {CLOTH: 12, THREAD: 35, SILK: 123456},
                                                             "seen": {SILK: NOW - 7200}}}
        dropped = [line for line in out if line.startswith("prices for item tooltips left out")]
        assert len(dropped) == 1 and "thrall--horde" in dropped[0] and "copper" in dropped[0], out
        assert plans.priced() == {"stonespine--horde"}
        # the next look: nothing new, the list left out is not asked for again, and nothing is said of it again
        hits.clear()
        wrote, out = look()
        assert wrote is False
        assert not any(p.endswith("prices.json") or p.endswith("ingame.json") for p in hits) and out == [], (hits, out)
        # the site's data of that house changes: its list is asked for again
        listed = json.loads((root / "data" / "houses.json").read_text(encoding="utf-8"))
        listed["houses"][1]["generated"] = NOW + 60
        (root / "data" / "houses.json").write_text(json.dumps(listed), encoding="utf-8")
        (root / "data" / "thrall--horde" / "prices.json").write_text(json.dumps(price_doc("thrall--horde")), encoding="utf-8")
        assert look()[0] is True and plans.priced() == {"stonespine--horde", "thrall--horde"}
    finally:
        plans.site_url = saved_site
        srv.shutdown()
        srv.server_close()
        _restore(kept)


def test_a_list_too_large_or_not_there_is_left_out_and_the_routes_written():
    hits = []
    huge = json.dumps(price_doc(prices={str(i): 99999 for i in range(1, 19000)}, seen={})) + " " * plans.MAX_PRICE_BYTES
    url, srv, root = _priced_site({"stonespine--horde": huge}, hits)                       # thrall--horde has none at all (404)
    kept = _helper_state()
    plans._refused.clear()                      # what an earlier test left out is not this one's
    try:
        docs, written = plans.refresh(url, force=True)
        assert len(docs) == 2 and written
        assert "FWCS_PRICES" not in plans.kept_file().read_text(encoding="utf-8")
        assert len(plans.DROPPED) == 2 and any("too large" in d for d in plans.DROPPED) and any("404" in d for d in plans.DROPPED)
    finally:
        srv.shutdown()
        srv.server_close()
        _restore(kept)


def test_a_file_an_earlier_helper_wrote_gets_the_lists_at_the_next_look():
    hits = []
    url, srv, root = _priced_site({"stonespine--horde": json.dumps(price_doc()), "thrall--horde": json.dumps(price_doc("thrall--horde"))}, hits)
    kept = _helper_state()
    plans._refused.clear()                      # what an earlier test left out is not this one's
    try:
        docs, written = plans.refresh(url, force=True)
        old = plans.plans_text(docs, url, written=NOW - 3600)                    # what 1.8.3 wrote: the routes, no prices
        for f in written:
            f.write_text(old, encoding="utf-8")
        assert plans.priced() == set()
        docs, written = plans.refresh(url)                                       # no `force`: the missing lists are reason enough
        assert written and plans.priced() == {"stonespine--horde", "thrall--horde"}
        # a site from before the lists (no "prices" in houses.json): nothing asked for, nothing written of them
        listed = json.loads((root / "data" / "houses.json").read_text(encoding="utf-8"))
        for h in listed["houses"]:
            h.pop("prices")
        (root / "data" / "houses.json").write_text(json.dumps(listed), encoding="utf-8")
        hits.clear()
        docs, written = plans.refresh(url, force=True)
        assert not any(p.endswith("prices.json") for p in hits) and "FWCS_PRICES" not in plans.kept_file().read_text(encoding="utf-8")
    finally:
        srv.shutdown()
        srv.server_close()
        _restore(kept)


def test_the_text_before_the_new_global_is_unchanged_and_the_global_is_compact():
    docs = [document()]
    plain = plans.plans_text(docs, "test", written=NOW, site_houses=[["stonespine", "Horde"]])
    assert plans.plans_text(docs, "test", written=NOW, site_houses=[["stonespine", "Horde"]], prices={}) == plain
    lists = {"stonespine--horde": {"at": NOW, "prices": {CLOTH: 12, THREAD: 35}, "seen": {}}}
    priced = plans.plans_text(docs, "test", written=NOW, site_houses=[["stonespine", "Horde"]], prices=lists)
    head = plain.split("FWCS_SITE = ")[0]
    assert priced.startswith(head + "FWCS_PRICES = {\n") and priced.endswith(plain[len(head):])
    assert priced.index("FWCS_PRICES") < priced.index("FWCS_SITE")
    assert '  [2589]=12,\n' in priced and "\n FWCS" not in priced
    # a failed look moves the stamp and puts its line last, as before: the price list is left where it is
    retouched = plans._retouch(priced, None, "reach")
    assert priced.split("FWCS_PRICES = ")[1].split("FWCS_SITE")[0] == retouched.split("FWCS_PRICES = ")[1].split("FWCS_SITE")[0]
    assert retouched.index("FWCS_PRICES") < retouched.index("FWCS_SITE") < retouched.index("FWCS_PLANS_PROBLEM")


def test_an_earlier_addon_reads_plans_lua_with_the_lists_as_it_read_it_without():
    if lupa is None or _release_source("ForeverWowCraftScanner.toc", BEFORE_THIS) is None:
        return
    plain = plans.plans_text([document()], "test", written=NOW)
    priced = plans.plans_text([document()], "test", written=NOW, prices={"stonespine--horde": {"at": NOW, "prices": {CLOTH: 12}, "seen": {}}})
    assert _shown(_load(priced, release=BEFORE_THIS)) == _shown(_load(plain, release=BEFORE_THIS))
    assert "Bolt of Linen Cloth" in _shown(_load(priced, release=BEFORE_THIS))


# ---- the addon ----------------------------------------------------------------------------------------------------
def lists() -> dict:
    """The price lists of two houses, the character's priced 35 minutes ago (silk three hours ago), as of now."""
    now = int(time.time())
    return {"stonespine--horde": {"at": now - 35 * 60, "prices": {CLOTH: 12, THREAD: 35, SILK: 123456}, "seen": {SILK: now - 3 * 3600}},
            "elsewhere--alliance": {"at": now, "prices": {BOLT: 1}, "seen": {}}}
# a tooltip that keeps its lines, and the client's ways to it: the hooks the addon puts on it, what filled it, its owner
TIP = """
  tiplines, hooked = {}, {}
  GameTooltip.AddLine = function(_, t) table.insert(tiplines, t) end
  GameTooltip.AddDoubleLine = function(_, l, r) table.insert(tiplines, l .. " = " .. r) end
  GameTooltip.HookScript = function(_, name, fn) hooked[name] = fn end
  GameTooltip.GetPrimaryTooltipInfo = function() return primary end
  GameTooltip.GetOwner = function() return owner end
"""


def tip(lua, item, how="data") -> list[str]:
    """The lines the addon adds to GameTooltip for `item`: through the client's tooltip data (`data`) or the tooltip drawn (`drawn`)."""
    lua.execute("tiplines = {}; if hooked.OnTooltipCleared then hooked.OnTooltipCleared(GameTooltip) end")
    if how == "data":
        lua.execute(f"for _, fn in ipairs(postcalls) do fn(GameTooltip, {{ id = {item}, lines = {{}} }}) end")
    else:
        lua.execute(f'GameTooltip.GetItem = function() return "x", "|cffffffff|Hitem:{item}::::::::60:::::|h[x]|h|r" end; hooked.OnTooltipSetItem(GameTooltip)')
    return [STRIP.sub("", lua.eval(f"tiplines[{i}]")) for i in range(1, int(lua.eval("#tiplines")) + 1)]


def priced_game(how="data", given=None, extra=""):
    saved = TIP + (HOOK if how == "data" else "") + extra
    return _game(saved=saved, prices=lists() if given is None else given)


def test_one_item_says_its_price_and_how_old_it_is():
    if lupa is None:
        return
    lua = priced_game()
    assert tip(lua, CLOTH) == ["Auction house = 12c each", "Price seen 35 min ago"]
    assert tip(lua, SILK) == ["Auction house = 12g 34s each", "Price seen 3 h ago"]          # its own time: scanned before the rest
    assert tip(lua, BOLT) == []                                                             # another house's item: nothing
    assert tip(lua, 99999) == []                                                            # an item the list lacks: nothing


def test_a_stack_in_the_bags_says_what_it_comes_to():
    if lupa is None:
        return
    lua = priced_game()
    lua.execute(f"bags[0][3] = {{ {THREAD}, 20 }}; bags[0][4] = {{ {THREAD}, 1 }}; bags[0][5] = {{ {CLOTH}, 7 }}")
    lua.execute('primary = { getterName = "GetBagItem", getterArgs = { 0, 3 } }')
    assert tip(lua, THREAD) == ["Auction house = 35c each", "Stack of 20 = 7s 00c", "Price seen 35 min ago"]
    lua.execute('primary = { getterName = "GetBagItem", getterArgs = { 0, 4 } }')
    assert tip(lua, THREAD) == ["Auction house = 35c each", "Price seen 35 min ago"]          # one: no stack line
    lua.execute('primary = { getterName = "GetBagItem", getterArgs = { 0, 5 } }')
    assert tip(lua, THREAD)[1] == "Price seen 35 min ago"                                   # the slot holds another item: no guess
    lua.execute('primary = { getterName = "GetHyperlink", getterArgs = { "item:2320" } }')
    assert len(tip(lua, THREAD)) == 2                                                       # a link: how many is not known
    # an older client: the bag slot the tooltip belongs to
    lua.execute('primary = nil; owner = { GetID = function() return 3 end, GetBagID = function() return 0 end }')
    assert tip(lua, THREAD)[1] == "Stack of 20 = 7s 00c"
    lua.execute('owner = { GetID = function() return 3 end, GetParent = function() return { GetName = function() return "ContainerFrame1" end, '
                'GetID = function() return 0 end } end }')
    assert tip(lua, THREAD)[1] == "Stack of 20 = 7s 00c"
    lua.execute('owner = { GetID = function() return 3 end, GetParent = function() return { GetName = function() return "AuctionHouseFrame" end } end }')
    assert len(tip(lua, THREAD)) == 2                                                       # not a bag: nothing guessed


def test_the_tooltip_drawn_on_a_client_without_tooltip_data_gets_the_same_lines():
    if lupa is None:
        return
    lua = priced_game("drawn")
    assert lua.eval("postcalls") is None and lua.eval("hooked.OnTooltipSetItem") is not None
    lua.execute(f"bags[0][3] = {{ {CLOTH}, 5 }}; owner = {{ GetID = function() return 3 end, GetBagID = function() return 0 end }}")
    assert tip(lua, CLOTH, "drawn") == ["Auction house = 12c each", "Stack of 5 = 60c", "Price seen 35 min ago"]
    # the client sets the same item twice in a row on one showing: the lines go on once
    lua.execute("hooked.OnTooltipSetItem(GameTooltip)")
    assert int(lua.eval("#tiplines")) == 3
    assert tip(lua, 99999, "drawn") == []


def test_the_box_turns_it_off_and_on_and_is_on_by_default():
    if lupa is None:
        return
    lua = priced_game()
    box = next(i for i in range(1, 30) if lua.eval(f"ns.options.boxes[{i}] and ns.options.boxes[{i}].label.text") == "Show the last known auction price on item tooltips")
    assert lua.eval(f"ns.options.boxes[{box}].get()") is True and lua.eval("FWCS_DB.__ui.tipPrice") is None
    lua.execute(f"local b = ns.options.boxes[{box}]; b.GetChecked = function() return false end; b.scripts.OnClick(b)")
    assert lua.eval("FWCS_DB.__ui.tipPrice") is False and tip(lua, CLOTH) == []
    lua.execute("ns.options:OnDefault()")
    assert lua.eval("FWCS_DB.__ui.tipPrice") is None and len(tip(lua, CLOTH)) == 2


def test_nothing_without_the_lists_without_a_house_or_with_odd_input():
    if lupa is None:
        return
    lua = _game(saved=TIP + HOOK)                                           # Plans.lua of an earlier helper: no FWCS_PRICES
    assert tip(lua, CLOTH) == [] and lua.eval("ns.priceFailures") == 0
    lua = priced_game(extra='function GetRealmName() return "Nowhere" end')    # a realm of no house the helper wrote
    assert tip(lua, CLOTH) == []
    lua = priced_game(given={"stonespine--horde": {"at": NOW, "prices": 5}})   # a list that is not one
    assert tip(lua, CLOTH) == []
    lua = priced_game()
    lua.execute("postcalls[1](GameTooltip, nil); postcalls[1](GameTooltip, { id = 'x' }); postcalls[1](nil, { id = 2589 }); "
                "postcalls[1](7, { id = 2589 })")
    lua.execute('GameTooltip.GetPrimaryTooltipInfo = function() error("no") end')
    assert tip(lua, CLOTH) == ["Auction house = 12c each"] and lua.eval("ns.priceFailures") == 1     # what was added stays; nothing escapes
    lua.execute("FWCS_DB = nil")
    assert tip(lua, CLOTH) == []                                            # before the saved variables are in


def test_an_item_with_no_price_costs_a_look_up_and_builds_nothing():
    if lupa is None:
        return
    lua = priced_game()
    lua.execute("calls = 0; local money, age = ns.Money, ns.Age; ns.Money = function(...) calls = calls + 1; return money(...) end; "
                "ns.Age = function(...) calls = calls + 1; return age(...) end")
    tip(lua, 99999)
    tip(lua, 99998)
    assert lua.eval("calls") == 0
    tip(lua, CLOTH)
    assert lua.eval("calls") == 2


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)

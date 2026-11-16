"""Vendor items first (15 Nov 2026): a leatherworker at 97 with 64 Medium Leather in the bags was told to buy the pattern for
Hillman's Belt at the auction house, although a recipe the character knows, orange at 97, takes Medium Leather and nothing else but
a vendor's goods. The data has it (data/professions/leatherworking.json): Dark Leather Tunic, spell 2169, 6 Medium Leather, 1 Fine
Thread and 1 Gray Dye a craft, yellow from 100, green 112, grey 125; Fine Thread and Gray Dye are a vendor's. The route's stretch here
is Hillman's Belt itself (8 Medium Leather, an Elixir of Wisdom from the house and 2 Fine Thread a craft), its pattern bought at the
auction house.

What is held here, on a skill-up route with "Use what I already have first" on: before the auction house, a recipe to buy or a
trainer, a known recipe that still gives points (orange or yellow, never green or grey, never one with a cooldown, of this profession)
and that what the character holds makes once a vendor's goods are added is made first: the bank, the mailbox, the vendor, then the
hammer, the route's own trip the arrow's note meanwhile. A recipe of a vendor's goods alone is left to the route. What the character
has is used now, even what a later stretch of the route planned to use. The profit route, and the box off: as before.

Needs a Lua: `pip install lupa`; without it this says so and passes.
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_bags_first as bags_first  # noqa: E402
from test_bags_first import strip  # noqa: E402
from test_ingame import _game, lupa  # noqa: E402
from test_plans import document  # noqa: E402

LW = 165
LEATHER, THREAD, DYE, ELIXIR, PATTERN, BELT, TUNIC, SCALE = 2319, 2321, 4340, 3383, 4294, 4250, 2317, 7287
SPELL_BELT, SPELL_TUNIC, SPELL_KIT, SPELL_GLOVES, SPELL_RIBS = 3767, 2169, 9101, 9072, 2546


def leather_doc() -> dict:
    """The test document with a leatherworking route 90 to 110, Hillman's Belt throughout, its pattern from the house; twice, as the
    profit route ("trainer") and as the skill-up route ("trainer-skill"), the document's variants saying which is which."""
    doc = copy.deepcopy(document())
    plan = {"profession": "leatherworking", "skill_line": LW, "variant": "trainer", "start": 90, "target": 110, "net": -60000, "spent": 60000,
            "sold": 0, "gaps": [], "made": {}, "sell": {}, "disenchant": [],
            "steps": [{"from": 90, "to": 110, "recipe": "Hillman's Belt", "spell": SPELL_BELT, "crafts": 20,
                       "uses": [[LEATHER, 8], [ELIXIR, 1], [THREAD, 2]], "makes": [BELT, 1], "per": [1] * 20,
                       "buy": [LEATHER, ELIXIR, THREAD], "craft": [], "learn": [PATTERN, 5000]}],
            "buy": {str(LEATHER): [150, "ah"], str(ELIXIR): [400, "ah"], str(THREAD): [100, "vendor"], str(PATTERN): [5000, "ah"]}}
    doc["plans"]["leatherworking-trainer"] = plan
    doc["plans"]["leatherworking-trainer-skill"] = dict(copy.deepcopy(plan), variant="trainer-skill")
    doc["variants"] = [["trainer", "Profit", "plans", "profit"], ["trainer-skill", "Skill-up", "plans", "skill"]]
    doc["focus"] = [["profit", "Profit"], ["skill", "Skill-up"]]
    doc["items"].update({str(LEATHER): "Medium Leather", str(THREAD): "Fine Thread", str(DYE): "Gray Dye", str(ELIXIR): "Elixir of Wisdom",
                         str(PATTERN): "Pattern: Hillman's Belt", str(BELT): "Hillman's Belt", str(TUNIC): "Dark Leather Tunic",
                         str(SCALE): "Red Whelp Scale"})
    return doc


GAME = f"""
  -- the leatherworking window as the client gives it: the recipes known, their colour (0 orange .. 3 grey) and reagents
  names = {{ [{SPELL_TUNIC}] = "Dark Leather Tunic", [{SPELL_KIT}] = "Dyed Thread Kit", [{SPELL_GLOVES}] = "Red Whelp Gloves" }}
  schematic = {{ [{SPELL_TUNIC}] = {{ {{ {LEATHER}, 6 }}, {{ {THREAD}, 1 }}, {{ {DYE}, 1 }} }},
                [{SPELL_KIT}] = {{ {{ {THREAD}, 2 }}, {{ {DYE}, 1 }} }},
                [{SPELL_GLOVES}] = {{ {{ {SCALE}, 6 }}, {{ {LEATHER}, 4 }}, {{ {THREAD}, 1 }} }} }}
  learned, colour, cooldown = {{}}, {{}}, {{}}
  for spell in pairs(names) do learned[spell] = true; colour[spell] = 0 end
  learned[{SPELL_BELT}] = false
  ProfessionsFrame = {{ CraftingPage = {{ CreateAllButton = CreateFrame("Button") }} }}
  C_TradeSkillUI = {{
    GetBaseProfessionInfo = function() return {{ professionID = {LW}, skillLevel = skill }} end,
    GetRecipeInfo = function(id) return {{ recipeID = id, name = names[id], learned = learned[id] or false, relativeDifficulty = colour[id] }} end,
    GetRecipeRequirements = function(id) return {{}} end,
    GetAllRecipeIDs = function() local out = {{}}; for spell in pairs(names) do table.insert(out, spell) end; table.sort(out); return out end,
    GetRecipeSchematic = function(id)
      local slots = {{}}
      for _, u in ipairs(schematic[id] or {{}}) do table.insert(slots, {{ reagents = {{ {{ itemID = u[1] }} }}, quantityRequired = u[2] }}) end
      return {{ reagentSlotSchematics = slots }}
    end,
    GetRecipeCooldown = function(id) return cooldown[id] end,
    CraftRecipe = function() end, StopRecipeRepeat = function() end,
  }}
  function GetNumSkillLines() return 2 end
  function GetSkillLineInfo(i)
    if i == 1 then return "Professions", true end
    return "Leatherworking", false, false, skill, 0, 0, 150
  end
  level = 30
  function UnitLevel() return level end
  skill = 97
  -- a merchant met who sells Gray Dye (the route itself buys none): a vendor's item by its price
  FWCS_DB.__vendors = {{ ["Creature-0-1-1-1-1"] = {{ name = "Dye Seller", items = {{ [{DYE}] = {{ price = 50, stack = 1, n = -1, usable = true }} }} }} }}
  ns.Settings().variant = "trainer-skill"
  ns.inv.Char().skills[{LW}] = skill
  Fire("SKILL_LINES_CHANGED"); Fire("BAG_UPDATE_DELAYED"); RunTimers()
"""


def game(focus="skill"):
    lua = _game(leather_doc())
    lua.execute(GAME)
    if focus == "profit":
        lua.execute('ns.Settings().variant = "trainer"; ns.HaveChanged()')
    return lua


def held(lua, bags=(), bank=(), mail=(), skill=97):
    """The bags now ({item: units}), the bank and the mail as last counted, the skill."""
    slots = ", ".join(f"{{ {i}, {n} }}" for i, n in dict(bags).items())
    rows = {}
    for col, place in ((2, bank), (3, mail)):
        for i, n in dict(place).items():
            rows.setdefault(i, [0, 0, 0, 0])[col - 1] = n
    items = ", ".join(f"[{i}] = {{ {', '.join(map(str, r))} }}" for i, r in rows.items())
    lua.execute(f"skill = {skill}; ns.inv.Char().skills[{LW}] = skill; bags[0] = {{ {slots} }}; ns.inv.Char().mailed = nil; "
                f"Fire('BAG_UPDATE_DELAYED'); RunTimers(); ns.inv.Char().items = {{ {items} }}; ns.HaveChanged()")


def verdict(lua) -> dict:
    """The Make button's verdict with the leatherworking window open."""
    lua.execute('Fire("TRADE_SKILL_SHOW")')
    v = lua.eval("ForeverWowCraftMake.verdict")
    return {"text": strip(v.text), "note": strip(v.note), "arrow": strip(v.arrowNote or v.note or v.text), "tip": [strip(t) for t in v.tip.values()],
            "spell": v.spell, "crafts": v.crafts, "to": v.to, "bank": v.bank, "place": v.place[1] if v.place else None,
            "item": v.place[3] if v.place else None, "aside": strip(v.aside.text) if v.aside else None,
            "aside_place": v.aside.place[1] if v.aside else None}


def test_the_hillmans_belt_case_the_vendor_then_the_hammer_then_the_route():
    """The report: skill 97, 64 Medium Leather in the bags, Hillman's Belt's pattern to buy. Ten tunics (60 of the leather), the
    thread and the dye for them bought from a vendor first; the pattern's purchase the arrow's note throughout."""
    if lupa is None:
        return
    lua = game()
    assert lua.eval('ns.RouteFor("leatherworking").variant') == "trainer-skill"
    held(lua, bags={LEATHER: 64})
    v = verdict(lua)
    assert v["text"] == "Buy 10 Fine Thread and 10 Gray Dye from a vendor" and v["place"] == "vendor", v
    assert v["arrow"] == "Buy 10 Fine Thread and 10 Gray Dye from a vendor; using your 60 Medium Leather", v
    assert v["note"] == "Using your 60 Medium Leather"
    assert v["aside"] == "Then buy the recipe for Hillman's Belt" and v["aside_place"] == "auction", v
    tip = v["tip"]
    i = tip.index("Using your 60 Medium Leather: Dark Leather Tunic gives points with only 10 Fine Thread and 10 Gray Dye to buy from a vendor.")
    assert tip[i + 1:i + 6] == ["To buy from a vendor:", "  10 Fine Thread, about 10s 00c", "  10 Gray Dye, about 5s 00c",
                                "Then make 10 Dark Leather Tunic, stopping at skill 110.",
                                "Then buy the recipe for Hillman's Belt (the arrow's note)."], tip
    assert lua.eval("ns.inv.Char().tolearn.item") == PATTERN                         # the list at the house still offers the pattern
    # bought: the hammer, the whole run from the bags
    held(lua, bags={LEATHER: 64, THREAD: 10, DYE: 10})
    v = verdict(lua)
    assert v["text"] == "Make 10 Dark Leather Tunic" and v["spell"] == SPELL_TUNIC and v["crafts"] == 10, v
    assert v["aside"] == "Then buy the recipe for Hillman's Belt", v
    assert any("Dark Leather Tunic is not on the route but still gives points: made from your bags" in t for t in v["tip"]), v["tip"]
    # made: 4 leather left, no craft of anything; the route's own verdict
    lua.execute(f"colour[{SPELL_TUNIC}] = 1")
    held(lua, bags={LEATHER: 4}, skill=107)
    v = verdict(lua)
    assert v["text"] == "Buy the recipe for Hillman's Belt first" and v["aside"] is None, v


def test_the_bank_then_the_vendor_then_the_hammer():
    if lupa is None:
        return
    lua = game()
    held(lua, bags={LEATHER: 30}, bank={LEATHER: 34})
    v = verdict(lua)
    assert v["text"] == "Take 30 Medium Leather from the bank" and v["bank"], v
    assert v["note"] == "Using your 60 Medium Leather; 30 Medium Leather: bank", v
    assert "In your bank (as counted when it was last open):" in v["tip"] and "Then buy 10 Fine Thread and 10 Gray Dye from a vendor." in v["tip"], v["tip"]
    assert v["aside"] == "Then buy the recipe for Hillman's Belt", v
    held(lua, bags={LEATHER: 60}, bank={LEATHER: 4})
    assert verdict(lua)["text"] == "Buy 10 Fine Thread and 10 Gray Dye from a vendor"
    held(lua, bags={LEATHER: 60, THREAD: 10, DYE: 10}, bank={LEATHER: 4})
    assert verdict(lua)["text"] == "Make 10 Dark Leather Tunic"


def test_the_mailbox_before_the_vendor():
    if lupa is None:
        return
    lua = game()
    held(lua, mail={LEATHER: 64, DYE: 3})
    v = verdict(lua)
    assert v["text"] == "Collect from the mailbox: 2 items" and v["place"] == "mailbox", v
    assert v["arrow"] == "Collect from the mailbox: 2 items; using your 60 Medium Leather", v
    assert "  60 Medium Leather" in v["tip"] and "  3 Gray Dye" in v["tip"] and "Then buy 10 Fine Thread and 7 Gray Dye from a vendor." in v["tip"], v["tip"]
    held(lua, bags={LEATHER: 64, DYE: 3})
    assert verdict(lua)["text"] == "Buy 10 Fine Thread and 7 Gray Dye from a vendor"


def test_only_orange_and_yellow_known_recipes_of_this_profession_and_never_a_vendors_goods_alone():
    """The tunic orange, then yellow: offered. Green, grey, cooling down, or the client saying it is another profession's: not, and
    the thread kit (a vendor's goods alone, orange) never is. Red Whelp Gloves take scales the character does not hold: not either."""
    if lupa is None:
        return
    lua = game()
    held(lua, bags={LEATHER: 64})
    assert verdict(lua)["text"] == "Buy 10 Fine Thread and 10 Gray Dye from a vendor"
    lua.execute(f"colour[{SPELL_TUNIC}] = 1; ns.HaveChanged()")
    assert verdict(lua)["text"] == "Buy 10 Fine Thread and 10 Gray Dye from a vendor"
    for change in (f"colour[{SPELL_TUNIC}] = 2", f"colour[{SPELL_TUNIC}] = 3", f"colour[{SPELL_TUNIC}] = 0; cooldown[{SPELL_TUNIC}] = 3600",
                   f"cooldown[{SPELL_TUNIC}] = nil; C_TradeSkillUI.GetTradeSkillLineForRecipe = function(id) return 2939, 'Cooking', 185 end"):
        lua.execute(change + "; ns.HaveChanged()")
        v = verdict(lua)
        assert v["text"] == "Buy the recipe for Hillman's Belt first", (change, v)
        assert not any("Dyed Thread Kit" in t or "Red Whelp" in t for t in v["tip"]), v["tip"]
    # the gloves, with the scales held: offered (4 leather a craft, 6 scales: 2 crafts), the thread bought for them
    lua.execute("C_TradeSkillUI.GetTradeSkillLineForRecipe = nil; ns.HaveChanged()")
    lua.execute(f"colour[{SPELL_TUNIC}] = 3")
    held(lua, bags={LEATHER: 64, SCALE: 12})
    assert verdict(lua)["text"] == "Buy 2 Fine Thread from a vendor"


def test_what_a_later_stretch_planned_to_use_is_used_now():
    """Medium Leather is the route's own (Hillman's Belt takes 8 a craft): the skill-up route uses it at once (until 15 Nov 2026 it
    was kept back for the belts). The profit route makes nothing but its own step."""
    if lupa is None:
        return
    lua = game()
    held(lua, bags={LEATHER: 64, THREAD: 10, DYE: 10})
    assert verdict(lua)["text"] == "Make 10 Dark Leather Tunic"
    lua.execute('ns.Settings().variant = "trainer"; ns.HaveChanged()')
    assert lua.eval('ns.RouteFor("leatherworking").variant') == "trainer"
    assert verdict(lua)["text"] == "Buy the recipe for Hillman's Belt first"          # no tunic, nor the thread kit, off the profit route


def test_the_route_learned_the_vendor_comes_before_the_auction_house():
    """Hillman's Belt known, its elixirs to buy at the house: the tunics first, from the leather and a vendor's goods; no aside."""
    if lupa is None:
        return
    lua = game()
    lua.execute(f"learned[{SPELL_BELT}] = true; names[{SPELL_BELT}] = \"Hillman's Belt\"; colour[{SPELL_BELT}] = 0")
    held(lua, bags={LEATHER: 64})
    v = verdict(lua)
    assert v["text"] == "Buy 10 Fine Thread and 10 Gray Dye from a vendor" and v["aside"] is None, v
    held(lua, bags={LEATHER: 64, THREAD: 10, DYE: 10})
    assert verdict(lua)["text"] == "Make 10 Dark Leather Tunic"
    held(lua, bags={LEATHER: 4, THREAD: 0}, skill=107)
    assert verdict(lua)["text"].startswith("Buy from a vendor (1) and the auction house"), verdict(lua)


def test_the_box_off_and_the_profit_route_are_as_before():
    if lupa is None:
        return
    lua = game()
    held(lua, bags={LEATHER: 64})
    assert verdict(lua)["text"] == "Buy 10 Fine Thread and 10 Gray Dye from a vendor"
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("have off")')
    v = verdict(lua)
    assert v["text"] == "Buy the recipe for Hillman's Belt first" and v["aside"] is None, v
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("have on")')
    assert verdict(lua)["text"] == "Buy 10 Fine Thread and 10 Gray Dye from a vendor"
    lua = game("profit")
    held(lua, bags={LEATHER: 64})
    v = verdict(lua)
    assert v["text"] == "Buy the recipe for Hillman's Belt first" and v["aside"] is None, v
    assert not any("to buy from a vendor" in t for t in v["tip"]), v["tip"]



def test_the_profit_route_follows_its_own_recipes_with_the_box_on():
    """15 Nov 2026: with the bags that make each of the three things happen on a skill-up route, the profit route gives its own step:
    no next-best of the stretch from the bags (the cake for the soup), no known recipe off the route (the panel's cake), no vendor
    trip (the tunics). What the character holds of the step's own reagents still counts: the soup's fin in the bank is fetched."""
    if lupa is None:
        return
    # 1. a next-best from the bags: the cakes for the soup on the skill-up route; on the profit route the soup's own fin, from the bank
    for focus, expect in (("skill", "Make 4 Gooey Spider Cake"), ("profit", "Take 1 Murloc Fin from the bank")):
        lua = bags_first.game(bags_first.cooking_doc(focus))
        bags_first.held(lua, bags={bags_first.FIN: 1, bags_first.LEG: 9, bags_first.SPICES: 5}, bank={bags_first.FIN: 1})
        assert bags_first.verdict(lua)["text"] == expect, (focus, bags_first.verdict(lua))
    # and the profit route's purchase is less what the bags hold of the soup's own reagents (1 fin of the 18, 5 spices of 9)
    v = bags_first.verdict(bags_first_held_profit())
    assert "  17 Murloc Fin (have 1), about 51s 00c, at the auction house" in v["tip"], v["tip"]
    # 2. a known recipe off the route: the panel's cake on the skill-up route; the recipe on the profit route
    for focus, expect in (("skill", "Make 4 Gooey Spider Cake"), ("profit", "Buy the recipe for Clam Chowder first")):
        doc = bags_first.offroute_doc()
        doc["variants"] = [["trainer", focus, "plans", focus]]
        lua = bags_first.game(doc)
        lua.execute(f"learned[{bags_first.SPELL_TAIL}] = true" + bags_first.PANEL)
        bags_first.held(lua, bags={bags_first.FIN: 6, bags_first.LEG: 9, bags_first.SPICES: 7}, skill=120)
        v = bags_first.panel_verdict(lua)
        assert v["text"] == expect and (focus == "skill" or v["aside"] is None), (focus, v)
    # 3. a vendor trip: the tunics on the skill-up route; the pattern on the profit route
    for focus, expect in (("skill", "Buy 10 Fine Thread and 10 Gray Dye from a vendor"), ("profit", "Buy the recipe for Hillman's Belt first")):
        lua = game(focus)
        held(lua, bags={LEATHER: 64})
        assert verdict(lua)["text"] == expect, (focus, verdict(lua))


def bags_first_held_profit():
    """The cooking profit route at 116 with 1 fin and 5 spices in the bags and nothing in the bank: the soup's own purchase."""
    lua = bags_first.game(bags_first.cooking_doc("profit"))
    bags_first.held(lua, bags={bags_first.FIN: 1, bags_first.LEG: 9, bags_first.SPICES: 5})
    return lua


if __name__ == "__main__":
    if lupa is None:
        print("skipped: no Lua here (pip install lupa); tests/lua_check.py still reads the addon's files")
        sys.exit(0)
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)

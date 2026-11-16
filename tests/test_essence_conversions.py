"""An enchanter's essences, split and combined (1.8.4): three Lesser Magic Essence make one Greater and one Greater makes three
Lesser, by using the item (the client's tables, read by the site). A plan's "convert" (plans.py) says each conversion both ways for
every essence the route uses; a conversion the route makes is in "made" without a spell, being no recipe of the profession's window.

What is held of either kind counts against what a step needs (bags, bank and mail as the rest of the addon counts them), converted in
whole items, and comes off what the step buys in the Make button, the shopping list and the /fwc window alike. The button cannot use an
item (the client allows that only from a secure action button), so the words say to right-click the essence in the bags. A document
without "convert" behaves as before.

Needs a Lua for most of it: `pip install lupa`; without it those say so and pass. The checks of plans.py run anyway.
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fwchelper import plans  # noqa: E402
from test_bags_first import strip  # noqa: E402
from test_ingame import _game, lupa  # noqa: E402
from test_plans import document  # noqa: E402

ENCHANTING = 333
LESSER, GREATER = 10938, 10939
SPELL_COMBINE, SPELL_SPLIT = 13361, 13362
SPELL_WAND, SPELL_ROD = 14807, 7795
WAND, ROD = 11288, 6339
CONVERT = {str(LESSER): [GREATER, 1, 3, SPELL_SPLIT], str(GREATER): [LESSER, 3, 1, SPELL_COMBINE]}


def enchanting_doc(kind="split", focus="skill", convert=True) -> dict:
    """The test document with an enchanting route 100 to 110 alone. "split": a step of 2 Lesser Magic Essence a craft, the route buying
    Greater and splitting it (20 lesser: 7 greater, one lesser over); "combine": a step of 1 Greater a craft for 3 crafts, the route
    buying Lesser and combining them; "lesser": the split step with the route buying Lesser as it is (no conversion of its own).
    `focus` "skill" or "profit"; `convert` False: a document from before 1.8.4."""
    doc = copy.deepcopy(document())
    if kind == "combine":
        step = {"from": 100, "to": 103, "recipe": "Greater Magic Wand", "spell": SPELL_WAND, "crafts": 3, "uses": [[GREATER, 1]],
                "makes": [WAND, 1], "per": [1] * 3, "buy": [LESSER], "craft": [GREATER]}
        made = {str(GREATER): [1, [[LESSER, 3]]]}
    else:
        step = {"from": 100, "to": 110, "recipe": "Runed Silver Rod", "spell": SPELL_ROD, "crafts": 10, "uses": [[LESSER, 2]],
                "makes": [ROD, 1], "per": [1] * 10, "buy": [GREATER] if kind == "split" else [LESSER], "craft": [LESSER] if kind == "split" else []}
        made = {str(LESSER): [3, [[GREATER, 1]]]} if kind == "split" else {}
    plan = {"profession": "enchanting", "skill_line": ENCHANTING, "variant": "trainer", "start": 100, "target": step["to"], "net": -2100,
            "spent": 2100, "sold": 0, "gaps": [], "steps": [step], "made": made, "sell": {}, "disenchant": [],
            "buy": {str(GREATER): [300, "ah"], str(LESSER): [120, "ah"]}}
    if convert:
        plan["convert"] = copy.deepcopy(CONVERT)
    doc["plans"] = {"enchanting-trainer": plan}
    doc["also"] = {}
    doc["variants"] = [["trainer", "Skill-up" if focus == "skill" else "Profit", "plans", focus]]
    doc["focus"] = [["profit", "Profit"], ["skill", "Skill-up"]]
    doc["items"].update({str(LESSER): "Lesser Magic Essence", str(GREATER): "Greater Magic Essence", str(WAND): "Greater Magic Wand",
                         str(ROD): "Runed Silver Rod"})
    return doc


GAME = f"""
  learned = {{ [{SPELL_WAND}] = true, [{SPELL_ROD}] = true }}
  C_TradeSkillUI = {{
    GetBaseProfessionInfo = function() return {{ professionID = {ENCHANTING}, skillLevel = skill }} end,
    GetRecipeInfo = function(id) return {{ recipeID = id, learned = learned[id] or false }} end,
    GetRecipeRequirements = function(id) return {{}} end,
    CraftRecipe = function() end, StopRecipeRepeat = function() end,
  }}
  function GetNumSkillLines() return 2 end
  function GetSkillLineInfo(i)
    if i == 1 then return "Professions", true end
    return "Enchanting", false, false, skill, 0, 0, 150
  end
  level = 30
  function UnitLevel() return level end
  skill = 100
  ns.inv.Char().skills[{ENCHANTING}] = skill
  Fire("SKILL_LINES_CHANGED"); Fire("BAG_UPDATE_DELAYED"); RunTimers()
"""


def game(doc):
    lua = _game(doc)
    lua.execute(GAME)
    return lua


def held(lua, bags=(), bank=(), mail=(), skill=100):
    """The bags now ({item: units}), the bank and the mail as last counted, the skill."""
    slots = ", ".join(f"{{ {i}, {n} }}" for i, n in dict(bags).items())
    rows = {}
    for col, place in ((2, bank), (3, mail)):
        for i, n in dict(place).items():
            rows.setdefault(i, [0, 0, 0, 0])[col - 1] = n
    items = ", ".join(f"[{i}] = {{ {', '.join(map(str, r))} }}" for i, r in rows.items())
    lua.execute(f"skill = {skill}; ns.inv.Char().skills[{ENCHANTING}] = skill; bags[0] = {{ {slots} }}; ns.inv.Char().mailed = nil; "
                f"Fire('BAG_UPDATE_DELAYED'); RunTimers(); ns.inv.Char().items = {{ {items} }}; ns.HaveChanged()")


def verdict(lua) -> dict:
    v = lua.eval(f'ns.verdict.Verdict({{ open = {{ id = {ENCHANTING}, rank = skill, max = 150 }}, profession = "enchanting" }})')
    return {"text": strip(v.text), "note": strip(v.note), "tip": [strip(t) for t in v.tip.values()], "spell": v.spell, "crafts": v.crafts,
            "bank": v.bank, "show": v.show, "place": v.place[1] if v.place else None}


def buy(lua) -> dict:
    """What the step still buys, as the Make button's walk has it (ns.NextCraft over the bags and the bank)."""
    nxt = lua.eval('(function() local p = ns.RouteFor("enchanting"); local have = {}; '
                   'for _, i in ipairs({ ' + f"{LESSER}, {GREATER}" + ' }) do local r = ns.inv.Char().items[i]; '
                   'have[i] = (ns.inv.Count(i) or 0) + (r and r[2] or 0) end; return ns.NextCraft(p, skill, have) end)()')
    return {b[1]: b[2] for b in nxt.buy.values()}


def test_greater_held_and_lesser_needed_says_split_then_the_step():
    if lupa is None:
        return
    lua = game(enchanting_doc())
    held(lua, bags={GREATER: 7})
    v = verdict(lua)
    assert v["text"] == "Split 7 Greater Magic Essence into 21 Lesser Magic Essence", v
    assert v["spell"] is None and v["show"] and v["tip"][-1] == "Right-click the Greater Magic Essence in your bags: one click a conversion, 1 into 3."
    assert "Then the step: Runed Silver Rod, skill 100 to 110." in v["tip"]
    assert not any("Run the helper" in t or t.startswith("Learn") for t in v["tip"]) and buy(lua) == {}
    held(lua, bags={LESSER: 21})
    v = verdict(lua)
    assert v["text"] == "Make 10 Runed Silver Rod" and v["spell"] == SPELL_ROD, v


def test_lesser_held_and_greater_needed_says_combine():
    if lupa is None:
        return
    lua = game(enchanting_doc("combine"))
    held(lua, bags={LESSER: 9})
    v = verdict(lua)
    assert v["text"] == "Combine 9 Lesser Magic Essence into 3 Greater Magic Essence", v
    assert v["tip"][-1] == "Right-click the Lesser Magic Essence in your bags: one click a conversion, 3 into 1."
    held(lua, bags={LESSER: 8})                              # two whole conversions; the third greater takes one lesser more, bought
    v = verdict(lua)
    assert v["text"] == "Combine 6 Lesser Magic Essence into 2 Greater Magic Essence", v
    assert buy(lua) == {LESSER: 1}
    held(lua, bags={GREATER: 3})
    assert verdict(lua)["text"] == "Make 3 Greater Magic Wand"


def test_a_mix_of_both_held_comes_off_what_is_bought():
    if lupa is None:
        return
    lua = game(enchanting_doc())
    held(lua)
    assert buy(lua) == {GREATER: 7}
    held(lua, bags={LESSER: 4, GREATER: 2})                  # 20 needed: 4 held, 6 from the 2 greater, 10 more from 4 greater bought
    assert buy(lua) == {GREATER: 4}
    assert verdict(lua)["text"] == "Split 2 Greater Magic Essence into 6 Lesser Magic Essence"
    # a route that buys Lesser as it is: a Greater held is split for it all the same, and fewer Lesser bought
    lua = game(enchanting_doc("lesser"))
    held(lua, bags={GREATER: 3})
    assert buy(lua) == {LESSER: 11}
    assert verdict(lua)["text"] == "Split 3 Greater Magic Essence into 9 Lesser Magic Essence"


def test_nothing_held_buys_what_the_route_bought_then_split():
    if lupa is None:
        return
    lua = game(enchanting_doc())
    held(lua)
    v = verdict(lua)
    assert v["text"] == "Buy 7 Greater Magic Essence at the auction house, to split", v
    assert "  7 Greater Magic Essence (have 0), about 21s 00c, at the auction house, to split into Lesser Magic Essence" in v["tip"], v["tip"]
    held(lua, bags={GREATER: 7})
    assert verdict(lua)["text"] == "Split 7 Greater Magic Essence into 21 Lesser Magic Essence"


def test_the_bank_and_the_mail_hold_essences_too():
    if lupa is None:
        return
    lua = game(enchanting_doc())                             # the route's own split: the bank's greater fetched, as any reagent bought
    held(lua, bank={GREATER: 7})
    v = verdict(lua)
    assert v["text"] == "Take 7 Greater Magic Essence from the bank" and v["bank"], v
    lua = game(enchanting_doc("lesser"))                     # the route buys lesser: the bank's greater serves, to split
    held(lua, bank={GREATER: 7})
    v = verdict(lua)
    assert v["text"] == "Take 7 Greater Magic Essence from the bank, to split" and v["bank"], v
    held(lua, mail={GREATER: 7})
    v = verdict(lua)
    assert v["text"] == "Collect 7 Greater Magic Essence from the mailbox" and v["place"] == "mailbox", v


def test_the_shopping_list_and_the_window_agree_with_the_button():
    if lupa is None:
        return
    lua = game(enchanting_doc())
    held(lua, bags={LESSER: 4, GREATER: 2})
    lua.execute('ns.inv.Char().making = "enchanting"')
    shopping = lua.eval("ns.craft.Shopping()")
    rows = [(shopping[i].item, shopping[i].units - shopping[i].have) for i in range(1, len(shopping) + 1)]
    assert rows == [(GREATER, 4)], rows
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("enchanting")')
    text = strip(lua.eval("AllText()"))
    assert "Greater Magic Essence" in text and "Lesser Magic Essence  split from Greater Magic Essence" in text, text
    assert dict(lua.eval('ns.Tailor(ns.RouteFor("enchanting"), 100, { [' + f"{LESSER}] = 4, [{GREATER}] = 2" + ' }).buy')) == {GREATER: 4}


def test_a_profit_route_does_the_same():
    if lupa is None:
        return
    lua = game(enchanting_doc(focus="profit"))
    held(lua, bags={GREATER: 7})
    assert verdict(lua)["text"] == "Split 7 Greater Magic Essence into 21 Lesser Magic Essence"
    held(lua, bags={LESSER: 4, GREATER: 2})
    assert buy(lua) == {GREATER: 4}


def test_a_document_without_convert_is_as_before():
    if lupa is None:
        return
    lua = game(enchanting_doc(convert=False))
    held(lua)
    assert verdict(lua)["text"] == "Buy 7 Greater Magic Essence at the auction house"
    held(lua, bags={GREATER: 7})                             # the route's own "made" row, read as before 1.8.4
    v = verdict(lua)
    assert v["text"] == "Make 7 Lesser Magic Essence first" and "Run the helper (fwch.py plans) for a newer route." in v["tip"], v
    lua = game(enchanting_doc("lesser", convert=False))
    held(lua, bags={GREATER: 3})
    assert buy(lua) == {LESSER: 20}


def test_check_plans_keeps_a_good_convert_and_drops_nonsense_without_the_routes():
    doc = enchanting_doc()
    assert plans.check_plans(doc) is None and doc["plans"]["enchanting-trainer"]["convert"] == CONVERT
    bad = [{str(LESSER): "split"}, {str(LESSER): [GREATER, 1, 3]}, {str(LESSER): [GREATER, 1, 1000, SPELL_SPLIT]},
           {str(LESSER): [GREATER, 0, 3, SPELL_SPLIT]}, {str(LESSER): [GREATER, True, 3, SPELL_SPLIT]}, {str(LESSER): [99999, 1, 3, SPELL_SPLIT]},
           {"x": [GREATER, 1, 3, SPELL_SPLIT]}, {str(LESSER): [LESSER, 1, 3, SPELL_SPLIT]}, {str(LESSER): {"from": GREATER}},
           {str(LESSER): [GREATER, 1, 3, "13362"]}, [GREATER, 1, 3], {str(i): [GREATER, 1, 3, SPELL_SPLIT] for i in range(1, 70)}]
    for convert in bad:
        doc = enchanting_doc()
        doc["plans"]["enchanting-trainer"]["convert"] = convert
        assert plans.check_plans(doc) is None, convert                       # the document stands
        assert "convert" not in doc["plans"]["enchanting-trainer"], convert   # without the conversions
        assert doc["plans"]["enchanting-trainer"]["steps"]                    # and with the route
    assert "convert" in plans.lua(enchanting_doc()["plans"]["enchanting-trainer"])      # it reaches Plans.lua as it is


if __name__ == "__main__":
    if lupa is None:
        print("skipped the game's part: no Lua here (pip install lupa); tests/lua_check.py still reads the addon's files")
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)

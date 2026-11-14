"""The bags first (14 Nov 2026): a cooking route at 116, its stretch Murloc Fin Soup to 125 (2 fins and a Hot Spices a craft),
Gooey Spider Cake its next-best (2 legs and a Hot Spices). The bags hold 1 fin, 9 legs and 5 spices; the bank 1 fin. The Make
button said "Take 1 Murloc Fin from the bank" for the soup, although 4 cakes could be made from the bags at once.

What is held here: while a recipe that may stand in for the stretch (the route's own, then its next-best, by the rules of "Use
what I already have first") can be made from the bags alone, the button makes a whole run of it; only once the bags hold no
craft of any does it send the character to the bank, then the mailbox, then a seller. The stretch's own recipe keeps its place
when the bags hold a craft of it; a next-best the character does not know, or cannot learn at its level, is passed over; with
the box off, the route's own recipes and nothing else, as before.

Then (14 Nov 2026), the cakes made, the button said "Buy the recipe for Clam Chowder first" with 3 soups' worth still in the
bags: the stretch's recipe not learned came before the bags. The route the player had (the Alliance skill-up cooking route of
the house, as fetched) has Clam Chowder 101 to 134, a scroll bought, its next-best Dig Rat Stew (a scroll too) and Crispy Lizard
Tail; neither the soup nor the cake is listed in it any more. The second half below is that shape: a recipe the planner vouches
for (the stretch's own and next-best, then those of the stretches before it) that the bags hold a craft of is made first, the
recipe's trip the arrow's note; a run stops where its chance falls to 0; the client's colour stands in where the route gives no
chance, and its grey is none; with the bags empty, the recipe first as before.

Last, the fallback: nothing the route vouches for in the bags, the profession panel open, any recipe the character knows that the
panel shows orange or yellow and the bags hold a craft of, orange first, then the most crafts; never green, grey or red, one
cooling down or with a cooldown at all, a transmute, or one that takes what the route still needs (a vendor's goods excepted);
with the panel closed or the box off, as before.

Needs a Lua: `pip install lupa`; without it this says so and passes.
"""
import copy
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_ingame import _game, lupa  # noqa: E402
from test_plans import document  # noqa: E402

COOKING = 185
FIN, LEG, SPICES, TAIL, MEAT = 1468, 2251, 2692, 5470, 2672
SOUP, CAKE, LIZARD, KABOB = 3663, 3666, 5479, 2683
SPELL_SOUP, SPELL_CAKE, SPELL_LIZARD, SPELL_KABOB = 3372, 3377, 6500, 2549
STRIP = re.compile(r"\|c[0-9a-fA-F]{8}|\|r")


def cooking_doc() -> dict:
    """The test document with a cooking route 100 to 135: kabobs, then the soup with the cake its next-best, then a lizard tail
    stretch that takes Hot Spices too. Legs are dear at the house (10s), so the soup stays the stretch's choice for its whole run
    whatever the bags hold (9 cakes' 9 legs to buy cost more than 16 fins)."""
    doc = copy.deepcopy(document())
    cake = {"recipe": "Gooey Spider Cake", "spell": SPELL_CAKE, "uses": [[LEG, 2], [SPICES, 1]], "makes": [CAKE, 1], "per": [1] * 9,
            "crafts": 9, "at": [110, 130, 150, 170], "cpp": 2020, "buy": [LEG, SPICES], "craft": []}
    steps = [
        {"from": 100, "to": 116, "recipe": "Seasoned Wolf Kabob", "spell": SPELL_KABOB, "crafts": 16, "uses": [[MEAT, 2], [SPICES, 1]],
         "makes": [KABOB, 1], "per": [1] * 16, "buy": [MEAT, SPICES], "craft": []},
        {"from": 116, "to": 125, "recipe": "Murloc Fin Soup", "spell": SPELL_SOUP, "crafts": 9, "uses": [[FIN, 2], [SPICES, 1]],
         "makes": [SOUP, 1], "per": [1] * 9, "buy": [FIN, SPICES], "craft": [], "alt": [cake]},
        {"from": 125, "to": 135, "recipe": "Crispy Lizard Tail", "spell": SPELL_LIZARD, "crafts": 10, "uses": [[TAIL, 1], [SPICES, 1]],
         "makes": [LIZARD, 1], "per": [1] * 10, "buy": [TAIL, SPICES], "craft": []}]
    doc["plans"]["cooking-trainer"] = {
        "profession": "cooking", "skill_line": COOKING, "variant": "trainer", "start": 100, "target": 135, "net": -20000, "spent": 20000,
        "sold": 0, "gaps": [], "steps": steps, "made": {}, "sell": {}, "disenchant": [],
        "buy": {str(FIN): [300, "ah"], str(LEG): [1000, "ah"], str(SPICES): [20, "vendor"], str(TAIL): [200, "ah"], str(MEAT): [100, "ah"]}}
    doc["items"].update({str(FIN): "Murloc Fin", str(LEG): "Gooey Spider Leg", str(SPICES): "Hot Spices", str(TAIL): "Thunder Lizard Tail",
                         str(MEAT): "Wolf Meat", str(SOUP): "Murloc Fin Soup", str(CAKE): "Gooey Spider Cake", str(LIZARD): "Crispy Lizard Tail",
                         str(KABOB): "Seasoned Wolf Kabob"})
    return doc


GAME = f"""
  colour = {{}}                      -- colour[spell] = the client's relativeDifficulty (0 orange .. 3 grey); none: the client does not say
  learned = {{ [{SPELL_KABOB}] = true, [{SPELL_SOUP}] = true, [{SPELL_CAKE}] = true, [{SPELL_LIZARD}] = true }}
  C_TradeSkillUI = {{
    GetBaseProfessionInfo = function() return {{ professionID = {COOKING}, skillLevel = skill }} end,
    GetRecipeInfo = function(id) return {{ recipeID = id, learned = learned[id] or false, relativeDifficulty = colour[id] }} end,
    GetRecipeRequirements = function(id) return {{}} end,
    CraftRecipe = function() end, StopRecipeRepeat = function() end,
  }}
  function GetNumSkillLines() return 2 end
  function GetSkillLineInfo(i)
    if i == 1 then return "Professions", true end
    return "Cooking", false, false, skill, 0, 0, 150
  end
  level = 30
  function UnitLevel() return level end
  skill = 116
  ns.inv.Char().skills[{COOKING}] = skill
  Fire("SKILL_LINES_CHANGED"); Fire("BAG_UPDATE_DELAYED"); RunTimers()
"""


def strip(text) -> str:
    return STRIP.sub("", text or "")


def game(doc=None):
    lua = _game(doc or cooking_doc())
    lua.execute(GAME)
    return lua


def held(lua, bags=(), bank=(), mail=(), skill=116):
    """The bags now ({item: units}), the bank and the mail as last counted, the skill."""
    slots = ", ".join(f"{{ {i}, {n} }}" for i, n in dict(bags).items())
    rows = {}
    for col, place in ((2, bank), (3, mail)):
        for i, n in dict(place).items():
            rows.setdefault(i, [0, 0, 0, 0])[col - 1] = n
    items = ", ".join(f"[{i}] = {{ {', '.join(map(str, r))} }}" for i, r in rows.items())
    lua.execute(f"skill = {skill}; ns.inv.Char().skills[{COOKING}] = skill; bags[0] = {{ {slots} }}; ns.inv.Char().mailed = nil; "
                f"Fire('BAG_UPDATE_DELAYED'); RunTimers(); ns.inv.Char().items = {{ {items} }}; ns.HaveChanged()")


def verdict(lua) -> dict:
    v = lua.eval(f'ns.verdict.Verdict({{ open = {{ id = {COOKING}, rank = skill, max = 150 }}, profession = "cooking" }})')
    return {"text": strip(v.text), "note": strip(v.note), "tip": [strip(t) for t in v.tip.values()], "spell": v.spell, "crafts": v.crafts,
            "to": v.to, "bank": v.bank, "place": v.place[1] if v.place else None, "aside": strip(v.aside.text) if v.aside else None,
            "aside_place": v.aside.place[1] if v.aside else None}


def test_the_bags_make_what_stands_in_before_the_bank_is_visited():
    """The report, as it was: 1 fin in the bags and 1 in the bank, 9 legs and 5 spices in the bags, skill 116."""
    if lupa is None:
        return
    lua = game()
    held(lua, bags={FIN: 1, LEG: 9, SPICES: 5}, bank={FIN: 1})
    assert lua.eval('ns.RouteFor("cooking").steps[2].recipe') == "Murloc Fin Soup"       # the stretch's whole-run choice is unchanged
    v = verdict(lua)
    assert v["text"] == "Make 4 Gooey Spider Cake", v
    assert v["spell"] == SPELL_CAKE and v["crafts"] == 4 and v["to"] == 125 and not v["bank"]
    assert "Using your 8 Gooey Spider Leg and 4 Hot Spices: Gooey Spider Cake stands in for Murloc Fin Soup from your bags, nothing to fetch or buy." in v["tip"], v["tip"]
    assert "In your bank for later: 1 Murloc Fin." in v["tip"] and v["tip"][-1] == "Click: makes 4, stopping at skill 125."
    assert v["note"] == "Using your 8 Gooey Spider Leg and 4 Hot Spices"                 # the arrow's note: this run's
    # the cakes made: 1 leg left, no craft of either from the bags. Now the bank's fin is fetched for the soup
    held(lua, bags={FIN: 1, LEG: 1, SPICES: 1}, bank={FIN: 1}, skill=120)
    v = verdict(lua)
    assert v["text"] == "Take 1 Murloc Fin from the bank" and v["bank"], v
    assert "In your bank (as counted when it was last open):" in v["tip"] and not any("stands in" in t for t in v["tip"])
    # fetched: the soup, from the bags
    held(lua, bags={FIN: 2, LEG: 1, SPICES: 1}, skill=120)
    assert verdict(lua)["text"] == "Make 1 Murloc Fin Soup"
    # nothing in the bags, the bank or the mail: bought, as ever (fins at the house, spices from a vendor)
    held(lua, skill=121)
    v = verdict(lua)
    assert v["text"] == "Buy from a vendor (1) and the auction house (1)", v
    assert "  8 Murloc Fin (have 0), about 24s 00c, at the auction house" in v["tip"], v["tip"]


def test_the_mail_comes_after_the_bags_too():
    if lupa is None:
        return
    lua = game()
    held(lua, bags={FIN: 1, LEG: 9, SPICES: 5}, mail={FIN: 1})
    assert verdict(lua)["text"] == "Make 4 Gooey Spider Cake"
    held(lua, bags={FIN: 1, LEG: 1, SPICES: 1}, mail={FIN: 1}, skill=120)
    v = verdict(lua)
    assert v["text"] == "Collect 1 Murloc Fin from the mailbox" and v["place"] == "mailbox", v


def test_a_craft_of_the_stretchs_own_recipe_in_the_bags_comes_first_and_runs_whole():
    """The soup's 2 fins in the bags: the soup, as before; a whole run of it (2 crafts from 4 fins), then a whole run of the cakes,
    never a craft of each in turn."""
    if lupa is None:
        return
    lua = game()
    held(lua, bags={FIN: 2, LEG: 9, SPICES: 5}, bank={FIN: 1})
    v = verdict(lua)
    assert v["text"] == "Make 1 Murloc Fin Soup" and v["spell"] == SPELL_SOUP and not any("stands in" in t for t in v["tip"]), v
    held(lua, bags={FIN: 4, LEG: 9, SPICES: 10})
    assert verdict(lua)["text"] == "Make 2 Murloc Fin Soup"
    held(lua, bags={LEG: 9, SPICES: 8}, skill=118)
    v = verdict(lua)
    assert v["text"] == "Make 4 Gooey Spider Cake" and not any("In your bank for later" in t for t in v["tip"]), v
    # three points left of the stretch: three cakes, not four (the stretch ends at 125)
    held(lua, bags={LEG: 9, SPICES: 8}, skill=122)
    assert verdict(lua)["text"] == "Make 3 Gooey Spider Cake"


def test_the_box_off_keeps_the_routes_own_recipes_and_the_bank_out():
    if lupa is None:
        return
    lua = game()
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("have off")')
    held(lua, bags={FIN: 1, LEG: 9, SPICES: 5}, bank={FIN: 1})
    v = verdict(lua)
    assert v["text"] == "Buy from a vendor (1) and the auction house (1)", v
    assert "  17 Murloc Fin (have 1), about 51s 00c, at the auction house" in v["tip"], v["tip"]
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("have on")')
    assert verdict(lua)["text"] == "Make 4 Gooey Spider Cake"


def test_a_next_best_the_character_cannot_make_now_is_passed_over():
    """Not known (a trainer's walk), or asking a level the character lacks: no craft from the bags, the bank as before."""
    if lupa is None:
        return
    lua = game()
    held(lua, bags={FIN: 1, LEG: 9, SPICES: 5}, bank={FIN: 1})
    lua.execute(f"learned[{SPELL_CAKE}] = false")
    assert verdict(lua)["text"] == "Take 1 Murloc Fin from the bank"
    lua.execute(f'learned[{SPELL_CAKE}] = true; FWCS_PLANS["stonespine--horde"].plans["cooking-trainer"].steps[2].alt[1].level = 40; ns.HaveChanged()')
    assert verdict(lua)["text"] == "Take 1 Murloc Fin from the bank"
    lua.execute("level = 40; ns.HaveChanged()")
    assert verdict(lua)["text"] == "Make 4 Gooey Spider Cake"


# ---- the stretch's recipe not learned yet: the Clam Chowder stretch ------------------------------------------------------------
CLAM, MILK, MILD, DIGRAT, CHOWDER_SCROLL, DIGRAT_SCROLL, SAUSAGE_SCROLL = 5503, 1179, 2678, 5051, 5528, 5487, 3679
BOAR_LUNG, BOAR_INTESTINE, BEAR_FLANK = 3173, 3172, 3174
SPELL_CHOWDER, SPELL_DIGRAT, SPELL_TAIL, SPELL_SAUSAGE = 6501, 6417, 6418, 3371


def per(at, frm, to):
    """The planner's crafts a point for a next-best (houseplan.alt_step, planner.Recipe.chance): 1 / the classic curve, 0 where grey."""
    out = []
    for s in range(frm, to):
        c = 0.0 if s < at[0] or s >= at[3] else 1.0 if s < at[1] or at[3] <= at[1] else min(1.0, (at[3] - s) / (at[3] - at[1]))
        out.append(round(1 / c, 3) if c else 0)
    return out


def chowder_doc() -> dict:
    """The shape of the fetched route: Blood Sausage to 90, then the soup to 101 with the cake its next-best (the stretch before;
    the route's own recipe goes without its colours, as the site sends it), then Clam Chowder 101 to 134, a scroll bought, its
    next-best Dig Rat Stew (a scroll too) and Crispy Lizard Tail, made grey at 125 here so that a run of it has to stop there."""
    doc = cooking_doc()
    cake = {"recipe": "Gooey Spider Cake", "spell": SPELL_CAKE, "uses": [[LEG, 2], [SPICES, 1]], "makes": [CAKE, 1], "per": per([90, 130, 150, 170], 90, 101),
            "crafts": 11, "at": [90, 130, 150, 170], "cpp": 2020, "buy": [LEG, SPICES], "craft": []}
    digrat = {"recipe": "Dig Rat Stew", "spell": SPELL_DIGRAT, "uses": [[DIGRAT, 1]], "makes": [5478, 1], "per": per([90, 130, 150, 170], 101, 134),
              "crafts": 33, "at": [90, 130, 150, 170], "cpp": 900, "buy": [DIGRAT], "craft": [], "learn": [DIGRAT_SCROLL, 15500]}
    lizard = {"recipe": "Crispy Lizard Tail", "spell": SPELL_TAIL, "uses": [[TAIL, 1], [SPICES, 1]], "makes": [LIZARD, 1], "per": per([100, 110, 115, 125], 101, 134),
              "crafts": 60, "at": [100, 110, 115, 125], "cpp": 950, "buy": [TAIL, SPICES], "craft": []}
    steps = [
        {"from": 60, "to": 90, "recipe": "Blood Sausage", "spell": SPELL_SAUSAGE, "crafts": 30, "uses": [[BOAR_LUNG, 1], [BOAR_INTESTINE, 1], [BEAR_FLANK, 1]],
         "makes": [3220, 1], "per": [1] * 30, "buy": [BOAR_LUNG, BOAR_INTESTINE, BEAR_FLANK], "craft": [], "learn": [SAUSAGE_SCROLL, 200]},
        {"from": 90, "to": 101, "recipe": "Murloc Fin Soup", "spell": SPELL_SOUP, "crafts": 11, "uses": [[FIN, 2], [SPICES, 1]],
         "makes": [SOUP, 1], "per": [1] * 11, "buy": [FIN, SPICES], "craft": [], "alt": [cake]},
        {"from": 101, "to": 134, "recipe": "Clam Chowder", "spell": SPELL_CHOWDER, "crafts": 34, "uses": [[CLAM, 1], [MILK, 1], [MILD, 1]],
         "makes": [5526, 1], "per": [1] * 30 + [1.03, 1.05, 1.08], "buy": [CLAM, MILK, MILD], "craft": [], "learn": [CHOWDER_SCROLL, 800],
         "alt": [digrat, lizard]}]
    plan = doc["plans"]["cooking-trainer"]
    plan.update(start=60, target=134, steps=steps)
    plan["buy"].update({str(CLAM): [150, "ah"], str(MILK): [25, "vendor"], str(MILD): [10, "vendor"], str(DIGRAT): [400, "ah"],
                        str(CHOWDER_SCROLL): [800, "ah"], str(DIGRAT_SCROLL): [15500, "ah"], str(BOAR_LUNG): [50, "ah"],
                        str(BOAR_INTESTINE): [50, "ah"], str(BEAR_FLANK): [50, "ah"]})
    doc["items"].update({str(CLAM): "Clam Meat", str(MILK): "Ice Cold Milk", str(MILD): "Mild Spices", str(DIGRAT): "Dig Rat",
                         str(CHOWDER_SCROLL): "Recipe: Clam Chowder", str(DIGRAT_SCROLL): "Recipe: Dig Rat Stew", str(SAUSAGE_SCROLL): "Recipe: Blood Sausage",
                         str(BOAR_LUNG): "Boar Lungs", str(BOAR_INTESTINE): "Boar Intestines", str(BEAR_FLANK): "Bear Meat",
                         "5526": "Clam Chowder", "5478": "Dig Rat Stew", "3220": "Blood Sausage"})
    return doc


def chowder_game():
    lua = game(chowder_doc())
    lua.execute(f"learned[{SPELL_TAIL}] = true; learned[{SPELL_SAUSAGE}] = true; colour[{SPELL_SOUP}] = 1")   # the soup: yellow in the panel
    return lua


def test_the_bags_come_before_buying_the_stretchs_recipe():
    """The report: Clam Chowder not learned, the bags hold 3 soups' and 4 cakes' worth. The cake first (the route gives its
    chance: orange at 120; the soup's comes from the client alone), the recipe's purchase the arrow's note; then the soups; with the
    bags empty, the recipe as before."""
    if lupa is None:
        return
    lua = chowder_game()
    held(lua, bags={FIN: 6, LEG: 9, SPICES: 7}, skill=120)
    v = verdict(lua)
    assert v["text"] == "Make 4 Gooey Spider Cake" and v["spell"] == SPELL_CAKE and v["to"] == 134, v
    assert v["aside"] == "Then buy the recipe for Clam Chowder" and v["aside_place"] == "auction", v
    assert "Using your 8 Gooey Spider Leg and 4 Hot Spices: Gooey Spider Cake, from an earlier stretch, still gives points: made from your bags, nothing to fetch or buy." in v["tip"], v["tip"]
    assert v["tip"][-2:] == ["Then buy the recipe for Clam Chowder (the arrow's note).", "Click: makes 4, stopping at skill 134."], v["tip"]
    assert lua.eval("ns.inv.Char().tolearn.item") == CHOWDER_SCROLL                    # the list at the house still offers the recipe
    # the cakes made: the soups (yellow in the panel), as many as the bags hold
    held(lua, bags={FIN: 6, LEG: 1, SPICES: 3}, skill=124)
    v = verdict(lua)
    assert v["text"] == "Make 3 Murloc Fin Soup" and v["aside"] == "Then buy the recipe for Clam Chowder", v
    # the client says grey: none, whatever the route's numbers
    lua.execute(f"colour[{SPELL_SOUP}] = 3")
    assert verdict(lua)["text"] == "Buy the recipe for Clam Chowder first"
    # nothing in the bags: the recipe first, as before
    lua.execute(f"colour[{SPELL_SOUP}] = 1")
    held(lua, skill=124)
    v = verdict(lua)
    assert v["text"] == "Buy the recipe for Clam Chowder first" and v["aside"] is None, v


def test_the_recipes_trip_follows_where_it_is():
    """The scroll in the bags: learned first (one click, no trip). In the mail: the mailbox is the arrow's note. A level short: said."""
    if lupa is None:
        return
    lua = chowder_game()
    held(lua, bags={FIN: 6, SPICES: 3, CHOWDER_SCROLL: 1}, skill=120)
    assert verdict(lua)["text"] == "Learn Clam Chowder: use Recipe: Clam Chowder in your bags"
    held(lua, bags={FIN: 6, SPICES: 3}, mail={CHOWDER_SCROLL: 1}, skill=120)
    v = verdict(lua)
    assert v["text"] == "Make 3 Murloc Fin Soup" and v["aside"] == "Then collect Recipe: Clam Chowder from the mailbox", v
    assert v["aside_place"] == "mailbox"
    lua.execute(f'FWCS_PLANS["stonespine--horde"].plans["cooking-trainer"].steps[3].learn = {{ {CHOWDER_SCROLL}, 800, 40 }}')
    held(lua, bags={FIN: 6, SPICES: 3}, skill=120)
    v = verdict(lua)                                    # at level 30 the next-best that fits stands in (Effective), its scroll the note
    assert v["text"] == "Make 3 Murloc Fin Soup" and v["aside"] == "Then buy the recipe for Dig Rat Stew", v
    lua.execute("FWCS_DB.__ui.levelRoutes = false; ns.HaveChanged()")                # "Routes for my level" off: the level said, no trip
    v = verdict(lua)
    assert v["text"] == "Make 3 Murloc Fin Soup" and v["aside"] is None and "Clam Chowder asks for character level 40: learned later." in v["tip"], v


def test_a_run_from_the_bags_stops_where_its_chance_falls_to_0():
    """Crispy Lizard Tail, a next-best of the stretch, grey at 125 (it gives no point from there to 134, which the stretch-wide rule
    refused): made from the bags up to 125, with about how many crafts the five points take, no point a craft promised."""
    if lupa is None:
        return
    lua = chowder_game()
    held(lua, bags={TAIL: 10, SPICES: 10}, skill=120)
    v = verdict(lua)
    assert v["text"] == "Make 10 Crispy Lizard Tail" and v["to"] == 125, v
    assert "Not every craft gives a point here: about 35 crafts for 5 points." in v["tip"] and v["tip"][-1] == "Click: makes 10, stopping at skill 125.", v["tip"]
    assert any("Crispy Lizard Tail stands in for Clam Chowder from your bags" in t for t in v["tip"])
    held(lua, bags={TAIL: 10, SPICES: 10}, skill=125)                                # grey: nothing from the bags
    assert verdict(lua)["text"] == "Buy the recipe for Clam Chowder first"


def test_the_box_off_keeps_the_recipe_first():
    if lupa is None:
        return
    lua = chowder_game()
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("have off")')
    held(lua, bags={FIN: 6, LEG: 9, SPICES: 7}, skill=120)
    v = verdict(lua)
    assert v["text"] == "Buy the recipe for Clam Chowder first" and v["aside"] is None, v


# ---- known recipes off the route, from the profession panel's own list --------------------------------------------------------
LONGJAW, EGG, SPELL_LONGJAW, SPELL_OMELET, SPELL_CLAMTHING, SPELL_EGGTHING, SPELL_TRANSMUTE = 6289, 3685, 6503, 3376, 9001, 9002, 9003


def offroute_doc() -> dict:
    """The fetched route's shape with nothing of the soup or the cake in it: Blood Sausage to 90, Longjaw Mud Snapper to 101, Clam
    Chowder 101 to 134 (a scroll bought; Dig Rat Stew and Crispy Lizard Tail its next-best), then Curiously Tasty Omelet to 150,
    which takes Raptor Eggs (the house's) and Hot Spices (a vendor's)."""
    doc = chowder_doc()
    plan = doc["plans"]["cooking-trainer"]
    plan["steps"][1] = {"from": 90, "to": 101, "recipe": "Longjaw Mud Snapper", "spell": SPELL_LONGJAW, "crafts": 11, "uses": [[LONGJAW, 1]],
                        "makes": [4592, 1], "per": [1] * 11, "buy": [LONGJAW], "craft": []}
    plan["steps"].append({"from": 134, "to": 150, "recipe": "Curiously Tasty Omelet", "spell": SPELL_OMELET, "crafts": 16, "uses": [[EGG, 1], [SPICES, 1]],
                          "makes": [3665, 1], "per": [1] * 16, "buy": [EGG, SPICES], "craft": []})
    plan["target"] = 150
    plan["buy"].update({str(LONGJAW): [60, "ah"], str(EGG): [80, "ah"]})
    doc["items"].update({str(LONGJAW): "Raw Longjaw Mud Snapper", str(EGG): "Raptor Egg", "4592": "Longjaw Mud Snapper", "3665": "Curiously Tasty Omelet"})
    return doc


PANEL = f"""
  ProfessionsFrame = {{ CraftingPage = {{ CreateAllButton = CreateFrame("Button") }} }}
  names = {{ [{SPELL_SOUP}] = "Murloc Fin Soup", [{SPELL_CAKE}] = "Gooey Spider Cake", [{SPELL_CLAMTHING}] = "Clam Thing",
            [{SPELL_EGGTHING}] = "Egg Thing", [{SPELL_TRANSMUTE}] = "Transmute: Fins to Legs", [{SPELL_SAUSAGE}] = "Blood Sausage" }}
  schematic = {{ [{SPELL_SOUP}] = {{ {{ {FIN}, 2 }}, {{ {SPICES}, 1 }} }}, [{SPELL_CAKE}] = {{ {{ {LEG}, 2 }}, {{ {SPICES}, 1 }} }},
                [{SPELL_CLAMTHING}] = {{ {{ {CLAM}, 1 }} }}, [{SPELL_EGGTHING}] = {{ {{ {EGG}, 1 }}, {{ {SPICES}, 1 }} }},
                [{SPELL_TRANSMUTE}] = {{ {{ {FIN}, 1 }} }} }}
  cooldown = {{}}                    -- cooldown[spell] = seconds left, as GetRecipeCooldown gives it
  for spell in pairs(names) do learned[spell] = true; colour[spell] = 0 end
  colour[{SPELL_SAUSAGE}] = nil
  C_TradeSkillUI.GetAllRecipeIDs = function() local out = {{}}; for spell in pairs(names) do table.insert(out, spell) end; table.sort(out); return out end
  C_TradeSkillUI.GetRecipeInfo = function(id) return {{ recipeID = id, name = names[id], learned = learned[id] or false, relativeDifficulty = colour[id] }} end
  C_TradeSkillUI.GetRecipeSchematic = function(id)
    local slots = {{}}
    for _, u in ipairs(schematic[id] or {{}}) do table.insert(slots, {{ reagents = {{ {{ itemID = u[1] }} }}, quantityRequired = u[2] }}) end
    return {{ reagentSlotSchematics = slots }}
  end
  C_TradeSkillUI.GetRecipeCooldown = function(id) return cooldown[id] end
"""


def panel_game():
    lua = game(offroute_doc())
    lua.execute(f"learned[{SPELL_TAIL}] = true" + PANEL)
    return lua


def panel_verdict(lua) -> dict:
    """The Make button's verdict with the profession panel open (the client's recipe list there)."""
    lua.execute('Fire("TRADE_SKILL_SHOW")')
    v = lua.eval("ForeverWowCraftMake.verdict")
    return {"text": strip(v.text), "note": strip(v.note), "tip": [strip(t) for t in v.tip.values()], "spell": v.spell, "to": v.to,
            "aside": strip(v.aside.text) if v.aside else None}


def test_a_known_orange_recipe_off_the_route_is_made_from_the_bags_before_the_recipe_is_bought():
    """The second report on the fetched route's shape: Clam Chowder not learned, a scroll to buy; the bags hold 6 fins, 9 legs and
    7 Hot Spices; the panel lists the soup and the cake, known and orange, neither on the route. The cakes first (4 crafts to the
    soups' 3), then the soups, then the recipe; the purchase is the arrow's note meanwhile. Hot Spices, which the omelets later take,
    are a vendor's and not held back."""
    if lupa is None:
        return
    lua = panel_game()
    held(lua, bags={FIN: 6, LEG: 9, SPICES: 7}, skill=120)
    v = panel_verdict(lua)
    assert v["text"] == "Make 4 Gooey Spider Cake" and v["spell"] == SPELL_CAKE and v["to"] == 134, v
    assert "Using your 8 Gooey Spider Leg and 4 Hot Spices: Gooey Spider Cake is not on the route but still gives points: made from your bags, nothing to fetch or buy." in v["tip"], v["tip"]
    assert v["tip"][-2:] == ["Then buy the recipe for Clam Chowder (the arrow's note).", "Click: makes 4, stopping at skill 134."], v["tip"]
    assert v["aside"] == "Then buy the recipe for Clam Chowder" and v["note"] == "Using your 8 Gooey Spider Leg and 4 Hot Spices"
    held(lua, bags={FIN: 6, LEG: 1, SPICES: 3}, skill=124)
    v = panel_verdict(lua)
    assert v["text"] == "Make 3 Murloc Fin Soup" and v["aside"] == "Then buy the recipe for Clam Chowder", v
    held(lua, bags={LEG: 1}, skill=127)
    assert panel_verdict(lua)["text"] == "Buy the recipe for Clam Chowder first"
    # the panel closed (the background pass's verdict): the character's record of the panel answers, the same verdict
    held(lua, bags={FIN: 6, LEG: 9, SPICES: 7}, skill=120)
    assert verdict(lua)["text"] == "Make 4 Gooey Spider Cake"


def test_only_orange_and_yellow_known_recipes_orange_first_and_none_cooling_down():
    if lupa is None:
        return
    lua = panel_game()
    held(lua, bags={FIN: 6, LEG: 9, SPICES: 7}, skill=120)
    lua.execute(f"colour[{SPELL_CAKE}] = 1")                                       # the cake yellow: the orange soup first, though fewer
    assert panel_verdict(lua)["text"] == "Make 3 Murloc Fin Soup"
    lua.execute(f"colour[{SPELL_SOUP}] = 2; ns.HaveChanged()")                      # the soup green: never off the route; the yellow cake
    assert panel_verdict(lua)["text"] == "Make 4 Gooey Spider Cake"
    lua.execute(f"colour[{SPELL_CAKE}] = 3; ns.HaveChanged()")                      # and grey: nothing
    assert panel_verdict(lua)["text"] == "Buy the recipe for Clam Chowder first"
    lua.execute(f"colour[{SPELL_SOUP}] = 0; colour[{SPELL_CAKE}] = 0; cooldown[{SPELL_CAKE}] = 3600; ns.HaveChanged()")
    assert panel_verdict(lua)["text"] == "Make 3 Murloc Fin Soup"                   # the cake cooling down: passed over
    held(lua, bags={FIN: 9}, skill=120)                                                # a transmute, by its name, never (the soup lacks spices)
    assert panel_verdict(lua)["text"] == "Buy the recipe for Clam Chowder first"
    lua.execute(f'names[{SPELL_TRANSMUTE}] = "Fin Thing"; ns.HaveChanged()')        # named otherwise, it would be made
    assert panel_verdict(lua)["text"] == "Make 9 Fin Thing"
    lua.execute(f"GetSpellBaseCooldown = function(id) return id == {SPELL_TRANSMUTE} and 3600000 or 0, 0 end; ns.HaveChanged()")
    assert panel_verdict(lua)["text"] == "Buy the recipe for Clam Chowder first"   # unless the client says it has a cooldown at all


def test_a_known_recipe_that_burns_what_the_route_needs_is_passed_over():
    """Clam Meat (the stretch's own, bought at the house) and Raptor Eggs (the omelets', later) are held back; the Hot Spices are not."""
    if lupa is None:
        return
    lua = panel_game()
    held(lua, bags={CLAM: 10, EGG: 10, SPICES: 10}, skill=120)
    assert panel_verdict(lua)["text"] == "Buy the recipe for Clam Chowder first"
    held(lua, bags={CLAM: 10, EGG: 10, SPICES: 10, FIN: 2}, skill=120)
    assert panel_verdict(lua)["text"] == "Make 1 Murloc Fin Soup"


def test_the_box_off_keeps_known_recipes_off_the_route_out():
    if lupa is None:
        return
    lua = panel_game()
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("have off")')
    held(lua, bags={FIN: 6, LEG: 9, SPICES: 7}, skill=120)
    assert panel_verdict(lua)["text"] == "Buy the recipe for Clam Chowder first"


# ---- the panel's list remembered: the same answer with the panel closed and after a reload --------------------------------------
def lua_literal(value) -> str:
    """A Lua value as Lua source: the saved file the game writes at a logout and reads at the next login."""
    if lupa.lua_type(value) == "table":
        return "{ " + " ".join(f"[{lua_literal(k)}] = {lua_literal(v)}," for k, v in value.items()) + " }"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


CLOSED = """
  C_TradeSkillUI.GetAllRecipeIDs = nil                                  -- the panel closed: the client lists nothing
  C_TradeSkillUI.GetRecipeInfo = function(id) return nil end            -- and says nothing of a recipe
  C_TradeSkillUI.GetRecipeSchematic = nil
"""


def reloaded(lua):
    """A /reload: a fresh Lua with the saved variables carried over, the panel not opened this session."""
    saved = "FWCS_DB = " + lua_literal(lua.eval("FWCS_DB"))
    fresh = _game(offroute_doc(), saved=saved)
    fresh.execute(GAME + CLOSED)
    return fresh


def test_what_the_panel_listed_is_remembered_closed_and_after_a_reload():
    if lupa is None:
        return
    lua = panel_game()
    held(lua, bags={FIN: 6, LEG: 9, SPICES: 7}, skill=120)
    shown = panel_verdict(lua)
    assert shown["text"] == "Make 4 Gooey Spider Cake", shown
    rec = lua.eval(f'FWCS_DB.__chars["Stonespine|Thrallson"].learned[{COOKING}]')
    assert rec.skill == 120 and len(rec.list) == 5                                     # every learned recipe, whatever its colour
    cake = [r for r in rec.list.values() if r.spell == SPELL_CAKE][0]
    assert (cake.colour, cake.name, cake.uses[1][1], cake.uses[1][2], cake.cd) == ("optimal", "Gooey Spider Cake", LEG, 2, None)
    assert [r.cd for r in rec.list.values() if r.spell == SPELL_TRANSMUTE] == [True]
    # the panel closed, the client silent: the same words, the same note, the same aside
    lua.execute(CLOSED)
    closed = verdict(lua)
    assert (closed["text"], closed["note"], closed["aside"]) == (shown["text"], shown["note"], shown["aside"]), closed
    # a reload, the panel not opened since; the arrow cleared first, so that what it says after is the background pass's own
    lua.execute('FWCS_DB.__chars["Stonespine|Thrallson"].arrow = nil')
    fresh = reloaded(lua)
    fresh.execute("IsPlayerSpell = function(id) return learned[id] == true end")
    held(fresh, bags={FIN: 6, LEG: 9, SPICES: 7}, skill=120)
    again = verdict(fresh)
    assert (again["text"], again["note"], again["aside"]) == (shown["text"], shown["note"], shown["aside"]), again
    fresh.execute('Fire("PLAYER_ENTERING_WORLD"); RunTimers(); RunTimers()')
    arrow = fresh.eval('FWCS_DB.__chars["Stonespine|Thrallson"].arrow')
    assert (arrow.title, arrow.note) == ("Make 4 Gooey Spider Cake", "Using your 8 Gooey Spider Leg and 4 Hot Spices")
    # the bags' counts are the client's, now: the legs gone, the soups
    held(fresh, bags={FIN: 6, LEG: 1, SPICES: 3}, skill=120)
    assert verdict(fresh)["text"] == "Make 3 Murloc Fin Soup"


def test_no_record_yet_says_to_open_the_window_once():
    if lupa is None:
        return
    lua = game(offroute_doc())
    lua.execute(f"learned[{SPELL_TAIL}] = true")                                      # the panel never opened: no record
    held(lua, bags={FIN: 6, LEG: 9, SPICES: 7}, skill=120)
    v = verdict(lua)
    assert v["text"] == "Buy the recipe for Clam Chowder first", v
    assert v["tip"].count("Open your Cooking window once so the addon can see what your bags can make.") == 1, v["tip"]
    # nothing said where the bags make the stretch's own recipe
    lua.execute(f"learned[{SPELL_CHOWDER}] = true")
    held(lua, bags={CLAM: 5, MILK: 5, MILD: 5}, skill=120)
    v = verdict(lua)
    assert v["text"] == "Make 5 Clam Chowder" and not any("Open your" in t for t in v["tip"]), v


def test_a_remembered_recipe_with_a_cooldown_or_seen_at_another_skill():
    """From the record: never one with a cooldown; seen at another skill, only where the route's numbers show it still orange or
    yellow (its `at`: the cake, listed as a next-best of a later stretch), else unknown."""
    if lupa is None:
        return
    lua = panel_game()
    held(lua, bags={FIN: 6, LEG: 9, SPICES: 7}, skill=120)
    assert panel_verdict(lua)["text"] == "Make 4 Gooey Spider Cake"
    lua.execute(CLOSED)
    rec = f'FWCS_DB.__chars["Stonespine|Thrallson"].learned[{COOKING}]'
    lua.execute(f"for _, r in ipairs({rec}.list) do if r.spell == {SPELL_CAKE} then r.cd = true end end")
    assert verdict(lua)["text"] == "Make 3 Murloc Fin Soup"                            # the cake marked with a cooldown: not from the record
    lua.execute(f"for _, r in ipairs({rec}.list) do r.cd = nil end")
    held(lua, bags={FIN: 6, LEG: 9, SPICES: 7}, skill=121)                            # a point since the record, the panel not opened
    assert verdict(lua)["text"] == "Buy the recipe for Clam Chowder first"            # neither has an `at` in the route: unknown
    plan = 'FWCS_PLANS["stonespine--horde"].plans["cooking-trainer"]'
    lua.execute(f'{plan}.steps[4].alt = {{ }}; {plan}.steps[4].alt[1] = {{ recipe = "Gooey Spider Cake", spell = {SPELL_CAKE}, uses = {{ {{ {LEG}, 2 }}, {{ {SPICES}, 1 }} }},'
                f' per = {{}}, crafts = 1, at = {{ 110, 130, 150, 170 }} }}; ns.HaveChanged()')
    assert verdict(lua)["text"] == "Make 4 Gooey Spider Cake"                         # the route's numbers: orange at 121
    lua.execute(f'{plan}.steps[4].alt[1].at = {{ 90, 100, 115, 140 }}; ns.HaveChanged()')
    assert verdict(lua)["text"] == "Buy the recipe for Clam Chowder first"            # green at 121 by them: not offered


def test_the_box_off_keeps_the_record_out():
    if lupa is None:
        return
    lua = panel_game()
    held(lua, bags={FIN: 6, LEG: 9, SPICES: 7}, skill=120)
    assert panel_verdict(lua)["text"] == "Make 4 Gooey Spider Cake"
    lua.execute(CLOSED + 'SlashCmdList.FOREVERWOWCRAFTSCANNER("have off")')
    v = verdict(lua)
    assert v["text"] == "Buy the recipe for Clam Chowder first" and not any("Open your" in t for t in v["tip"]), v


if __name__ == "__main__":
    if lupa is None:
        print("skipped: no Lua here (pip install lupa); tests/lua_check.py still reads the addon's files")
        sys.exit(0)
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)

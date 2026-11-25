"""A stand-in from an earlier stretch keeps its colour (23 Nov 2026). A leatherworker at skill 140, "Use what I already have first"
ticked, the 140 to 180 stretch Raptor Hide Harness (its pattern not learned), 100 Heavy Leather in the bags: Hillman's Cloak, the
125 to 140 stretch before, would still give points (yellow at 145) and the bags make 20 of them. The arrow said "Buy the recipe
for Raptor Hide Harness first": the cloak's chance came from its own stretch's `per`, which ends at 139, and from `at`, which only
a next-best carried; with the profession window closed and the remembered list taken at skill 139 (every skill-up makes it stale)
the client's colour was missing too, and the cloak was dropped.

Now a step of the document carries `at` ([learn, yellow, green, grey]) for its own recipe, and the addon takes a stand-in's
colour from it, as it does from a next-best's: orange below at[2], yellow below at[3], green below at[4], grey from at[4]. The
client's own colour, when it gives one, still wins; a document without a step's `at` (an older one) behaves as before.

Needs a Lua: `pip install lupa`; without it this says so and passes.
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_bags_first import CLOSED, GAME, PANEL, strip  # noqa: E402
from test_ingame import _game, lupa  # noqa: E402
from test_plans import document  # noqa: E402

LEATHERWORKING = 165
HEAVY, THREAD, CLOAK_ITEM, HARNESS_ITEM = 4234, 2321, 4237, 4239
SPELL_CLOAK, SPELL_HARNESS = 3760, 4096
AT = [100, 145, 155, 165]            # Hillman's Cloak: learned 100, yellow 145, green 155, grey 165


def leather_doc(with_at=True) -> dict:
    doc = copy.deepcopy(document())
    doc["variants"] = [["trainer", "Skill-up", "plans", "skill"]]
    doc["focus"] = [["profit", "Profit"], ["skill", "Skill-up"]]
    cloak = {"from": 125, "to": 140, "recipe": "Hillman's Cloak", "spell": SPELL_CLOAK, "crafts": 15, "uses": [[HEAVY, 5], [THREAD, 2]],
             "makes": [CLOAK_ITEM, 1], "per": [1] * 15, "buy": [HEAVY, THREAD], "craft": []}
    if with_at:
        cloak["at"] = AT
    harness = {"from": 140, "to": 180, "recipe": "Raptor Hide Harness", "spell": SPELL_HARNESS, "crafts": 40, "uses": [[HEAVY, 4], [THREAD, 2]],
               "makes": [HARNESS_ITEM, 1], "per": [1] * 40, "buy": [HEAVY, THREAD], "craft": [], "learn": [4296, 500]}
    if with_at:
        harness["at"] = [140, 160, 180, 200]
    doc["plans"]["leatherworking-trainer"] = {
        "profession": "leatherworking", "skill_line": LEATHERWORKING, "variant": "trainer", "start": 125, "target": 180, "net": -20000,
        "spent": 20000, "sold": 0, "gaps": [], "steps": [cloak, harness], "made": {}, "sell": {}, "disenchant": [],
        "buy": {str(HEAVY): [100, "ah"], str(THREAD): [20, "vendor"]}}
    doc["items"].update({str(HEAVY): "Heavy Leather", str(THREAD): "Fine Thread", str(CLOAK_ITEM): "Hillman's Cloak",
                         str(HARNESS_ITEM): "Raptor Hide Harness", "4296": "Pattern: Raptor Hide Harness"})
    return doc


def leather_game(with_at=True):
    """The window closed, the client giving no colour; the character knows the cloak (in the remembered list, taken at skill 139)
    and not the harness."""
    lua = _game(leather_doc(with_at))
    lua.execute(GAME + PANEL + CLOSED + f"""
      C_TradeSkillUI.GetBaseProfessionInfo = function() return {{ professionID = {LEATHERWORKING}, skillLevel = skill }} end
      learned = {{ [{SPELL_CLOAK}] = true }}
      ns.Settings().variant = "plans-skill"
      ns.inv.Char().learned = ns.inv.Char().learned or {{}}
      ns.inv.Char().learned[{LEATHERWORKING}] = {{ skill = 139, t = 1, list = {{ {{ spell = {SPELL_CLOAK}, colour = "optimal",
        name = "Hillman's Cloak", uses = {{ {{ {HEAVY}, 5 }}, {{ {THREAD}, 2 }} }} }} }} }}
    """)
    return lua


def verdict(lua, skill, bags):
    slots = ", ".join(f"{{ {i}, {n} }}" for i, n in bags.items())
    lua.execute(f"skill = {skill}; ns.inv.Char().skills[{LEATHERWORKING}] = skill; bags[0] = {{ {slots} }}; ns.inv.Char().mailed = nil; "
                f"Fire('BAG_UPDATE_DELAYED'); RunTimers(); ns.inv.Char().items = {{}}; ns.HaveChanged()")
    v = lua.eval(f'ns.verdict.Verdict({{ open = {{ id = {LEATHERWORKING}, rank = skill, max = 225 }}, profession = "leatherworking" }})')
    return strip(v.text)


def test_the_cloak_of_an_earlier_stretch_stands_in_by_the_steps_own_colours():
    if lupa is None:
        return
    lua = leather_game()
    # skill 140, the cloak orange by its `at` (yellow only from 145): all 100 leather and 40 thread make 20 crafts
    assert verdict(lua, 140, {HEAVY: 100, THREAD: 40}) == "Make 20 Hillman's Cloak"
    # no thread: the vendor's goods for the cloak are the verdict, as for any stand-in
    assert verdict(lua, 140, {HEAVY: 100}) == "Buy 40 Fine Thread from a vendor, for 20 Hillman's Cloak"
    # yellow at 150 (below green 155) still offered; grey from 165 never
    assert verdict(lua, 150, {HEAVY: 100, THREAD: 40}).startswith("Make ")
    assert verdict(lua, 165, {HEAVY: 100, THREAD: 40}) == "Buy the recipe for Raptor Hide Harness first"


def test_the_clients_colour_still_wins_and_an_older_document_behaves_as_before():
    if lupa is None:
        return
    lua = leather_game()
    # the remembered list taken at this skill says grey for the cloak: the client's word beats the route's numbers
    lua.execute(f'ns.inv.Char().learned[{LEATHERWORKING}].list[1].colour = "trivial"; ns.inv.Char().learned[{LEATHERWORKING}].skill = 140')
    assert verdict(lua, 140, {HEAVY: 100, THREAD: 40}) == "Buy the recipe for Raptor Hide Harness first"
    old = leather_game(with_at=False)           # no `at` on the steps: the cloak is dropped, as in 1.8.6
    assert verdict(old, 140, {HEAVY: 100, THREAD: 40}) == "Buy the recipe for Raptor Hide Harness first"


if __name__ == "__main__":
    if lupa is None:
        print("skipped: no Lua here (pip install lupa)")
        sys.exit(0)
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)

"""One ranking of the recipes that stand in (23 Nov 2026). A leatherworker at skill 140 on the skill-up route, "Use what I already
have first" ticked, 100 Heavy Leather in the bags, no Fine Thread, the pattern for Raptor Hide Harness (the 140 to 180 stretch)
not learned; Hillman's Cloak (5 leather and 2 thread, the route's stretch before) and Heavy Armor Kit (5 leather and 1 thread, not on
the route) both known and orange. The vendor-gap path (VendorGapVerdict) ranked by colour, then the most crafts the held goods and
a vendor's make, then by NAME: the kit ("Buy 20 Fine Thread from a vendor, for 20 Heavy Armor Kit"). The bags path (BagsVerdict) took
the route's own recipes first, in the route's order, and the record's after: with the 20 thread bought, "Make 10 Hillman's Cloak",
leaving 50 leather unused. The player was sent to buy for one recipe and told to make another.

Now one ranking (Verdict.lua, Ranked) serves both: orange before yellow, the recipe the last trip was for while it still qualifies,
the most expected skill points from what is held after the trip, the lowest net cost (what is still to buy, minus what a vendor pays
for the products, the document's recipes table), the fewer items to buy, the lower spell id.

Needs a Lua: `pip install lupa`; without it this says so and passes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_ingame import lupa  # noqa: E402
from test_list_follows_the_arrow import game, stage  # noqa: E402
from test_stand_in_colours import HEAVY, LEATHERWORKING, SPELL_CLOAK, THREAD  # noqa: E402

SPELL_KIT = 3780


def known_game(cloak_pays=None):
    """The list-follows-the-arrow game, with the kit known too (the record taken at skill 140: the client's colours stand), and, when
    given, what a vendor pays for a cloak in the document's recipes table ([cost, worth, sells, chance, vendor pays])."""
    lua = game()
    lua.execute(f"""
      local rec = ns.inv.Char().learned[{LEATHERWORKING}]
      rec.skill = 140
      table.insert(rec.list, {{ spell = {SPELL_KIT}, colour = "optimal", name = "Heavy Armor Kit", uses = {{ {{ {HEAVY}, 5 }}, {{ {THREAD}, 1 }} }} }})
      learned[{SPELL_KIT}] = true
    """)
    if cloak_pays is not None:
        lua.execute(f"ns.inv.House().recipes = {{ [{SPELL_CLOAK}] = {{ 0, 0, 0, 1, {cloak_pays} }} }}")
    return lua


def test_the_recipe_the_trip_is_for_is_the_recipe_made_and_listed():
    if lupa is None:
        return
    lua = known_game()
    # no thread: both make 20 crafts and 20 points; the kit buys 20 thread, the cloak 40: the kit, the cheaper trip
    text, arrow, title, rows = stage(lua, {HEAVY: 100})
    assert text == "Buy 20 Fine Thread from a vendor, for 20 Heavy Armor Kit", text
    assert arrow == "Buy 20 Fine Thread from a vendor, for 20 Heavy Armor Kit;\nusing your 100 Heavy Leather", arrow
    assert title == "Heavy Armor Kit, from your 100 Heavy Leather, needs", title
    assert rows[0] == ("Fine Thread", "need 20, have 0", "Buy 20"), rows
    # the thread bought: the bags make 10 cloaks or 20 kits, and the kit is what the thread was bought for
    text, _, title, _ = stage(lua, {HEAVY: 100, THREAD: 20})
    assert text == "Make 20 Heavy Armor Kit", text
    assert title == "Heavy Armor Kit: nothing to buy", title


def test_equal_points_go_to_the_lowest_net_cost_a_vendors_pay_included():
    if lupa is None:
        return
    lua = known_game(cloak_pays=1027)
    # 10 leather: 2 crafts of either, 2 points of either (the cloak is orange to 145); 2 cloaks are worth 2054 to a vendor, more than
    # the 4 thread cost (20 copper each) against the kit's 2
    text, _, title, _ = stage(lua, {HEAVY: 10})
    assert text == "Buy 4 Fine Thread from a vendor, for 2 Hillman's Cloak", text
    assert title == "Hillman's Cloak, from your 10 Heavy Leather, needs", title
    # the thread bought: the cloak is what it was for, and the list says so
    text, _, title, _ = stage(lua, {HEAVY: 10, THREAD: 4})
    assert text == "Make 2 Hillman's Cloak", text
    assert title == "Hillman's Cloak: nothing to buy", title
    # without a vendor's pay in the document the kit's trip is the cheaper (2 thread), at both stages
    lua = known_game()
    text, _, _, _ = stage(lua, {HEAVY: 10})
    assert text == "Buy 2 Fine Thread from a vendor, for 2 Heavy Armor Kit", text
    text, _, _, _ = stage(lua, {HEAVY: 10, THREAD: 2})
    assert text == "Make 2 Heavy Armor Kit", text


def test_a_recipe_the_route_knows_less_of_is_never_ahead_for_it():
    if lupa is None:
        return
    # 100 leather, no thread. The cloak has the route's curve (yellow from 145), the kit none: no points are compared, the crafts tie
    # at 20 and the net cost decides: the cloak buys 40 thread (20 copper each, the fixture's price) = 800 and is paid 20 x 1027 = 20540
    # (-19740); the kit buys 20 thread = 400 and is paid nothing (400): the cloak, at both stages
    lua = known_game(cloak_pays=1027)
    text, arrow, title, _ = stage(lua, {HEAVY: 100})
    assert text == "Buy 40 Fine Thread from a vendor, for 20 Hillman's Cloak", text
    assert arrow == "Buy 40 Fine Thread from a vendor, for 20 Hillman's Cloak;\nusing your 100 Heavy Leather", arrow
    assert title == "Hillman's Cloak, from your 100 Heavy Leather, needs", title
    text, _, title, _ = stage(lua, {HEAVY: 100, THREAD: 40})
    assert text == "Make 20 Hillman's Cloak", text
    assert title == "Hillman's Cloak: nothing to buy", title
    # with no pay in the document the kit's trip is the cheaper, and it is the kit at both stages
    lua = known_game()
    text, _, _, _ = stage(lua, {HEAVY: 100})
    assert text == "Buy 20 Fine Thread from a vendor, for 20 Heavy Armor Kit", text
    # thread for 10 cloaks or 20 kits and no trip: the crafts the holdings allow decide, the kit's 20
    lua = known_game(cloak_pays=1027)
    text, _, _, _ = stage(lua, {HEAVY: 100, THREAD: 20})
    assert text == "Make 20 Heavy Armor Kit", text


def test_where_both_have_curves_the_points_decide():
    if lupa is None:
        return
    # the kit listed on the route too, as the cloak's next-best, orange to 165 (the cloak yellow from 145): 20 points of 20 crafts to the
    # cloak's 15.8, and points come before a vendor's pay (20540 for the cloaks)
    lua = known_game(cloak_pays=1027)
    lua.execute(f"""
      local plan = ns.inv.House().plans["leatherworking-trainer"]
      plan.steps[1].alt = {{ {{ recipe = "Heavy Armor Kit", spell = {SPELL_KIT}, uses = {{ {{ {HEAVY}, 5 }}, {{ {THREAD}, 1 }} }},
                               at = {{ 100, 165, 175, 185 }}, per = {{}}, crafts = 0 }} }}
      ns.HaveChanged()
    """)
    text, _, _, _ = stage(lua, {HEAVY: 100})
    assert text == "Buy 20 Fine Thread from a vendor, for 20 Heavy Armor Kit", text
    text, _, _, _ = stage(lua, {HEAVY: 100, THREAD: 20})
    assert text == "Make 20 Heavy Armor Kit", text


def test_the_recipe_a_trip_was_for_stays_while_it_can_be_made():
    if lupa is None:
        return
    lua = known_game(cloak_pays=1027)
    text, _, _, _ = stage(lua, {HEAVY: 10})
    assert text == "Buy 4 Fine Thread from a vendor, for 2 Hillman's Cloak", text
    # 2 thread bought only, the kit would now tie (2 crafts, no thread to buy, cheaper): the cloak (1 craft) is still what it was for
    text, _, _, _ = stage(lua, {HEAVY: 10, THREAD: 2})
    assert text == "Make 1 Hillman's Cloak", text
    # a fresh memory (a reload) and the same bags: the ranking alone says the kit (2 points to the cloak's 1)
    lua = known_game(cloak_pays=1027)
    text, _, _, _ = stage(lua, {HEAVY: 10, THREAD: 2})
    assert text == "Make 2 Heavy Armor Kit", text


if __name__ == "__main__":
    if lupa is None:
        print("skipped: no Lua here (pip install lupa)")
        sys.exit(0)
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)

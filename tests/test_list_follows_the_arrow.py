"""The shopping list follows the arrow (23 Nov 2026). A leatherworker at skill 140, "Use what I already have first" ticked, 100 Heavy
Leather in the bags, no Fine Thread, the pattern for Raptor Hide Harness (the 140 to 180 stretch) not learned, Hillman's Cloak known
and orange: the arrow said "Buy 20 Fine Thread from a vendor; using your 100 Heavy Leather" and, at the vendor, the list showed the
harness's needs (the recipe, leather, and the thread last) under the harness's title. PR 286 meant the list to hold the cloak's goods
first; it did not in the game. After the thread was bought the Make button said to make the cloak and the list went back to "Buy 20".

Why PR 286 did not show in the game: the list worked out the stand-in itself (a second replay of the chain, GapShopping), and with the
profession window closed (the player is at a vendor) it did so without the spellbook and the character's record of what he knows that
the arrow's pass (Craft.lua, Standing) has: the cloak was "not known", no stand-in, the harness's list. Its test had the panel open.

Now the list is built from the verdict's own decision (ns.craft.Standing, as the arrow is; the verdict carries `listing`): at a vendor
for the cloak's goods the title names the cloak and the rows are what is still to buy for it; where the cloak is made from the bags
the list says nothing is to buy for it, then a "Then:" heading row and the route step's needs after; any other verdict (the step's
own recipe, its pattern) is the step's list as before. At an open merchant the rows it sells come first. The arrow names the recipe.

Needs a Lua: `pip install lupa`; without it this says so and passes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_bags_first import strip  # noqa: E402
from test_ingame import lupa  # noqa: E402
from test_stand_in_colours import HEAVY, LEATHERWORKING, SPELL_HARNESS, THREAD, leather_game  # noqa: E402

THEN = "Then: Raptor Hide Harness, skill 140 to 180, needs"
PATTERN = "Pattern: Raptor Hide Harness (recipe)"


def game():
    """The window closed (a player at a vendor), the spellbook asked as the game's is, the merchant open and selling Fine Thread."""
    lua = leather_game()
    lua.execute(f"""
      IsPlayerSpell = function(spell) return learned[spell] == true end
      function GetSkillLineInfo(i) if i == 1 then return "Professions", true end return "Leatherworking", false, false, skill, 0, 0, 225 end
      ns.inv.Char().making = "leatherworking"
      wares = {{ {THREAD} }}
      function GetMerchantNumItems() return #wares end
      function GetMerchantItemLink(i) return "|cffffffff|Hitem:" .. wares[i] .. "::::::::1:::::::|h[x]|h|r" end
      function GetMerchantItemInfo(i) return "Fine Thread", "tex", 20, 1, -1, true, true end
      function GetMerchantItemMaxStack(i) return 20 end
      function BuyMerchantItem(i, n) end
      MerchantFrame = CreateFrame("Frame")
    """)
    return lua


def stage(lua, bags, skill=140, bank=None):
    """The bags (and the bank) now, the arrow's pass run, the merchant opened again: the arrow's text and its note, the list's title,
    and its rows as shown: [(name or heading, need text, the Buy button's text or None)]."""
    slots = ", ".join(f"{{ {i}, {n} }}" for i, n in bags.items())
    items = ", ".join(f"[{i}] = {{ 0, {n}, 0, 0 }}" for i, n in (bank or {}).items())
    lua.execute(f"skill = {skill}; ns.inv.Char().skills[{LEATHERWORKING}] = skill; bags[0] = {{ {slots} }}; ns.inv.Char().mailed = nil; "
                f"Fire('BAG_UPDATE_DELAYED'); RunTimers(); ns.inv.Char().items = {{ {items} }}; ns.HaveChanged(); "
                "Fire('MERCHANT_CLOSED'); if ns.HideShopping then ns.HideShopping() end; Fire('MERCHANT_SHOW'); Fire('BAG_UPDATE_DELAYED')")
    # the arrow's pass with the window closed (Craft.lua, Standing: the spellbook says what is learned); on a build without it, the verdict as given
    v = lua.eval('ns.craft.Standing and ns.craft.Standing("leatherworking")') or lua.eval(
        f'ns.verdict.Verdict({{ open = {{ id = {LEATHERWORKING}, rank = skill, max = 225 }}, profession = "leatherworking" }})')
    title = strip(lua.eval("ForeverWowCraftShop.title.text"))
    rows = []
    for i in range(1, 13):
        e = f"ForeverWowCraftShop.rows[{i}]"
        if lua.eval(f"{e}.shown"):
            rows.append((strip(lua.eval(f"{e}.name.text")), strip(lua.eval(f"{e}.need.text")), lua.eval(f"{e}.buy.shown and {e}.buy.text or nil")))
    return strip(v.text), strip(v.arrowNote or ""), title, rows


def test_at_the_vendor_the_list_is_what_the_cloak_needs_and_what_the_arrow_says():
    if lupa is None:
        return
    lua = game()
    text, arrow, title, rows = stage(lua, {HEAVY: 100})
    assert text == "Buy 40 Fine Thread from a vendor, for 20 Hillman's Cloak", text
    assert arrow == "Buy 40 Fine Thread from a vendor, for 20 Hillman's Cloak;\nusing your 100 Heavy Leather", arrow
    assert title == "Hillman's Cloak, from your 100 Heavy Leather, needs", title
    # the cloak's thread first, a stack's Buy button; then the harness, set apart, with its own needs (the thread is not listed twice)
    assert rows[0] == ("Fine Thread", "need 40, have 0", "Buy 20"), rows
    assert rows[1] == (THEN, "", None), rows
    assert [r[0] for r in rows[2:]] == [PATTERN, "Heavy Leather"], rows


def test_once_the_thread_is_bought_the_list_says_nothing_is_due_and_the_harness_comes_after():
    if lupa is None:
        return
    lua = game()
    text, _, title, rows = stage(lua, {HEAVY: 100, THREAD: 40})
    assert text == "Make 20 Hillman's Cloak", text
    assert title == "Hillman's Cloak: nothing to buy", title                     # (with both goods named the title runs long, and drops them)
    assert rows[0] == (THEN, "", None), rows                                  # nothing due now: the first row is the "then" part
    # the harness's needs, the merchant's thread first (it may be stocked up for later), under the heading and not as the need of now
    assert rows[1] == ("Fine Thread", "need 80, have 40", "Buy 20"), rows
    assert [r[0] for r in rows[2:]] == [PATTERN, "Heavy Leather"], rows


def test_from_the_bank_the_list_is_the_cloaks_too():
    if lupa is None:
        return
    lua = game()
    text, _, title, rows = stage(lua, {THREAD: 40}, bank={HEAVY: 100})
    assert text == "Take 100 Heavy Leather from the bank", text
    assert title == "Hillman's Cloak, from your 100 Heavy Leather: nothing to buy", title
    assert rows[0] == (THEN, "", None), rows


def test_a_verdict_on_the_steps_own_recipe_is_the_steps_list_as_before():
    if lupa is None:
        return
    lua = game()
    # the cloak grey by 165: the step's pattern is the verdict, the step's own title, no heading row; the merchant's thread first
    # (the walk puts the pattern first), as at any open merchant
    text, _, title, rows = stage(lua, {HEAVY: 100}, skill=165)
    assert text == "Buy the recipe for Raptor Hide Harness first", text
    assert title == "Raptor Hide Harness, skill 165 to 180, needs", title
    assert [r[0] for r in rows] == ["Fine Thread", PATTERN], rows
    # the pattern learned, the goods in the bags: the step's own craft is made, and the list is its needs, as before
    lua.execute(f"learned[{SPELL_HARNESS}] = true")
    text, _, _, _ = stage(lua, {HEAVY: 100, THREAD: 40}, skill=165)
    assert text == "Make 15 Raptor Hide Harness", text
    lua.execute("__l = ns.craft.Shopping()")
    assert lua.eval("__l.title") == "Raptor Hide Harness, skill 165 to 180, needs" and lua.eval("#__l") == 0


if __name__ == "__main__":
    if lupa is None:
        print("skipped: no Lua here (pip install lupa)")
        sys.exit(0)
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)

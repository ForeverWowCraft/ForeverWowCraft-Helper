"""The arrow and the shopping list at a vendor agree (23 Nov 2026). A player's arrow said to buy Salt from a vendor, and the list
that opened at the vendor's window showed a pattern and some thread, "needs ... thread": two different answers.

Cause: the arrow's verdict (Verdict.lua, VendorGapVerdict) may send the player to a vendor for the goods of a recipe he knows that
still gives points with what he holds ("Use what I already have first"), while the list (ns.craft.Shopping) was only ever the route
step's own needs (ShoppingOf). The goods of the stand-in were on no list, so the vendor's window did not offer them.

Here: the cooking route's stretch is Clam Chowder (a scroll bought); the bags hold 9 Raw Fins, the known Murloc Fin Soup wants a
Hot Spices from a vendor with each pair of fins. The arrow says "Buy 4 Hot Spices from a vendor, for 4 Murloc Fin Soup"; the list must hold the spices,
the vendor's, first, as well as the route's own needs. Where the arrow says anything else, the list is the step's, as before.

Needs a Lua: `pip install lupa`; without it this says so and passes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_bags_first import FIN, LEG, SPICES, panel_game, panel_verdict, held  # noqa: E402
from test_ingame import lupa  # noqa: E402


def listed(lua):
    """The list the vendor's window shows: [(item, units, have, source)], and its title."""
    lua.execute("__list = ns.craft.Shopping()")
    rows = [(int(lua.eval(f"__list[{i}].item")), int(lua.eval(f"__list[{i}].units")), int(lua.eval(f"__list[{i}].have")), lua.eval(f"__list[{i}].source"))
            for i in range(1, int(lua.eval("#__list")) + 1) if lua.eval(f"__list[{i}].heading") is None]       # not the "Then:" heading row
    return rows, lua.eval("__list.title")


def test_the_goods_the_arrow_sends_to_a_vendor_for_are_on_the_list():
    if lupa is None:
        return
    lua = panel_game()
    held(lua, bags={FIN: 9}, skill=120)
    assert panel_verdict(lua)["text"] == "Buy 4 Hot Spices from a vendor, for 4 Murloc Fin Soup"
    rows, title = listed(lua)
    assert rows[0] == (SPICES, 4, 0, "vendor"), rows            # first: what the arrow says
    assert len(rows) > 1 and all(r[0] != SPICES for r in rows[1:]), rows   # the step's own needs follow, no item twice
    assert "needs" in title


def test_where_the_arrow_makes_something_the_list_is_the_steps_as_before():
    if lupa is None:
        return
    lua = panel_game()
    held(lua, bags={FIN: 6, LEG: 9, SPICES: 7}, skill=120)
    assert panel_verdict(lua)["text"] == "Make 4 Gooey Spider Cake"
    rows, _ = listed(lua)
    assert all(r[0] != SPICES for r in rows), rows
    held(lua, bags={LEG: 1}, skill=127)
    assert panel_verdict(lua)["text"] == "Buy the recipe for Clam Chowder first"
    rows, _ = listed(lua)
    assert all(r[0] != SPICES for r in rows), rows


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok" if lupa is not None else "skipped: pip install lupa")

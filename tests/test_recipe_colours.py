"""Recipe colours (14 Nov 2026): the skills at which the player's own profession window shows each learned recipe orange, yellow,
green or grey, kept for the whole account by spell (FWCS_DB.__colours, Verdict.lua NoteColours) and sent with the vendors met.

Held here: two looks at two skills make the lowest and highest skill of each colour; a window linked in chat records nothing; a skill
bonus other than 0, or a client that says nothing of one, records nothing; a colour where the kept bounds say it cannot be drops the
older pair; a recipe not learned is not recorded; a profession without a route is; a first look before the client's list loads is
tried again at the next refresh, a costly empty look at most once a second and once more by a timer; every skill point gained in a
Make run is looked at, while the button's verdict holds through the cast; a switch to another profession, its list not yet
followed, records nothing of the last one's list at the new rank; 1.8.2's table is started again once; nothing of the character
is in the table.

Needs a Lua: `pip install lupa`; without it this says so and passes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_bags_first import (COOKING, FIN, GAME, LEATHERWORKING, LEG, LINES, LW_LIST, PANEL, SPELL_CAKE, SPELL_EGGTHING,  # noqa: E402
                             SPELL_KIT, SPELL_SAUSAGE, SPELL_SOUP, SPELL_TAIL, SPICES, SWITCH, held, lua_literal, offroute_doc,
                             panel_game, panel_verdict, strip)
from test_ingame import _game, lupa  # noqa: E402

ALCHEMY = 171
BASE = """
  prof, mod = %d, 0
  C_TradeSkillUI.GetBaseProfessionInfo = function() return { professionID = prof, skillLevel = skill, skillModifier = mod } end
""" % COOKING


def game():
    lua = panel_game()
    lua.execute(BASE)
    return lua


def colours(lua) -> dict:
    """FWCS_DB.__colours as Python: {spell: {"o": (lo, hi), ..., "t": time}}."""
    table = lua.eval("FWCS_DB.__colours")
    if table is None:
        return {}
    return {spell: {k: (tuple(v.values()) if lupa.lua_type(v) == "table" else v) for k, v in row.items()} for spell, row in table.items()}


def look(lua, skill, **colour):
    """The window open at `skill`, the given recipes in the given colour (0 orange .. 3 grey)."""
    lua.execute("; ".join(f"colour[{spell}] = {c}" for spell, c in colour.items()) or "do end")    # before the skill moves: held's
    held(lua, skill=skill)                                                                          # bag event redraws the panel too
    panel_verdict(lua)


def test_two_looks_make_each_colours_lowest_and_highest_skill():
    if lupa is None:
        return
    lua = game()
    look(lua, 120)
    got = colours(lua)
    assert got[SPELL_CAKE]["o"] == (120, 120) and set(got[SPELL_CAKE]) == {"o", "t"}, got
    assert SPELL_SAUSAGE not in got                                         # no colour from the client: nothing
    look(lua, 125, **{str(SPELL_CAKE): 1})
    look(lua, 130, **{str(SPELL_CAKE): 1, str(SPELL_SOUP): 0})
    got = colours(lua)
    assert (got[SPELL_CAKE]["o"], got[SPELL_CAKE]["y"]) == ((120, 120), (125, 130)), got[SPELL_CAKE]
    assert got[SPELL_SOUP]["o"] == (120, 130) and "y" not in got[SPELL_SOUP]
    t = got[SPELL_CAKE]["t"]
    look(lua, 130, **{str(SPELL_CAKE): 1})                                  # the same again: nothing changes, t neither
    assert colours(lua)[SPELL_CAKE]["t"] == t


def test_a_contradiction_drops_the_older_pair():
    """A hotfix moved the cake up: orange at 131, above the yellow kept from 125: the yellow goes, the orange stretches to 131."""
    if lupa is None:
        return
    lua = game()
    look(lua, 120)
    look(lua, 125, **{str(SPELL_CAKE): 1})
    lua.execute('FWCS_DB.__colours[%d].t = 1' % SPELL_CAKE)
    look(lua, 131, **{str(SPELL_CAKE): 0})
    row = colours(lua)[SPELL_CAKE]
    assert row["o"] == (120, 131) and "y" not in row and row["t"] > 1, row
    look(lua, 135, **{str(SPELL_CAKE): 3})                                  # grey above every orange: no contradiction
    look(lua, 128, **{str(SPELL_CAKE): 2})                                  # green under the orange's highest: the orange goes
    row = colours(lua)[SPELL_CAKE]
    assert row["x"] == (135, 135) and row["g"] == (128, 128) and "o" not in row, row


def test_a_linked_window_a_bonus_or_no_word_of_one_records_nothing():
    if lupa is None:
        return
    lua = game()
    lua.execute("C_TradeSkillUI.IsTradeSkillLinked = function() return true, 'Someone' end")
    look(lua, 120)
    assert colours(lua) == {}
    lua.execute("C_TradeSkillUI.IsTradeSkillLinked = function() return false end; mod = 10")
    look(lua, 121)
    assert colours(lua) == {}                                               # a racial or item bonus on: which skill colours is unknown
    lua.execute("mod = nil")
    look(lua, 122)
    assert colours(lua) == {}                                               # no word of a bonus: the same
    lua.execute("mod = 0")
    look(lua, 123)
    assert colours(lua)[SPELL_CAKE]["o"] == (123, 123)


def test_only_learned_recipes_and_any_profession():
    if lupa is None:
        return
    lua = game()
    lua.execute(f"learned[{SPELL_EGGTHING}] = false; prof = {ALCHEMY}")      # a profession with no route: recorded all the same
    look(lua, 120)
    got = colours(lua)
    assert SPELL_EGGTHING not in got and got[SPELL_CAKE]["o"] == (120, 120), got
    assert lua.eval("ForeverWowCraftMake.verdict.text") == "No route for this profession"


CLOCK = "clock = 100; GetTime = function() return clock end; realLearned = learned"


def test_no_list_at_the_first_look_then_the_list_at_once():
    """The live game, 15 Nov 2026: at TRADE_SKILL_SHOW the client lists no recipe yet; the list comes a moment later with
    TRADE_SKILL_LIST_UPDATE, which moves neither the bags nor the skill (ns.HaveGen). A look at no list costs nothing and is not
    kept or held back: the colours are recorded at once."""
    if lupa is None:
        return
    lua = game()
    lua.execute(CLOCK + "; realIDs = C_TradeSkillUI.GetAllRecipeIDs; C_TradeSkillUI.GetAllRecipeIDs = function() return {} end")
    look(lua, 120)
    assert colours(lua) == {}
    lua.execute("C_TradeSkillUI.GetAllRecipeIDs = realIDs; clock = 100.05; Fire('TRADE_SKILL_LIST_UPDATE')")
    assert colours(lua)[SPELL_CAKE]["o"] == (120, 120), colours(lua)


def test_a_list_none_learned_then_the_flags_with_no_event_is_looked_at_again_by_a_timer():
    """The ids listed but none learned yet at the first look; the flags come 0.2 s later and no event follows: the look set a
    little over a second on (C_Timer) records them, once."""
    if lupa is None:
        return
    lua = game()
    lua.execute(CLOCK + "; learned = {}")
    look(lua, 120)                                                          # held runs the timers before the window opens
    assert colours(lua) == {} and len(lua.eval("timers")) == 1, lua.eval("timers")
    lua.execute("learned = realLearned; clock = 100.2")
    assert colours(lua) == {}
    lua.execute("clock = 101.1; RunTimers()")
    assert colours(lua)[SPELL_CAKE]["o"] == (120, 120), colours(lua)
    assert len(lua.eval("timers")) == 0                                     # recorded: nothing more set


def test_a_list_none_learned_is_looked_at_again_at_most_once_a_second():
    """Each look at a list with none learned costs a call per recipe: a refresh within a second of one is not looked at; one after
    it is. One timer for the change, window and skill, however many such looks."""
    if lupa is None:
        return
    lua = game()
    lua.execute(CLOCK + "; learned = {}")
    look(lua, 120)
    lua.execute("clock = 101.5; Fire('TRADE_SKILL_LIST_UPDATE')")           # looked at again: still none learned
    assert colours(lua) == {} and len(lua.eval("timers")) == 1
    lua.execute("learned = realLearned; clock = 102; Fire('TRADE_SKILL_LIST_UPDATE')")   # half a second on: not looked at again
    assert colours(lua) == {}
    lua.execute("clock = 103; Fire('TRADE_SKILL_LIST_UPDATE')")
    assert colours(lua)[SPELL_CAKE]["o"] == (120, 120), colours(lua)


def test_every_skill_point_of_a_make_run_is_looked_at_while_the_verdict_holds():
    """A Make run from 119: the button's verdict holds while the client casts (Craft.lua Refresh), and the skill goes 120, 121, 122
    with the cake orange at 120 and yellow from 121. Each point is looked at: the orange's highest is 120 and the yellow's lowest
    121, the two skills a colour changes between, not only the skills before and after the run."""
    if lupa is None:
        return
    lua = game()
    held(lua, bags={FIN: 6, LEG: 9, SPICES: 7}, skill=119)
    v = panel_verdict(lua)
    assert v["text"] == "Make 4 Gooey Spider Cake", v
    assert colours(lua)[SPELL_CAKE]["o"] == (119, 119)
    lua.execute("casting = false; UnitCastingInfo = function() if casting then return 'Gooey Spider Cake' end end; "
                "ForeverWowCraftMake.scripts.OnClick(ForeverWowCraftMake); casting = true")
    for skill, c in ((120, 0), (121, 1), (122, 1)):
        lua.execute(f"colour[{SPELL_CAKE}] = {c}; skill = {skill}; ns.inv.Char().skills[{COOKING}] = skill; "
                    f"bags[0] = {{ {{ {FIN}, 6 }}, {{ {LEG}, {9 - 2 * (skill - 119)} }}, {{ {SPICES}, {7 - (skill - 119)} }} }}; "
                    "Fire('CHAT_MSG_SKILL'); Fire('SKILL_LINES_CHANGED'); Fire('BAG_UPDATE_DELAYED')")
        assert strip(lua.eval("ForeverWowCraftMake.verdict.text")) == "Make 4 Gooey Spider Cake"     # held through the cast
    lua.execute("casting = false; Fire('BAG_UPDATE_DELAYED')")                # the run over: the verdict moves on
    assert strip(lua.eval("ForeverWowCraftMake.verdict.text")) != "Make 4 Gooey Spider Cake"
    row = colours(lua)[SPELL_CAKE]
    assert row["o"] == (119, 120) and row["y"] == (121, 122), row


def test_a_switch_records_nothing_of_the_last_professions_list_at_the_new_rank():
    """The live game, 15 Nov 2026: the window toggled from Cooking to Leatherworking; the client named Leatherworking (rank 30) while
    its list was still Cooking's, and Cooking's colours were recorded at 30. Now that look records nothing; the Leatherworking list,
    once it follows, is recorded at 30 (by the later look a little over a second on, as a look of a list not loaded yet)."""
    if lupa is None:
        return
    lua = game()
    lua.execute(CLOCK + LINES + SWITCH)
    look(lua, 120)
    assert colours(lua)[SPELL_CAKE]["o"] == (120, 120)
    lua.execute(f"prof = {LEATHERWORKING}; clock = 100.5")
    panel_verdict(lua)
    got = colours(lua)
    assert got[SPELL_CAKE]["o"] == (120, 120) and SPELL_KIT not in got, got        # nothing at 30 for the cake
    assert len(lua.eval("timers")) == 1
    lua.execute(LW_LIST + "clock = 100.6; Fire('TRADE_SKILL_LIST_UPDATE')")         # within the second: held back
    lua.execute("clock = 101.7; RunTimers()")
    got = colours(lua)
    assert got[SPELL_KIT]["o"] == (30, 30) and got[SPELL_CAKE]["o"] == (120, 120) and set(got[SPELL_CAKE]) == {"o", "t"}, got


def test_a_client_that_cannot_say_whose_a_recipe_is_records_as_before():
    if lupa is None:
        return
    lua = game()
    lua.execute(CLOCK + SWITCH)
    look(lua, 120)
    lua.execute(f"prof = {LEATHERWORKING}; clock = 100.5")
    panel_verdict(lua)
    assert colours(lua)[SPELL_CAKE]["o"] == (30, 120)                                # no word from the client: the look counts


def test_the_colours_of_helper_182_are_started_again_once():
    """Rows recorded before the switch was told apart may be another profession's: the table is dropped at the first pass and marked
    (FWCS_DB.__coloursFrom = 2), and never again."""
    if lupa is None:
        return
    lua = game()
    lua.execute("FWCS_DB.__colours = { [1] = { o = { 5, 5 }, t = 1 } }")
    look(lua, 120)
    got = colours(lua)
    assert 1 not in got and got[SPELL_CAKE]["o"] == (120, 120) and lua.eval("FWCS_DB.__coloursFrom") == 2, got
    lua.execute("FWCS_DB.__colours[1] = { o = { 5, 5 }, t = 1 }")
    look(lua, 125, **{str(SPELL_CAKE): 1})
    got = colours(lua)
    assert got[1]["o"] == (5, 5) and got[SPELL_CAKE]["y"] == (125, 125), got
    saved = lua_literal(lua.eval("FWCS_DB"))                                         # a reload: the mark carried over, nothing dropped
    fresh = panel_game_saved(saved)
    look(fresh, 126, **{str(SPELL_CAKE): 1})
    got = colours(fresh)
    assert got[1]["o"] == (5, 5) and got[SPELL_CAKE]["y"] == (125, 126), got


def panel_game_saved(saved: str):
    """game() after a /reload: the saved variables carried over."""
    lua = _game(offroute_doc(), saved="FWCS_DB = " + saved)
    lua.execute(GAME + f"learned[{SPELL_TAIL}] = true" + PANEL + BASE)
    return lua


def test_nothing_of_the_character_is_in_the_table():
    if lupa is None:
        return
    lua = game()
    look(lua, 120)
    look(lua, 125, **{str(SPELL_CAKE): 1})
    text = lua_literal(lua.eval("FWCS_DB.__colours"))
    for word in ("Thrallson", "Stonespine", "|", "learned", "skills", "Cooking", "Gooey"):
        assert word not in text, (word, text)
    for spell, row in colours(lua).items():
        assert isinstance(spell, int) and set(row) <= {"o", "y", "g", "x", "t"}, (spell, row)
    assert lua.eval('FWCS_DB.__chars["Stonespine|Thrallson"].colours') is None and lua.eval("ns.notedAt") is None   # no reminder of its own


if __name__ == "__main__":
    if lupa is None:
        print("skipped: no Lua here (pip install lupa); tests/lua_check.py still reads the addon's files")
        sys.exit(0)
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)

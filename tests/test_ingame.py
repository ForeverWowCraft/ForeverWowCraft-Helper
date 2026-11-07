"""The addon's Lua, run: what is left of a route for a character that has things (Tailor.lua),
and the /fwc window drawn against a stand-in for the game (every file of the .toc, in order).

Needs a Lua: `pip install lupa` (it is not needed to use the helper). Without it, this says so
and passes: tests/lua_check.py still reads the files.
"""
import re
import sys
from pathlib import Path

HELPER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HELPER))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fwchelper import plans  # noqa: E402
from test_plans import document  # noqa: E402

try:
    from lupa import lua51 as lupa          # the game's Lua is 5.1
except ImportError:
    try:
        import lupa
    except ImportError:
        lupa = None

ADDON = HELPER / "addon" / "ForeverWowCraftScanner"
BOLT, CLOTH, THREAD, SHIRT, VEST, DYE = 2996, 2589, 2320, 2576, 2568, 2324

# A stand-in for the game: frames that take any call, remember their scripts, events and text.
GAME = r'''
frames, strings, printed, timers = {}, {}, {}, {}
local function Widget()
  local w = { scripts = {}, events = {}, shown = true, text = "" }
  return setmetatable(w, { __index = function(self, key)
    if key == "SetScript" then return function(s, name, fn) s.scripts[name] = fn end end
    if key == "RegisterEvent" then return function(s, event)
      if event == "NO_SUCH_EVENT" or event == "PLAYERBANKSLOTS_CHANGED" then error("unknown event " .. event) end
      s.events[event] = true end end
    if key == "Show" then return function(s) local was = s.shown; s.shown = true; if not was and s.scripts.OnShow then s.scripts.OnShow(s) end end end
    if key == "Hide" then return function(s) s.shown = false end end
    if key == "Disable" then return function(s) s.enabled = false end end
    if key == "Enable" then return function(s) s.enabled = true end end
    if key == "IsShown" then return function(s) return s.shown end end
    if key == "SetText" or key == "SetFormattedText" then return function(s, t, ...) s.text = select("#", ...) > 0 and string.format(t, ...) or tostring(t) end end
    if key == "GetText" then return function(s) return s.text end end
    if key == "SetAttribute" then return function(s, k, v) local a = rawget(s, "attributes") or {}; a[k] = v; s.attributes = a end end
    if key == "GetAttribute" then return function(s, k) local a = rawget(s, "attributes"); return a and a[k] end end
    if key == "SetHeight" then return function(s, h) s.height = h end end
    if key == "GetHeight" then return function(s) return rawget(s, "height") or 400 end end
    if key == "CreateFontString" then return function(s) local f = Widget(); f.owner = s; table.insert(strings, f); return f end end
    if key == "CreateTexture" then return function() return Widget() end end
    if key == "GetFont" then return function() return "font", 12 end end
    if key == "GetPoint" then return function() return "CENTER", nil, "CENTER", 0, 0 end end
    if key:sub(1, 3) == "Get" then return function() return 0 end end
    return function() end
  end })
end
function CreateFrame(_, name, _, template) local f = Widget(); f.template = template or ""; if name then _G[name] = f end; table.insert(frames, f); return f end
function Fire(event, ...)
  for _, f in ipairs(frames) do
    if f.events[event] and f.scripts.OnEvent then f.scripts.OnEvent(f, event, ...) end
  end
end
function RunTimers() local due = timers; timers = {}; for _, fn in ipairs(due) do fn() end end
function AllText() local out = {}; for _, s in ipairs(strings) do if s.shown and s.owner.shown then table.insert(out, s.text) end end; return table.concat(out, "\n") end
UIParent, GameTooltip, UIErrorsFrame = Widget(), Widget(), Widget()
function GameTooltip_Hide() end
hooks = {}                          -- hooks[name or table] = { fn, ... }, what hooksecurefunc was given
function hooksecurefunc(a, b, c)
  local key, fn = c and b or a, c or b
  local owner = c and a or _G
  hooks[key] = hooks[key] or {}
  table.insert(hooks[key], fn)
  local orig = owner[key]
  owner[key] = function(...) if orig then orig(...) end; for _, h in ipairs(hooks[key]) do h(...) end end
end
function PlaySound() end
function InterfaceOptions_AddCategory(panel) registered_panel = panel end
UISpecialFrames, SlashCmdList, SOUNDKIT = {}, {}, {}
Enum = { AuctionHouseSortOrder = { Price = 1 } }
C_Timer = { After = function(_, fn) table.insert(timers, fn) end, NewTicker = function() return { Cancel = function() end } end }
mail = {}                           -- mail[i] = { { itemID, count }, ... }, the inbox while a mailbox is open
owned = {}                          -- owned[i] = { itemID, quantity, status }, the character's auctions once asked for
asked = 0
C_AuctionHouse = {
  SendSearchQuery = function() end,
  QueryOwnedAuctions = function() asked = asked + 1 end,
  GetNumOwnedAuctions = function() return #owned end,
  GetOwnedAuctionInfo = function(i) local a = owned[i]; return { itemKey = { itemID = a[1] }, quantity = a[2], status = a[3] } end,
}
function GetInboxNumItems() return #mail end
function GetInboxItem(i, a) local s = mail[i] and mail[i][a]; if s then return "name", s[1], "texture", s[2] end end
function print(...) table.insert(printed, table.concat({ ... }, " ")) end
time = os.time
function GetTime() return os.clock() end
function GetRealmName() return "Stonespine" end
function UnitName() return "Thrallson" end
function UnitFactionGroup() return "Horde" end
function FormatLargeNumber(n) return tostring(n) end
bags = { [0] = {} }                 -- bags[bag][slot] = { itemID, count }
bank = {}                           -- bank[itemID] = count, what the game counts with the bank open
NUM_BAG_SLOTS = 4
C_Container = {
  GetContainerNumSlots = function(bag) return bags[bag] and 16 or 0 end,
  GetContainerItemInfo = function(bag, slot) local s = bags[bag] and bags[bag][slot]; if s then return { itemID = s[1], stackCount = s[2] } end end,
}
function GetItemCount(item, withBank)
  local n = 0
  for _, bag in pairs(bags) do for _, s in pairs(bag) do if s[1] == item then n = n + s[2] end end end
  return n + (withBank and (bank[item] or 0) or 0)
end
skill = 44
money = 1000000                     -- copper in the bags: 100 gold, so that nothing is short of gold unless a test says
function GetMoney() return money end
function GetNumSkillLines() return 2 end
function GetSkillLineInfo(i) if i == 1 then return "Professions", true end return "Tailoring", false, false, skill end
locale = "enUS"
function GetLocale() return locale end
known, spells, loads = {}, {}, {}   -- the client's names: known[itemID], spells[spellID]; loads: the items it was asked to load
C_Item = {
  GetItemInfo = function(id) return known[id] end,
  RequestLoadItemDataByID = function(id) table.insert(loads, id) end,
}
function GetSpellInfo(id) return spells[id] end
FWCS_QUEUE = { ["FWC Tailoring"] = { { 2996, "Bolt of Linen Cloth" }, { 2589, "Linen Cloth" }, { 2320, "Coarse Thread" } } }
ns = {}
function Load(name, source)
  local chunk = assert(loadstring(source, name))
  chunk("ForeverWowCraftScanner", ns)
end
'''


def _game(doc=None):
    """A Lua with the stand-in game and the addon loaded as the .toc says, the character logged in."""
    lua = lupa.LuaRuntime()
    lua.execute(GAME)
    toc = (ADDON / "ForeverWowCraftScanner.toc").read_text(encoding="utf-8")
    files = [line.strip() for line in toc.splitlines() if line.strip().endswith(".lua")]
    assert files == ["Queue.lua", "Plans.lua", "Fresh.lua", "ForeverWowCraftScanner.lua", "Tailor.lua", "Inventory.lua", "Widgets.lua", "Window.lua",
                     "Background.lua", "Remind.lua", "Panel.lua", "Seed.lua", "Places.lua", "Shop.lua", "Verdict.lua", "Craft.lua"]
    for name in files:
        if name == "Queue.lua":
            continue                                    # the stand-in has a short one
        source = plans.plans_text([doc or document()], "test") if name == "Plans.lua" else (ADDON / name).read_text(encoding="utf-8")
        lua.globals().Load(name, source)
    lua.execute('Fire("PLAYER_LOGIN"); Fire("PLAYER_ENTERING_WORLD", true); RunTimers()')
    return lua


def _tailor(lua, skill, have):
    """ns.Tailor of the document's route, as Python values."""
    lua.globals().have = lua.table_from(have)
    out = lua.eval(f'ns.Tailor(FWCS_PLANS["stonespine--horde"].plans["tailoring-trainer"], {skill}, have)')
    return {k: (dict(v) if lupa.lua_type(v) == "table" else v) for k, v in out.items()}


def test_a_route_with_nothing_in_hand_is_the_route():
    lua = _game()
    out = _tailor(lua, 1, {})
    # 40 bolts from 80 cloth; 10 shirts use 10 of them; 12 vests use 36: 30 from stock, 6 made of 12 more cloth
    assert out["buy"] == {CLOTH: 92, THREAD: 22, DYE: 10} and out["make"] == {BOLT: 6} and out["used"] == {}
    assert out["sell"] == {SHIRT: 10, VEST: 12} and out["crafts"] == 62
    assert out["spent"] == 92 * 30 + 22 * 10 + 10 * 25 and out["sold"] == 10 * 40.5 + 12 * 120


def test_what_the_character_has_is_taken_off():
    lua = _game()
    out = _tailor(lua, 1, {BOLT: 20, THREAD: 100, CLOTH: 10})
    # the first step makes bolts whatever is in hand (it is how the skill is gained); the 20 owned
    # bolts go into shirts and vests, so no more are made, and the 10 cloth go into the first step
    assert out["buy"] == {CLOTH: 70, DYE: 10} and out["make"] == {}
    assert out["used"] == {BOLT: 20, THREAD: 22, CLOTH: 10}
    assert out["sell"] == {SHIRT: 10, VEST: 12, BOLT: 14}        # the bolts the route made and did not need


def test_from_the_characters_skill_on():
    lua = _game()
    step = 'FWCS_PLANS["stonespine--horde"].plans["tailoring-trainer"].steps'
    assert [lua.eval(f"ns.CraftsLeft({step}[3], {s})") for s in (1, 51, 55, 59, 60)] == [12, 12, 7, 2, 0]
    # at 44 the bolts of the first step were never made: the shirts' are made the way that step made them
    out = _tailor(lua, 44, {})
    assert [(s["step"]["recipe"], s["crafts"], s["from"], s["to"]) for s in out["steps"].values()] == \
        [("White Linen Shirt", 7, 44, 51), ("Brown Linen Vest", 12, 51, 60)]
    assert out["make"] == {BOLT: 7 + 36} and out["buy"] == {CLOTH: 86, THREAD: 19, DYE: 7}
    assert _tailor(lua, 60, {})["crafts"] == 0


def test_a_part_of_the_route():
    lua = _game()
    step = 'FWCS_PLANS["stonespine--horde"].plans["tailoring-trainer"].steps'
    # the vests' step (51-60, 12 crafts): all of it within 44-60, none of it up to 51, 7 of it up to 56
    assert [lua.eval(f"ns.CraftsLeft({step}[3], 44, {u})") for u in (60, 51, 56)] == [12, 0, 7]
    assert lua.eval(f"ns.CraftsLeft({step}[3], 55, 56)") == 2                      # one point of 1.333 crafts: rounded up
    # 44 to 51: the shirts only; the bolts for them made, nothing of the vests
    lua.globals().have = lua.table_from({})
    out = lua.eval('ns.Tailor(FWCS_PLANS["stonespine--horde"].plans["tailoring-trainer"], 44, have, 51)')
    assert out["to"] == 51 and out["crafts"] == 7 and dict(out["make"]) == {BOLT: 7} and dict(out["buy"]) == {CLOTH: 14, THREAD: 7, DYE: 7}
    assert [(s["from"], s["to"]) for s in out["steps"].values()] == [(44, 51)]
    # and from the start to 41: the first step alone, its bolts left to sell
    out = lua.eval('ns.Tailor(FWCS_PLANS["stonespine--horde"].plans["tailoring-trainer"], 1, have, 41)')
    assert dict(out["sell"]) == {BOLT: 40} and dict(out["buy"]) == {CLOTH: 80}


def test_a_recipe_to_buy_is_on_the_list_unless_owned():
    doc = document()
    doc["items"]["6000"] = "Pattern: Brown Linen Vest"
    doc["plans"]["tailoring-trainer"]["steps"][2]["learn"] = [6000, 500]
    lua = _game(doc)
    out = _tailor(lua, 1, {})
    assert [dict(r) for r in out["learn"].values()] == [{"item": 6000, "cost": 500, "owned": False}]
    assert out["spent"] == 92 * 30 + 22 * 10 + 10 * 25 + 500
    assert _tailor(lua, 1, {6000: 1})["spent"] == 92 * 30 + 22 * 10 + 10 * 25
    assert _tailor(lua, 55, {})["learn"] == {}                   # past the step's start: it is known already


def test_the_window_shows_the_route_less_bags_and_bank():
    lua = _game()
    lua.execute("bags[0][1] = { 2996, 5 }; bags[0][2] = { 2320, 20 }; bags[0][3] = { 99999, 3 }")     # the last is nothing a profession uses
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("")')
    text = lua.eval("AllText()")
    assert "Tailoring 44 to 60, from your skill. 19 crafts." in text, text
    for part in ("Shopping list", "Linen Cloth", "From what you have", "Route", "White Linen Shirt", "Make on the way", "Left to sell",
                 "Stonespine (Horde)", "Your bank is not counted yet", "Your mail is not counted yet", "Your auctions are not counted yet",
                 "Bags are counted as they are. The bank is counted as it was when last open. The mail is counted"):
        assert part in text, part
    assert "You do not have" not in text
    # the Auctionator import: what is left to buy on the auction house, with quantities, no vendor items
    # (at 44 with 5 bolts and 20 thread: 7 shirts need 2 more bolts, 12 vests 36: 38 bolts from 76 cloth)
    assert lua.eval("(ns.AuctionatorImport())") == 'FWC Tailoring 44-60^"Linen Cloth";;;;;;;;;;;;;76'
    # or everything from nothing: 43 bolts from 86 cloth (the thread is a vendor item: left out)
    assert lua.eval("(ns.AuctionatorImport(true))") == 'FWC Tailoring 44-60 all^"Linen Cloth";;;;;;;;;;;;;86'
    # what the list comes to
    sum_ = dict(lua.eval("select(2, ns.AuctionatorImport())"))
    assert sum_ == {"items": 1, "units": 76, "recipes": 0, "cost": 76 * 30, "unpriced": 0, "english": 0}
    lua.execute("ns.ShowAuctionator()")                                      # what the button does: the box opens
    plain = re.sub(r"\|c[0-9a-f]{8}|\|r", "", lua.eval("AllText()"))
    assert "1 distinct item, 76 units, about 22s 80c at the route's prices" in plain
    # the Feedback button: the project's Discord in a box, the link selected for Ctrl+C
    lua.execute("ns.ShowFeedback()")
    assert lua.eval("ns.DISCORD").startswith("https://discord.gg/") and "Say so on the project's Discord" in lua.eval("AllText()")
    me = lua.eval('FWCS_DB.__chars["Stonespine|Thrallson"]')
    assert (me["items"][BOLT][1], me["items"][BOLT][2]) == (5, 0)
    assert me["items"][99999] is None and me["skills"][197] == 44 and me["faction"] == "Horde"
    # the bank counts once it has been open; closed again, what was seen stays
    lua.execute('bank[2589] = 40; Fire("BANKFRAME_OPENED"); RunTimers(); Fire("BANKFRAME_CLOSED"); bank[2589] = nil; RunTimers()')
    assert me["items"][CLOTH][2] == 40 and me["bankSeen"] is not None
    text = lua.eval("AllText()")
    assert "Your bank is not counted yet" not in text and "counted as it was when last open, 0 min ago" in text
    # the mail counts while a mailbox is open; the auctions once the auction house has sent the list
    # (asked for when it opens); a sold auction is money, not an item. 36 cloth left to buy, then 20
    lua.execute('mail[1] = { { 2589, 10 } }; Fire("MAIL_SHOW"); Fire("MAIL_INBOX_UPDATE"); RunTimers(); Fire("MAIL_CLOSED"); mail[1] = nil; RunTimers()')
    assert me["items"][CLOTH][3] == 10 and me["mailSeen"] is not None
    assert lua.eval("(ns.AuctionatorImport())") == 'FWC Tailoring 44-60^"Linen Cloth";;;;;;;;;;;;;26'
    lua.execute('Fire("AUCTION_HOUSE_SHOW"); owned = { { 2589, 6, 0 }, { 2589, 99, 1 } }; Fire("OWNED_AUCTIONS_UPDATED"); RunTimers(); Fire("AUCTION_HOUSE_CLOSED"); RunTimers()')
    assert lua.eval("asked") == 1 and me["items"][CLOTH][4] == 6 and me["ahSeen"] is not None
    assert lua.eval("(ns.AuctionatorImport())") == 'FWC Tailoring 44-60^"Linen Cloth";;;;;;;;;;;;;20'
    plain = re.sub(r"\|c[0-9a-f]{8}|\|r", "", lua.eval("AllText()"))
    assert "Mail: counted as it was when a mailbox was last open" in plain and "Auctions: counted as they were" in plain
    # the bags are read again without losing the other places
    lua.execute('bags[0][4] = { 2589, 1 }; Fire("BAG_UPDATE_DELAYED"); RunTimers()')
    assert [me["items"][CLOTH][i] for i in (1, 2, 3, 4)] == [1, 40, 10, 6]
    assert lua.eval("(ns.AuctionatorImport())") == 'FWC Tailoring 44-60^"Linen Cloth";;;;;;;;;;;;;19'
    # a skill gained and a bag change draw it again
    lua.execute('skill = 51; bags[0][1] = nil; Fire("CHAT_MSG_SKILL"); RunTimers()')
    assert "Tailoring 51 to 60" in lua.eval("AllText()") and "White Linen Shirt" not in lua.eval("AllText()")
    # another character's things count unless switched off (the shipped default since 1.6.13); /fwc alts switches
    lua.execute('FWCS_DB.__chars["Stonespine|Bankalt"] = { name = "Bankalt", house = "Stonespine", faction = "Horde", items = { [2996] = { 0, 36 } } }; Fire("BAG_UPDATE_DELAYED"); RunTimers()')
    counted = lua.eval("AllText()")
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("alts")')
    alone = lua.eval("AllText()")
    assert "Make on the way" not in counted and "Make on the way" in alone and lua.eval("FWCS_DB.__ui.alts") is False
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("alts")')
    assert "Make on the way" not in lua.eval("AllText()") and lua.eval("FWCS_DB.__ui.alts") is True
    # said by hand, the skill to plan from; and a character without the profession gets the whole route
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("from 1")')
    assert "Tailoring 1 to 60, from the skill you gave" in lua.eval("AllText()")
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("from auto"); GetSkillLineInfo = function() return "Professions", true end; Fire("SKILL_LINES_CHANGED"); RunTimers()')
    # the profession shown is kept only while the character has it: nothing now, until picked
    # from the row of buttons (one per profession the routes cover, greyed when not the character's)
    assert "This character has no profession yet." in lua.eval("AllText()") and lua.eval("ForeverWowCraftAlso.text") == "-"
    assert lua.eval("ForeverWowCraftProfessionTailoring.text") == "|cff808080Tailoring|r"
    assert lua.eval("ForeverWowCraftProfessionEnchanting.text") == "|cff808080Enchanting|r"
    lua.execute("ForeverWowCraftProfessionTailoring.scripts.OnClick(ForeverWowCraftProfessionTailoring)")
    text = lua.eval("AllText()")
    assert "Tailoring 1 to 60, a profession you do not have: the whole route" in text
    assert "This character has no profession the routes cover." in text and "The whole of Tailoring is shown, from skill 1" in text
    assert lua.eval("(ns.AuctionatorImport())").startswith('FWC Tailoring 1-60^"Linen Cloth";;;;;;;;;;;;;')
    # the sliders: a part of the route, kept for the character; back at the ends it is the whole route
    lua.execute('GetSkillLineInfo = function(i) if i == 1 then return "Professions", true end return "Tailoring", false, false, 44 end; Fire("SKILL_LINES_CHANGED"); RunTimers()')
    assert (lua.eval("ForeverWowCraftRange.min"), lua.eval("ForeverWowCraftRange.max"), lua.eval("ForeverWowCraftRange.from"),
            lua.eval("ForeverWowCraftRange.upto")) == (1, 60, 44, 60)
    lua.execute('ForeverWowCraftRange:Moved("upto", 51)')
    plain = re.sub(r"\|c[0-9a-f]{8}|\|r", "", lua.eval("AllText()"))
    assert "Tailoring 44 to 51 (of 60), from your skill. 7 crafts." in plain and "Brown Linen Vest" not in plain
    assert lua.eval("(ns.AuctionatorImport())") == ""                               # the alts' bolts cover the shirts
    assert lua.eval("(ns.AuctionatorImport(true))") == 'FWC Tailoring 44-51 all^"Linen Cloth";;;;;;;;;;;;;14'
    assert lua.eval('FWCS_DB.__chars["Stonespine|Thrallson"].upto.tailoring') == 51
    lua.execute('ForeverWowCraftRange:Moved("from", 55)')                             # not past the other end: held to 50
    assert "Tailoring 50 to 51 (of 60), from the skill you gave" in re.sub(r"\|c[0-9a-f]{8}|\|r", "", lua.eval("AllText()"))
    lua.execute('ForeverWowCraftRange:Moved("from", 44); ForeverWowCraftRange:Moved("upto", 60)')
    assert "Tailoring 44 to 60, from your skill." in lua.eval("AllText()")
    assert lua.eval('FWCS_DB.__chars["Stonespine|Thrallson"].upto.tailoring') is None
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("to 56")')
    assert "Tailoring 44 to 56 (of 60)" in lua.eval("AllText()")
    # the numbers typed: Enter takes one; Reset is the character's skill to the route's end
    lua.execute('local e = ForeverWowCraftRange.fromText; e.text = "47"; e.scripts.OnEnterPressed(e)')
    assert "Tailoring 47 to 56 (of 60), from the skill you gave" in re.sub(r"\|c[0-9a-f]{8}|\|r", "", lua.eval("AllText()"))
    lua.execute("ForeverWowCraftReset.scripts.OnClick(ForeverWowCraftReset)")
    assert "Tailoring 44 to 60, from your skill." in lua.eval("AllText()")
    # the gold: how far it reaches is said; ticked, the route is cut there (the slider's right end
    # is then the gold's, and moving the left end does not make it the player's)
    plain = lambda: re.sub(r"\|c[0-9a-f]{8}|\|r", "", lua.eval("AllText()"))  # noqa: E731
    lua.execute('money = 0; Fire("PLAYER_MONEY"); RunTimers()')
    assert "Gold in your bags, 0c: as far as skill 44 of the 60." in plain()
    lua.execute('money = 110; Fire("PLAYER_MONEY"); RunTimers()')           # 25c a point from here, with the alt's bolts
    assert "Gold in your bags, 1s 10c: as far as skill 48 of the 60." in plain() and lua.eval("ForeverWowCraftGold.text") == "1s 10c"
    lua.execute("ForeverWowCraftCap.scripts.OnClick(ForeverWowCraftCap)")
    assert "Tailoring 44 to 48 (of 60), from your skill." in plain() and "as far as skill 48, where the list stops" in plain()
    assert lua.eval("(ns.AuctionatorImport(true))").startswith("FWC Tailoring 44-48 all^")
    assert lua.eval("ForeverWowCraftRange.upto") == 48 and lua.eval('FWCS_DB.__chars["Stonespine|Thrallson"].upto.tailoring') is None
    lua.execute('ForeverWowCraftRange:Moved("from", 46)')
    assert "Tailoring 46 to 50 (of 60)" in plain() and lua.eval('FWCS_DB.__chars["Stonespine|Thrallson"].upto.tailoring') is None
    # an amount typed counts instead of the bags, until the box is emptied; nonsense is the bags
    lua.execute('local e = ForeverWowCraftGold; e.text = "2g"; e.scripts.OnEnterPressed(e)')
    assert "Gold as typed, 2g 00s: enough for all of this." in plain() and "Tailoring 46 to 60, from the skill you gave" in plain()
    lua.execute('local e = ForeverWowCraftGold; e.text = "lots"; e.scripts.OnEnterPressed(e)')
    assert "Gold in your bags, 1s 10c: as far as skill 50, where the list stops" in plain()
    lua.execute("ForeverWowCraftCap.scripts.OnClick(ForeverWowCraftCap)")
    assert "Tailoring 46 to 60" in plain() and "as far as skill 50 of the 60." in plain()
    lua.execute('ForeverWowCraftRange:Moved("from", 44); money = 0')
    # a second profession counted: by hand, and by itself once the character has one
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("also enchanting")')
    plain = re.sub(r"\|c[0-9a-f]{8}|\|r", "", lua.eval("AllText()"))
    assert "Tailoring with Enchanting 44 to 60, from your skill." in plain and "disenchant" in plain
    assert lua.eval('FWCS_DB.__chars["Stonespine|Thrallson"].also.tailoring') == "enchanting"
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("also none")')
    assert "with Enchanting" not in lua.eval("AllText()") and lua.eval('FWCS_DB.__chars["Stonespine|Thrallson"].also.tailoring') is False
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("also auto")')
    assert "with Enchanting" not in lua.eval("AllText()")                           # not an enchanter: nothing counted by itself
    lua.execute('GetNumSkillLines = function() return 3 end; GetSkillLineInfo = function(i) if i == 1 then return "Professions", true end '
                'if i == 2 then return "Tailoring", false, false, 44 end return "Enchanting", false, false, 20 end; Fire("SKILL_LINES_CHANGED"); RunTimers()')
    assert "Tailoring with Enchanting 44 to 60" in re.sub(r"\|c[0-9a-f]{8}|\|r", "", lua.eval("AllText()"))
    # the buttons: the character's own in plain text, the lit one the one shown; under Also, the second one to count
    assert lua.eval("ForeverWowCraftProfessionTailoring.text") == "Tailoring" and lua.eval("ForeverWowCraftProfessionEnchanting.text") == "Enchanting"
    assert lua.eval("ForeverWowCraftAlso.text") == "Also: Enchanting"
    lua.execute("ForeverWowCraftAlso.scripts.OnClick(ForeverWowCraftAlso)")
    plain = re.sub(r"\|c[0-9a-f]{8}|\|r", "", lua.eval("AllText()"))
    assert "( ) None" in plain and "(x) Enchanting (20)" in plain and "Tailoring (44)" not in plain
    # a secondary profession (cooking) is neither counted by itself nor offered, though it is a profession to show
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("also none"); GetNumSkillLines = function() return 3 end; '
                'GetSkillLineInfo = function(i) if i == 1 then return "Professions", true end '
                'if i == 2 then return "Tailoring", false, false, 44 end return "Cooking", false, false, 75 end; '
                'Fire("SKILL_LINES_CHANGED"); RunTimers(); SlashCmdList.FOREVERWOWCRAFT("also auto")')
    plain = re.sub(r"\|c[0-9a-f]{8}|\|r", "", lua.eval("AllText()"))
    assert "( ) Enchanting (not yours)" in plain and lua.eval("ForeverWowCraftProfessionCooking.text") == "Cooking" and ") Cooking" not in plain
    assert "with Cooking" not in plain and "with Enchanting" not in plain
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("also cooking")')
    assert "secondary profession" in lua.eval("printed[#printed]") and lua.eval('FWCS_DB.__chars["Stonespine|Thrallson"].also.tailoring') is None
    lua.execute("ForeverWowCraftAlso.scripts.OnClick(ForeverWowCraftAlso)")   # closed again
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("to auto")')
    # /fwc again closes it; /fwcs plan opens it
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("")')
    assert lua.eval("AllText()").count("Shopping list") == 1          # still drawn, in a window that is hidden


def test_a_client_in_another_language_sees_its_own_names():
    lua = _game()
    # the profession is found by the client's own name for it (the first rank's spell); a recipe is a spell,
    # an item the client has met (the shirt, the vest, the dye) is named by it
    lua.execute('locale = "deDE"; spells[3908] = "Schneiderei"; spells[2393] = "Weißes Leinenhemd"; '
                'known[2576] = "Weißes Leinenhemd"; known[2568] = "Braune Leinenweste"; known[2324] = "Bleichmittel"; '
                'GetSkillLineInfo = function(i) if i == 1 then return "Berufe", true end return "Schneiderei", false, false, skill end; '
                'Fire("SKILL_LINES_CHANGED"); RunTimers(); SlashCmdList.FOREVERWOWCRAFT("")')
    text = lua.eval("AllText()")
    assert "Tailoring 44 to 60, from your skill. 19 crafts." in text and "Weißes Leinenhemd" in text and "White Linen Shirt" not in text
    # the items the client has not handed over yet are asked for, and English meanwhile; the import string says so
    assert "Linen Cloth" in text and set(lua.eval("loads").values()) >= {2320, 2589, 2996}      # (the arrow's verdict may ask more)
    assert lua.eval("(ns.AuctionatorImport())") == 'FWC Tailoring 44-60^"Linen Cloth";;;;;;;;;;;;;86'
    assert dict(lua.eval("select(2, ns.AuctionatorImport())"))["english"] == 1
    lua.execute("ns.ShowAuctionator()")
    assert "1 name is still in English" in re.sub(r"\|c[0-9a-f]{8}|\|r", "", lua.eval("AllText()"))
    # the names come: the window is drawn again, once, and the import string is the client's
    lua.execute('known[2589] = "Leinenstoff"; known[2996] = "Leinenstoffballen"; Fire("ITEM_DATA_LOAD_RESULT", 2589); Fire("ITEM_DATA_LOAD_RESULT", 2996); RunTimers()')
    text = lua.eval("AllText()")
    assert "Leinenstoff" in text and "Leinenstoffballen" in text and "Linen Cloth" not in text
    assert lua.eval("(ns.AuctionatorImport())") == 'FWC Tailoring 44-60^"Leinenstoff";;;;;;;;;;;;;86'
    assert dict(lua.eval("select(2, ns.AuctionatorImport())"))["english"] == 0
    loads = list(lua.eval("loads").values())
    assert len(loads) == len(set(loads))                                        # asked once each, not again
    # an item no one asked for does not draw the window; a closed window is not drawn either
    lua.execute('Fire("ITEM_DATA_LOAD_RESULT", 99999); ForeverWowCraftWindow:Hide(); Fire("ITEM_DATA_LOAD_RESULT", 2320); RunTimers()')


def test_a_character_without_a_profession_sees_no_route_until_one_is_picked():
    lua = _game()
    lua.execute('GetSkillLineInfo = function() return "Professions", true end; SlashCmdList.FOREVERWOWCRAFT("")')
    plain = re.sub(r"\|c[0-9a-f]{8}|\|r", "", lua.eval("AllText()"))
    assert lua.eval("ForeverWowCraftAlso.text") == "-" and "This character has no profession yet." in plain
    assert "Shopping list" not in plain and "Skill" not in plain and not lua.eval("ForeverWowCraftRange.shown")
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("from 10")')
    assert "no profession shown yet" in lua.eval("printed[#printed]")
    # the buttons still offer every profession, greyed; one clicked, its whole route shows; Also opens nothing until then
    lua.execute("ForeverWowCraftAlso.scripts.OnClick(ForeverWowCraftAlso)")
    assert lua.eval("ForeverWowCraftPicker") is None
    assert lua.eval("ForeverWowCraftProfessionTailoring.text") == "|cff808080Tailoring|r"
    lua.execute("ForeverWowCraftProfessionTailoring.scripts.OnClick(ForeverWowCraftProfessionTailoring)")
    plain = re.sub(r"\|c[0-9a-f]{8}|\|r", "", lua.eval("AllText()"))
    assert "Tailoring 1 to 60, a profession you do not have" in plain and "Shopping list" in plain and lua.eval("ForeverWowCraftRange.shown")
    assert lua.eval("ForeverWowCraftAlso.text") == "Also: none"


def test_the_focus_button_turns_between_the_profit_and_the_skill_up_route():
    doc = document()
    doc["plans"]["tailoring-trainer-skill"] = dict(doc["plans"]["tailoring-trainer"], variant="trainer-skill", sold=0, net=-3000, spent=3000)
    doc["variants"] = [["trainer", "Profit", "plans", "profit"], ["trainer-skill", "Skill-up", "plans", "skill"]]
    doc["focus"] = [["profit", "Profit"], ["skill", "Skill-up"]]
    lua = _game(doc)
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("")')
    assert lua.eval("ForeverWowCraftFocus.shown") and lua.eval("ForeverWowCraftFocus.text") == "[  ] skill-up"
    assert lua.eval("ns.Settings().variant") == "trainer"
    # no button chooses the recipes any more: every route may buy them (2 Nov 2026)
    assert lua.eval("ForeverWowCraftVariant") is None
    # the click moves the arrow, the Make button and the shopping list at once (Craft.lua's pass, not its next tick)
    lua.execute("repointed = 0; ns.ReloadShopping = function() repointed = repointed + 1 end")
    lua.execute("ForeverWowCraftFocus.scripts.OnClick(ForeverWowCraftFocus)")
    assert lua.eval("ForeverWowCraftFocus.text") == "|cff40ff40[x]|r skill-up" and lua.eval("ns.Settings().variant") == "trainer-skill"
    assert lua.eval("repointed") == 1
    lua.execute("ForeverWowCraftFocus.scripts.OnClick(ForeverWowCraftFocus)")
    assert lua.eval("ns.Settings().variant") == "trainer" and lua.eval("repointed") == 2
    lua.execute("ForeverWowCraftProfessionTailoring.scripts.OnClick(ForeverWowCraftProfessionTailoring)")
    assert lua.eval("repointed") == 3
    # a document from before there was a focus has the profit routes alone, and no button for it
    lua = _game()
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("")')
    assert not lua.eval("ForeverWowCraftFocus.shown") and "Tailoring 44 to 60" in lua.eval("AllText()")


def test_the_profession_panel_says_what_making_one_comes_to():
    doc = document()
    # a bolt sells for 90c if it does (the route counts it at 70c, 50 % likely, 50c at the vendor): +30c beside it;
    # a shirt from a document before the plain sale was carried costs 45c; the vest has no price
    doc["recipes"] = {"2963": [60, 70, 90, 0.5, 50], "2393": [85, 40], "2385": False}
    lua = _game(doc)
    # Blizzard_TradeSkillUI's list, loaded when the panel first opens: a row per recipe, headers between
    lua.execute('''
      TradeSkillFrame = { RecipeList = CreateFrame("Frame") }
      local list = TradeSkillFrame.RecipeList
      list.buttons = { CreateFrame("Button"), CreateFrame("Button"), CreateFrame("Button"), CreateFrame("Button"), CreateFrame("Button") }
      function list:RefreshDisplay()
        self.buttons[1].tradeSkillInfo = { type = "header", name = "Cloth" }
        self.buttons[2].tradeSkillInfo = { type = "recipe", recipeID = 2963 }
        self.buttons[3].tradeSkillInfo = { type = "recipe", recipeID = 2393 }
        self.buttons[4].tradeSkillInfo = { type = "recipe", recipeID = 2385 }
        self.buttons[5].tradeSkillInfo = { type = "recipe", recipeID = 99999 }
      end
      Fire("ADDON_LOADED", "Blizzard_TradeSkillUI")
      list:RefreshDisplay()
    ''')
    text = lambda i: lua.eval(f"TradeSkillFrame.RecipeList.buttons[{i}].fwcText.text")  # noqa: E731
    assert [text(i) for i in (1, 2, 3, 4, 5)] == ["", "|cff40ff40+30c|r", "|cffff6060-45c|r", "|cff808080?|r", ""]
    # Blizzard_Professions, Forever's: a scroll box that makes a row for each element in view, the
    # recipe in a tree node's data; drawn again as a whole after a scroll or a filter
    lua.execute('''
      ScrollBoxListViewMixin = { Event = { OnInitializedFrame = "OnInitializedFrame" } }
      ScrollBoxListMixin = { Event = { OnUpdate = "OnUpdate" } }
      local box, view = CreateFrame("Frame"), { callbacks = {} }
      function view:RegisterCallback(event, fn, owner) self.callbacks[event] = fn end
      box.callbacks = {}
      function box:GetView() return view end
      function box:RegisterCallback(event, fn, owner) self.callbacks[event] = fn end
      local function Node(data) return { GetData = function() return data end } end
      box.frames = { { CreateFrame("Button"), Node({ categoryInfo = { name = "Explosives" } }) },
                     { CreateFrame("Button"), Node({ recipeInfo = { recipeID = 2963, name = "Bolt" } }) },
                     { CreateFrame("Button"), { recipeInfo = { recipeID = 2393 } } } }
      function box:ForEachFrame(fn) for _, f in ipairs(self.frames) do fn(f[1], f[2]) end end
      ProfessionsFrame = { CraftingPage = { RecipeList = { ScrollBox = box } } }
      Fire("ADDON_LOADED", "Blizzard_Professions")
      -- a row made for a recipe that scrolled into view
      local row = CreateFrame("Button")
      view.callbacks.OnInitializedFrame(nil, row, Node({ recipeInfo = { recipeID = 2385 } }))
      made = row
    ''')
    assert [lua.eval(f"ProfessionsFrame.CraftingPage.RecipeList.ScrollBox.frames[{i}][1].fwcText.text") for i in (1, 2, 3)] == ["", "|cff40ff40+30c|r", "|cffff6060-45c|r"]
    assert lua.eval("made.fwcText.text") == "|cff808080?|r"
    # the number has a mouse of its own: pointing at it brings the tooltip for the row, once, and leaving lets it go
    lua.execute("made.fwcHit.scripts.OnEnter(); made.fwcHit.scripts.OnEnter()")
    assert lua.eval("rawget(GameTooltip, 'fwcFor') == made")
    lua.execute("made.fwcHit.scripts.OnLeave()")
    assert lua.eval("rawget(GameTooltip, 'fwcFor') == nil")
    lua.execute('ProfessionsFrame.CraftingPage.RecipeList.ScrollBox.frames[2][2] = { recipeInfo = { recipeID = 2393 } }; '
                'ProfessionsFrame.CraftingPage.RecipeList.ScrollBox.callbacks.OnUpdate()')     # the row now shows another recipe
    assert lua.eval("ProfessionsFrame.CraftingPage.RecipeList.ScrollBox.frames[2][1].fwcText.text") == "|cffff6060-45c|r"
    # the older panel: fixed rows, an index into the list, the spell in the recipe link
    lua.execute('''
      TRADE_SKILLS_DISPLAYED = 3
      TradeSkillSkill1, TradeSkillSkill2, TradeSkillSkill3 = CreateFrame("Button"), CreateFrame("Button"), CreateFrame("Button")
      local rows = { { "Cloth", "header" }, { "Bolt of Linen Cloth", "trivial" }, { "White Linen Shirt", "easy" } }
      function GetTradeSkillInfo(i) return rows[i][1], rows[i][2] end
      function GetTradeSkillRecipeLink(i) return ({ nil, "|cffffd000|Henchant:2963|h[Bolt of Linen Cloth]|h|r", "|cffffd000|Henchant:2393|h[White Linen Shirt]|h|r" })[i] end
      function TradeSkillFrame_Update() end
      Fire("TRADE_SKILL_SHOW")
    ''')
    assert [lua.eval(f"TradeSkillSkill{i}.fwcText.text") for i in (1, 2, 3)] == ["", "|cff40ff40+30c|r", "|cffff6060-45c|r"]
    lua.execute("TradeSkillFrame_Update()")                                   # the game's own redraw paints again
    assert lua.eval("TradeSkillSkill2.fwcText.text") == "|cff40ff40+30c|r"
    # a document without the recipes (from before) shows nothing
    lua = _game()
    lua.execute('TradeSkillFrame = { RecipeList = CreateFrame("Frame") }; TradeSkillFrame.RecipeList.buttons = { CreateFrame("Button") }; '
                'function TradeSkillFrame.RecipeList:RefreshDisplay() self.buttons[1].tradeSkillInfo = { type = "recipe", recipeID = 2963 } end; '
                'Fire("ADDON_LOADED", "Blizzard_TradeSkillUI"); TradeSkillFrame.RecipeList:RefreshDisplay()')
    assert lua.eval("TradeSkillFrame.RecipeList.buttons[1].fwcText.text") == ""


def test_a_character_of_a_house_without_routes_is_told_what_to_do():
    lua = _game(document(house="elsewhere--alliance", realm="Elsewhere", faction="Alliance"))
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("plan")')
    text = lua.eval("AllText()")
    assert "No routes for this character's auction house yet." in text and "The helper fetches them" in text
    assert "helper is not installed" not in text and "helper last ran" not in text        # Plans.lua was just written
    # the helper has not run for days: one grey line, nothing else
    lua.execute("FWCS_PLANS_WRITTEN = time() - 3 * 86400; Fire('BAG_UPDATE_DELAYED'); RunTimers()")
    plain = re.sub(r"\|c[0-9a-f]{8}|\|r", "", lua.eval("AllText()"))
    assert "The helper last ran 3 days ago: start it (the icon by the clock)" in plain
    # never written at all: the helper is not installed
    lua.execute("FWCS_PLANS_WRITTEN = nil; Fire('BAG_UPDATE_DELAYED'); RunTimers()")
    plain = re.sub(r"\|c[0-9a-f]{8}|\|r", "", lua.eval("AllText()"))
    assert "The helper is not installed on this PC: foreverwowcraft.com/helper" in plain and "stays on this PC" in plain


def test_the_scanner_in_the_background():
    """The button on the auction house frame, and the options page, against the stub."""
    lua = _game()
    assert lua.eval("ns.scanner.BarHidden()") and lua.eval("ns.scanner.AutoScanEnabled()") and not lua.eval("ns.scanner.ReadyAlertEnabled()")
    lua.execute("FWCS_DEV = true")                                  # what a helper before 1.5.6 wrote from a checkout: no longer shows the bar
    assert lua.eval("ns.scanner.BarHidden()") and lua.eval("ns.scanner.AutoScanEnabled()")
    lua.execute("FWCS_DEV = nil; FWCS_DB.__ui.hidden = false")      # the switch is the only way to the bar
    assert not lua.eval("ns.scanner.BarHidden()") and not lua.eval("ns.scanner.AutoScanEnabled()")
    lua.execute("FWCS_DB.__ui.hidden = nil")
    # the options page registered the old way (the stub has no Settings API)
    assert lua.eval("ns.options.name") == "ForeverWowCraft" and lua.eval("#ns.options.boxes") == 10
    assert lua.eval("registered_panel == ns.options")
    # every setting is on the page (the user, 6 Nov 2026): the switches, by their getters and setters
    lua.execute("ns.options:refresh()")
    labels = [lua.eval(f"ns.options.boxes[{i}].label.text") for i in range(1, 11)]
    assert labels[3] == "The telemetry panel under the bar" and labels[5] == "The arrow to what the Make button needs"
    assert labels[8] == "Count other characters' bags and banks" and labels[9] == "A reminder to reload, every 15 minutes"
    # the shipped defaults, top to bottom, are the user's page of 7 Nov 2026: auto scan, save sound, (bar off), (telemetry off),
    # (ready sound off), arrow, arrow kept, shopping list, other characters, reminder
    lua.execute("FWCS_DB.__ui = {}; ns.options:refresh()")
    assert [lua.eval(f"ns.options.boxes[{i}].get()") for i in range(1, 11)] == [True, True, False, False, False, True, True, True, True, True]
    # the Settings window's own hooks: OnRefresh reads the boxes again (OnShow never fired for a frame made at load,
    # and every box showed unticked after an update, 7 Nov 2026); OnDefault puts the shipped defaults back
    lua.execute("FWCS_DB.__ui = { auto = false, alts = false, log = true, remind = false }; ns.options:OnRefresh()")
    assert [lua.eval(f"ns.options.boxes[{i}].get()") for i in (1, 4, 9, 10)] == [False, True, False, False]
    lua.execute("ns.options:OnDefault()")
    assert [lua.eval(f"ns.options.boxes[{i}].get()") for i in range(1, 11)] == [True, True, False, False, False, True, True, True, True, True]
    assert lua.eval("FWCS_DB.__ui.auto") is None and lua.eval("FWCS_DB.__ui.alts") is None
    lua.execute("local b = ns.options.boxes[9]; b.GetChecked = function() return true end; b.scripts.OnClick(b)")
    assert lua.eval("FWCS_DB.__ui.alts") is True
    lua.execute("local b = ns.options.boxes[6]; b.GetChecked = function() return false end; b.scripts.OnClick(b)")
    assert lua.eval("FWCS_DB.__ui.arrow") is False
    lua.execute("local b = ns.options.boxes[6]; b.GetChecked = function() return true end; b.scripts.OnClick(b); FWCS_DB.__ui.alts = nil")
    assert lua.eval("FWCS_DB.__ui.arrow") is None
    # which auction house the prices are kept as: four buttons, the one in force marked
    lua.execute("ns.options:refresh()")
    assert lua.eval("ForeverWowCraftOptionsHouseWhereyoustand.text") == "|cff40ff40[x]|r Where you stand"
    lua.execute("ForeverWowCraftOptionsHouseHorde.scripts.OnClick(ForeverWowCraftOptionsHouseHorde)")
    assert lua.eval("FWCS_DB.__ui.house") == "Horde" and lua.eval("ForeverWowCraftOptionsHouseHorde.text") == "|cff40ff40[x]|r Horde"
    assert lua.eval("ForeverWowCraftOptionsHouseWhereyoustand.text") == "Where you stand"
    lua.execute("ForeverWowCraftOptionsHouseWhereyoustand.scripts.OnClick(ForeverWowCraftOptionsHouseWhereyoustand)")
    assert lua.eval("FWCS_DB.__ui.house") is None
    # the dragged things back where they started
    lua.execute("FWCS_DB.__ui.pos = { 'TOP', 'TOP', 10, -10 }; FWCS_DB.__ui.winPos = { 'TOP', 'TOP', 1, 1 }; FWCS_DB.__ui.arrowPos = { 'TOP', 'TOP', 2, 2 }; "
                "ForeverWowCraftOptionsReset.scripts.OnClick(ForeverWowCraftOptionsReset)")
    assert lua.eval("FWCS_DB.__ui.pos") is None and lua.eval("FWCS_DB.__ui.winPos") is None and lua.eval("FWCS_DB.__ui.arrowPos") is None
    # the auction house opens: the button appears, dim while the snapshot is on its cooldown, lit once there is something to save
    lua.execute('AuctionHouseFrame = CreateFrame("Frame"); FWCS_DB.__ui.lastFull = time() - 60; Fire("AUCTION_HOUSE_SHOW")')
    assert lua.eval("ForeverWowCraftAHButton.text").startswith("|cff808080Prices in ")
    lua.execute("FWCS_DB.__ui.lastFull = nil; ns.scanner.Refresh()")
    assert lua.eval("ForeverWowCraftAHButton.text") == "Scan Prices"


# ---- the Make button (Craft.lua) -------------------------------------------------------------
def _next(lua, skill, have):
    """ns.NextCraft of the document's tailoring route, as Python values."""
    lua.globals().have = lua.table_from(have)
    out = lua.eval(f'ns.NextCraft(FWCS_PLANS["stonespine--horde"].plans["tailoring-trainer"], {skill}, have)')
    if out is None:
        return None
    rows = lambda t: [list(r.values()) for r in t.values()]  # noqa: E731
    return {"spell": out.spell, "crafts": out.crafts, "from": out["from"], "to": out.to,
            "buy": rows(out.buy), "make": [r[:4] for r in rows(out.make)]}


def test_the_next_thing_to_make_is_the_first_step_left_at_the_skill():
    lua = _game()
    # from 1 with nothing: the bolts, all 40 of them, and the cloth to buy
    assert _next(lua, 1, {}) == {"spell": 2963, "crafts": 40, "from": 1, "to": 41, "buy": [[CLOTH, 80]], "make": []}
    assert _next(lua, 1, {CLOTH: 80})["buy"] == []
    # at 45, into the shirts: 6 crafts, the bolts made on the way (the route says how), their cloth bought
    out = _next(lua, 45, {THREAD: 6, DYE: 6})
    assert out["spell"] == 2393 and out["crafts"] == 6 and out["from"] == 45 and out["to"] == 51
    assert out["make"] == [[BOLT, 6, 6, 2963]] and out["buy"] == [[CLOTH, 12]]
    # with the bolts in the bags nothing is made on the way
    out = _next(lua, 45, {THREAD: 6, DYE: 6, BOLT: 6})
    assert out["make"] == [] and out["buy"] == []
    # the vests: 3 bolts a craft, made from the cloth in the bags
    out = _next(lua, 51, {CLOTH: 72, THREAD: 12})
    assert out["spell"] == 2385 and out["crafts"] == 12 and out["make"] == [[BOLT, 36, 36, 2963]] and out["buy"] == []
    # done
    assert _next(lua, 60, {}) is None


def test_the_make_button_crafts_the_route_a_step_at_a_time():
    lua = _game()
    # Blizzard_Professions, with the client's crafting: what it is asked to craft is recorded
    lua.execute('''
      crafted, stopped, learned, reqs = {}, 0, { [2963] = true, [2393] = true, [2385] = true }, {}
      C_TradeSkillUI = {
        GetBaseProfessionInfo = function() return { professionID = 197, professionName = "Tailoring", skillLevel = skill } end,
        GetRecipeInfo = function(id) return { recipeID = id, learned = learned[id] or false } end,
        GetRecipeRequirements = function(id) return reqs[id] or {} end,
        CraftRecipe = function(id, n) table.insert(crafted, { id, n }) end,
        StopRecipeRepeat = function() stopped = stopped + 1 end,
      }
      cancelled = 0
      function SpellStopCasting() cancelled = cancelled + 1 end
      ProfessionsFrame = { CraftingPage = { CreateAllButton = CreateFrame("Button"), CreateButton = CreateFrame("Button") } }
      Fire("ADDON_LOADED", "Blizzard_Professions")
      Fire("TRADE_SKILL_SHOW")
    ''')
    text = lambda: lua.eval("ForeverWowCraftMake.verdict.text")  # noqa: E731
    mode = lambda: lua.eval("ForeverWowCraftMake.mode")  # noqa: E731
    click = lambda: lua.execute("ForeverWowCraftMake.scripts.OnClick(ForeverWowCraftMake)")  # noqa: E731
    crafted = lambda: [list(r.values()) for r in lua.eval("crafted").values()]  # noqa: E731
    # at the apprentice cap no craft gives a point: the next rank, from the trainer, comes first
    lua.execute('skill = 51; C_TradeSkillUI.GetBaseProfessionInfo = function() return { professionID = 197, professionName = "Tailoring", skillLevel = skill, maxSkillLevel = 51 } end; Fire("TRADE_SKILL_LIST_UPDATE")')
    lines = list(lua.eval("ForeverWowCraftMake.verdict.tip").values())
    assert text() == "Train the next rank of Tailoring first" and "no craft gives a point" in lines[-2]
    assert "trainer" in lines[-1] and lua.eval("ForeverWowCraftMake.verdict.place[5]") == 52     # the seed's, or none seen
    # from 25 below the cap the rank is a note under the arrow, the craft path going on; from
    # one below the cap it comes first
    lua.execute('skill = 44; C_TradeSkillUI.GetBaseProfessionInfo = function() return { professionID = 197, professionName = "Tailoring", skillLevel = skill, maxSkillLevel = 55 } end; Fire("TRADE_SKILL_LIST_UPDATE")')
    assert text().startswith("Buy") and lua.eval("ForeverWowCraftMake.verdict.aside.text") == "Train the next rank of Tailoring"
    assert lua.eval("ForeverWowCraftArrow.text.text").endswith("> Train the next rank of Tailoring|r")           # folded
    lua.execute('ForeverWowCraftArrow.scripts.OnMouseUp(ForeverWowCraftArrow, "LeftButton")')
    assert "v Train the next rank of Tailoring: " in lua.eval("ForeverWowCraftArrow.text.text") and "(from skill 30; the cap is 55)" in lua.eval("ForeverWowCraftArrow.text.text")
    lua.execute('ForeverWowCraftArrow.scripts.OnMouseUp(ForeverWowCraftArrow, "LeftButton")')
    lua.execute('skill = 54; Fire("TRADE_SKILL_LIST_UPDATE")')
    assert text() == "Train the next rank of Tailoring first" and "the next point reaches the cap" in list(lua.eval("ForeverWowCraftMake.verdict.tip").values())[-2]
    lua.execute('skill = 44')
    lua.execute('C_TradeSkillUI.GetBaseProfessionInfo = function() return { professionID = 197, professionName = "Tailoring", skillLevel = skill, maxSkillLevel = 75 } end; Fire("TRADE_SKILL_LIST_UPDATE")')
    assert text().startswith("Buy")                                                            # 44 is more than 25 below 75
    lua.execute('C_TradeSkillUI.GetBaseProfessionInfo = function() return { professionID = 197, professionName = "Tailoring", skillLevel = skill, maxSkillLevel = 150 } end; skill = 44; Fire("SKILL_LINES_CHANGED")')
    # at skill 44, the shirts: the bags hold nothing, so the first thing is to buy: the cloth at
    # the house, the thread and the dye from a vendor; the click opens the list
    assert text() == "Buy at the auction house (1) and a vendor (2)" and mode() == "Buy" and lua.eval("ForeverWowCraftMake.glow.shown") is True
    tip = [re.sub(r"\|c[0-9a-fA-F]{8}|\|r", "", line) for line in lua.eval("ForeverWowCraftMake.verdict.tip").values()]
    assert "  14 Linen Cloth (have 0), about 4s 20c, at the auction house" in tip and "  7 Coarse Thread (have 0), about 70c, from a vendor" in tip
    click()                                            # the click: the words in chat, and the list
    assert crafted() == [] and lua.eval("ForeverWowCraftShop.shown") is True
    assert lua.eval("printed[#printed]").startswith("|cfff2b51dForeverWowCraft|r: Buy at the auction house (1) and a vendor (2). ")
    assert lua.eval("ForeverWowCraftShop.title.text") == "White Linen Shirt, skill 44 to 51, needs"
    assert [lua.eval(f"ForeverWowCraftShop.rows[{i}].name.text") for i in (1, 2, 3)] == ["Linen Cloth", "Coarse Thread", "Bleach"]
    assert lua.eval("ForeverWowCraftShop.rows[1].need.text") == "need 14, have 0" and lua.eval("ForeverWowCraftShop.rows[2].status.text") == "vendor"
    lua.execute("ForeverWowCraftShop:Hide()")
    # the purse short of what the step buys (6s 65c): the words say by how much and the two ways
    # out, the cloth farmed instead of bought, not the vendor's thread and dye; no arrow to a
    # seller, the click still lists; red. The gold back, the verdict is the buy again
    lua.execute('money = 400; Fire("PLAYER_MONEY")')
    strip = lambda s: re.sub(r"\|c[0-9a-fA-F]{8}|\|r", "", s)  # noqa: E731
    assert strip(text()) == "Short 2s 65c: farm gold or farm 14 Linen Cloth" and mode() == "Short"
    tip = [strip(line) for line in lua.eval("ForeverWowCraftMake.verdict.tip").values()]
    assert "Gold in the bags: 4s 00c; this needs about 6s 65c." in tip and "Farm the gold, or farm 14 Linen Cloth instead of buying (the rest takes gold)." in tip
    assert tip[-1] == "Click: the shopping list." and lua.eval("ForeverWowCraftMake.verdict.place") is None
    assert lua.eval("ForeverWowCraftMake.verdict.short") == 265 and strip(lua.eval("ForeverWowCraftArrow.text.text")).endswith("Short 2s 65c: farm gold or farm 14 Linen Cloth")
    click()
    assert lua.eval("ForeverWowCraftShop.shown") is True and strip(lua.eval("printed[#printed]")).startswith("ForeverWowCraft: Short 2s 65c: farm gold or farm 14 Linen Cloth. Click: the shopping list.")
    lua.execute('ForeverWowCraftShop:Hide(); money = 1000000; Fire("PLAYER_MONEY")')
    assert text() == "Buy at the auction house (1) and a vendor (2)" and mode() == "Buy"
    # with some bolts already, the bolts still short of the step's 7 come first (5 more), not
    # the shirt the bags could make one of: branches before the root
    lua.execute('bags[0] = { { 2589, 14 }, { 2996, 2 }, { 2320, 7 }, { 2324, 7 } }; Fire("BAG_UPDATE_DELAYED")')
    assert text() == "Make 5 Bolt of Linen Cloth"
    # with the cloth, thread and dye in the bags: the bolts first, on the way
    lua.execute('bags[0] = { { 2589, 14 }, { 2320, 7 }, { 2324, 7 } }; Fire("BAG_UPDATE_DELAYED")')
    assert text() == "Make 7 Bolt of Linen Cloth"
    click()
    assert crafted() == [[2963, 7]]
    # the bolts made: the shirts themselves, up to the step's end
    lua.execute('bags[0] = { { 2996, 7 }, { 2320, 7 }, { 2324, 7 } }; Fire("BAG_UPDATE_DELAYED")')
    assert text() == "Make 7 White Linen Shirt"
    click()
    assert crafted() == [[2963, 7], [2393, 7]]
    # a skill point short of the step's end: the crafting goes on; at the end it is stopped
    lua.execute('skill = 50; Fire("SKILL_LINES_CHANGED")')
    assert lua.eval("stopped") == 0
    lua.execute('skill = 51; Fire("SKILL_LINES_CHANGED")')
    assert lua.eval("stopped") == 1 and lua.eval("cancelled") == 0 and "press Escape" in lua.eval("printed[#printed]")   # the cast under way is the player's to cancel
    # the next step, the vests, with the bags holding what they take: a recipe not known, then a place
    lua.execute('learned[2385] = false; bags[0] = { { 2996, 36 }, { 2320, 12 } }; Fire("BAG_UPDATE_DELAYED")')
    assert text() == "Learn Brown Linen Vest first"
    lua.execute('learned[2385] = true; reqs[2385] = { { name = "Anvil", met = false }, { name = "Thread", met = true } }; Fire("TRADE_SKILL_LIST_UPDATE")')
    assert text() == "Needs Anvil"
    click()
    assert len(crafted()) == 2
    # at the anvil, with reagents for only 5 of the 12: 5 are asked for
    lua.execute('reqs[2385] = {}; bags[0] = { { 2996, 15 }, { 2320, 12 } }; Fire("BAG_UPDATE_DELAYED")')
    assert text() == "Make 5 Brown Linen Vest"
    click()
    assert crafted()[-1] == [2385, 5]
    # done
    lua.execute('skill = 60; Fire("SKILL_LINES_CHANGED")')
    assert text() == "Route done at skill 60"
    # a panel showing a profession the site has no route for
    lua.execute('C_TradeSkillUI.GetBaseProfessionInfo = function() return { professionID = 164, skillLevel = 1 } end; Fire("TRADE_SKILL_SHOW")')
    assert text() == "No route for this profession"


# ---- places and the arrow (Places.lua) --------------------------------------------------------
PLACES_GAME = '''
  map, px, py, facing = 1453, 0.50, 0.50, 0       -- Stormwind; facing north
  C_Map = {
    GetBestMapForUnit = function() return map end,
    GetPlayerMapPosition = function(m) return { x = px, y = py } end,
    GetMapWorldSize = function(m) return 1000, 1000 end,
    GetMapInfo = function(m) return { name = m == 1453 and "Stormwind City" or "Elwynn Forest" } end,
  }
  function GetPlayerFacing() return facing end
  services, skillreq = {}, {}
  function GetNumTrainerServices() return #services end
  function GetTrainerServiceInfo(i) return services[i], "available" end
  function GetTrainerServiceSkillReq(i) return skillreq[i] end
  wares = {}
  function GetMerchantNumItems() return #wares end
  function GetMerchantItemLink(i) return "|cffffffff|Hitem:" .. wares[i] .. "::::::::1:::::::|h[x]|h|r" end
  seedplaces, FWCS_SEED.places = FWCS_SEED.places, {}      -- the seed's Stormwind put aside: these tests meet things
'''


def test_the_seed_knows_the_vanilla_world():
    lua = _game()
    lua.execute(PLACES_GAME + "FWCS_SEED.places = seedplaces; px, py = 0.52, 0.83")
    # the character is Horde (the stub's): Stormwind's trainer is not for it; an Alliance one has it
    assert lua.eval('(ns.NearestPlace("trainer", "tailoring", nil, 200))') is None or lua.eval('(ns.NearestPlace("trainer", "tailoring", nil, 200))').name != "Georgio Bolero"
    lua.execute('UnitFactionGroup = function() return "Alliance" end')
    # by Stormwind's tailoring shop: its artisan trainer, a few yards off, with the seed's map size
    p, d, here = lua.eval('ns.NearestPlace("trainer", "tailoring", nil, 200)')
    assert p.name == "Georgio Bolero" and p.seed is True and d < 20 and here is True
    # a trainer that teaches further than any in the city is sought elsewhere
    found = lua.eval('ns.NearestPlace("trainer", "tailoring", nil, 290)')
    assert found is None or found[0].name != "Georgio Bolero"
    # from Westfall, where no first-aid trainer is, the one that teaches Journeyman (to 76) is
    # Goldshire's, the nearest through the world, not the first fitting row of the seed (Brill's,
    # labelled Western Plaguelands by its rectangle: 6 Nov 2026); yards are said, not pointed
    lua.execute("map, px, py = 1436, 0.56, 0.47")
    p, d, here = lua.eval('ns.NearestPlace("trainer", "first-aid", nil, 76)')
    assert p.name == "Michelle Belle" and here is False and 1000 < d < 2500
    assert lua.eval("ns.Far(1436, 0.56, 0.47, 1453, 0.53, 0.45)") > lua.eval("ns.Far(1436, 0.56, 0.47, 1429, 0.43, 0.66)")   # Stormwind is further
    assert lua.eval("ns.Far(1436, 0.56, 0.47, 1454, 0.5, 0.5)") is None                   # Orgrimmar: another continent
    lua.execute("map, px, py = 1453, 0.52, 0.83")
    # an anvil, and the auction house
    assert lua.eval('(ns.NearestPlace("station", "Anvil"))').what == "Anvil"
    assert lua.eval('(ns.NearestPlace("auction"))').name.startswith("Auctioneer")
    lua.execute("ns.PlacesCommand()")
    assert "and 1604 that the addon came with" in lua.eval("printed[#printed]")


def test_the_arrow_points_across_maps_on_one_continent():
    """From Sentinel Hill to Goldshire's trainer: the arrow turns north-east, the words say the
    map and about how far; to Orgrimmar, the other continent, the words alone."""
    lua = _game()
    lua.execute(PLACES_GAME + "FWCS_SEED.places = seedplaces; map, px, py = 1436, 0.56, 0.47")
    lua.execute('ns.SetArrow({ map = 1429, x = 0.43, y = 0.66, kind = "trainer" }, "First Aid trainer: Michelle Belle", false, "Learn Journeyman First Aid", "First Aid")')
    lua.execute("ForeverWowCraftArrow.tex.SetRotation = function(t, r) t.rotation = r end; ForeverWowCraftArrow.scripts.OnUpdate(ForeverWowCraftArrow, 1)")
    arrow = lua.eval("ForeverWowCraftArrow")
    assert arrow.tex.shown is True and arrow.text.text.startswith("First Aid\nTrainer: Michelle Belle\nin Elwynn Forest, about ")
    yards = int(re.search(r"about (\d+) yd", arrow.text.text).group(1))
    assert 1000 < yards < 2500
    import math
    assert -math.pi / 2 < lua.eval("ForeverWowCraftArrow.tex.rotation") < 0          # facing north, Goldshire is to the north-east: a turn right
    lua.execute('ns.SetArrow({ map = 1454, x = 0.5, y = 0.5, kind = "trainer" }, "First Aid trainer: Arnok", false, nil, "First Aid"); ForeverWowCraftArrow.scripts.OnUpdate(ForeverWowCraftArrow, 1)')
    assert lua.eval("ForeverWowCraftArrow.tex.shown") is False and lua.eval("ForeverWowCraftArrow.text.text").endswith("in Elwynn Forest")     # the stub names every other map so


def test_the_bearing_turns_an_arrow_that_points_up():
    lua = _game()
    import math
    b = lambda *a: lua.eval("ns.Bearing(%s)" % ", ".join(str(x) for x in a))  # noqa: E731
    # a target due east, facing north: the arrow turns right a quarter (SetRotation turns left for positive)
    assert abs(b(0.5, 0.5, 0.6, 0.5, 0) + math.pi / 2) < 1e-9
    # facing east (a quarter turn left three times): the target is ahead
    assert abs(b(0.5, 0.5, 0.6, 0.5, 3 * math.pi / 2) + 2 * math.pi) < 1e-9
    # due north (y grows south), facing north: ahead
    assert abs(b(0.5, 0.5, 0.5, 0.4, 0)) < 1e-9


def test_places_are_noted_as_the_character_meets_them():
    lua = _game()
    lua.execute(PLACES_GAME)
    # a tailoring trainer: the services ask for Tailoring, and a route's recipe is among them
    lua.execute('services = { "Journeyman Tailor", "White Linen Shirt", "Brown Linen Vest" }; skillreq = { "Tailoring", "Tailoring", "Tailoring" }; Fire("TRAINER_SHOW")')
    places = lambda: [dict(p) for p in lua.eval("FWCS_DB.__places").values()]  # noqa: E731
    assert len(places()) == 1 and places()[0]["kind"] == "trainer" and places()[0]["what"] == "tailoring" and places()[0]["map"] == 1453
    assert list(places()[0]["teaches"].values()) == ["White Linen Shirt", "Brown Linen Vest"]
    # seen again a few yards on: the same place
    lua.execute('px = 0.51; Fire("TRAINER_SHOW")')
    assert len(places()) == 1
    # a vendor selling thread (a route's item) and a sword (not): the thread is kept
    lua.execute('px = 0.70; wares = { 2320, 25 }; Fire("MERCHANT_SHOW")')
    assert len(places()) == 2 and places()[1]["kind"] == "vendor" and list(places()[1]["sells"].values()) == [THREAD]
    # the vendor's whole stock, by the creature's id, for the helper to send (nothing of the character)
    lua.execute('''
      function GetMerchantItemInfo(i) if i == 1 then return "Coarse Thread", "tex", 10, 1, -1, true, true, false end return "Sword", "tex", 500, 1, 2, true, false, true end
      function GetMerchantItemCostInfo(i) return i == 2 and 1 or 0 end
      function GetMerchantItemCostItem(i, j) return "tex", 45, "|cffffffff|Hitem:250000::::::::1:::::::|h[Favor]|h|r", "Favor" end
      function UnitGUID(unit) return "Creature-0-4170-0-10-3579-000057A14C" end
      function GetBuildInfo() return "1.60.1", "70790", "Nov 3 2026", 16001 end
      Fire("MERCHANT_SHOW")
    ''')
    v = lua.eval("FWCS_DB.__vendors[3579]")
    assert v.name == "Thrallson" and v.map == 1453 and abs(v.x - 0.70) < 1e-9 and v.faction == "Horde" and v.build == "70790" and v.t > 0   # the stub's npc is named so
    thread, sword = v["items"][THREAD], v["items"][25]
    assert (thread.price, thread.stack, thread.n, thread.usable) == (10, 1, -1, True) and thread.cost is None
    assert (sword.price, sword.n, sword.usable) == (500, 2, False) and dict(sword.cost) == {250000: 45}
    # a trainer's window the same way (since 1.6.12): each service and the skill it asks for, Forever's own learn level
    lua.execute('px = 0.51; GetTrainerServiceSkillReq = function(i) return skillreq[i], ({ 50, 1, 15 })[i] end; Fire("TRAINER_SHOW"); '
                'GetTrainerServiceSkillReq = function(i) return skillreq[i] end')
    t = lua.eval("FWCS_DB.__trainers[3579]")
    assert t.name == "Thrallson" and t.skill == "Tailoring" and t.map == 1453 and t.faction == "Horde" and t.build == "70790" and t.t > 0
    assert dict(t.teaches) == {"Journeyman Tailor": 50, "White Linen Shirt": 1, "Brown Linen Vest": 15}
    lua.execute('services = { "Brown Linen Vest" }; GetTrainerServiceSkillReq = function(i) return skillreq[i], 20 end; Fire("TRAINER_SHOW"); '
                'GetTrainerServiceSkillReq = function(i) return skillreq[i] end; services = { "Journeyman Tailor", "White Linen Shirt", "Brown Linen Vest" }')
    assert dict(lua.eval("FWCS_DB.__trainers[3579].teaches")) == {"Journeyman Tailor": 50, "White Linen Shirt": 1, "Brown Linen Vest": 20}   # the union; the newest skill
    lua.execute('GetMerchantItemInfo, GetMerchantItemCostInfo, GetMerchantItemCostItem, UnitGUID, GetBuildInfo = nil, nil, nil, nil, nil')
    assert len(places()) == 2                                                              # the place list is as before
    # the auctioneer, in another part of town
    lua.execute('px, py = 0.60, 0.30; Fire("AUCTION_HOUSE_SHOW")')
    assert [p["kind"] for p in places()] == ["trainer", "vendor", "auction"]
    # nearest: the vendor selling thread, 200 yd east of the start
    lua.execute('px, py = 0.50, 0.50')
    p, d, here = lua.eval('ns.NearestPlace("vendor", nil, %d)' % THREAD)
    assert p.kind == "vendor" and abs(d - 200) < 1e-6 and here is True
    assert lua.eval('ns.NearestPlace("vendor", nil, 25)') is None
    # on another map, the one seen is named, with the way through the world (Stormwind from Elwynn)
    lua.execute('map = 1429')
    p, d, here = lua.eval('ns.NearestPlace("trainer", "tailoring")')
    assert p.what == "tailoring" and d is not None and 0 < d < 3000 and here is False


def test_a_recipe_the_route_buys_takes_gold_and_only_gold():
    """The step's reagents in the bags, the recipe to buy (5s) and 1s in the purse: short, and
    nothing to farm but the gold. With the silver, the recipe is the next thing."""
    lua = _game()
    lua.execute('''
      learned, reqs = { [2963] = true, [2393] = true, [2385] = false }, {}
      C_TradeSkillUI = {
        GetBaseProfessionInfo = function() return { professionID = 197, skillLevel = skill } end,
        GetRecipeInfo = function(id) return { recipeID = id, learned = learned[id] or false } end,
        GetRecipeRequirements = function(id) return reqs[id] or {} end,
        CraftRecipe = function() end, StopRecipeRepeat = function() end,
      }
      ProfessionsFrame = { CraftingPage = { CreateAllButton = CreateFrame("Button") } }
      local doc = FWCS_PLANS["stonespine--horde"]
      doc.plans["tailoring-trainer"].steps[3].learn = { 6000, 500 }
      doc.plans["tailoring-trainer"].buy[6000] = { 500, "vendor" }
      doc.items[6000] = "Pattern: Brown Linen Vest"
      skill = 51
      bags[0] = { { 2996, 36 }, { 2320, 12 } }
      money = 100
      Fire("TRADE_SKILL_SHOW")
    ''')
    strip = lambda s: re.sub(r"\|c[0-9a-fA-F]{8}|\|r", "", s)  # noqa: E731
    text = lambda: strip(lua.eval("ForeverWowCraftMake.verdict.text"))  # noqa: E731
    tip = lambda: [strip(line) for line in lua.eval("ForeverWowCraftMake.verdict.tip").values()]  # noqa: E731
    assert text() == "Short 4s 00c: farm gold" and lua.eval("ForeverWowCraftMake.mode") == "Short"
    assert "Gold in the bags: 1s 00c; this needs about 5s 00c." in tip() and "Farm the gold: what is short is bought, not farmed." in tip()
    assert lua.eval("ForeverWowCraftMake.verdict.place") is None and lua.eval("ForeverWowCraftMake.verdict.shopping[1].recipe") is True
    lua.execute('money = 600; Fire("PLAYER_MONEY")')
    assert text() == "Learn Brown Linen Vest first" and lua.eval("ForeverWowCraftMake.verdict.place[1]") == "vendor"


def test_the_make_button_points_the_arrow_at_what_it_needs():
    lua = _game()
    lua.execute(PLACES_GAME)
    lua.execute('''
      crafted, learned, reqs = {}, { [2963] = true, [2393] = true, [2385] = false }, {}
      C_TradeSkillUI = {
        GetBaseProfessionInfo = function() return { professionID = 197, skillLevel = skill } end,
        GetRecipeInfo = function(id) return { recipeID = id, learned = learned[id] or false } end,
        GetRecipeRequirements = function(id) return reqs[id] or {} end,
        CraftRecipe = function(id, n) table.insert(crafted, { id, n }) end,
        StopRecipeRepeat = function() end,
      }
      selected = 2393
      ProfessionsFrame = { CraftingPage = { CreateAllButton = CreateFrame("Button"),
                                            SchematicForm = { GetRecipeInfo = function() return { recipeID = selected } end } } }
      skill = 51
      bags[0] = { { 2996, 36 }, { 2320, 12 } }
      Fire("TRADE_SKILL_SHOW")
    ''')
    text = lambda: lua.eval("ForeverWowCraftMake.verdict.text")  # noqa: E731
    tip = lambda: list(lua.eval("ForeverWowCraftMake.verdict.tip").values())  # noqa: E731
    arrow = lambda: lua.eval("ForeverWowCraftArrow")  # noqa: E731
    # the vests are not known and no trainer has been seen: the tooltip says so, no arrow
    assert text() == "Learn Brown Linen Vest first"
    assert tip()[-1].startswith("No trainer seen yet")
    assert arrow().shown is True and arrow().text.text == "Tailoring" + chr(10) + "No trainer seen yet" + chr(10) + "(Learn Brown Linen Vest first)"
    # a trainer seen 300 yd south: the arrow points there, turned round (facing north)
    lua.execute('px, py = 0.50, 0.80; services = { "Brown Linen Vest" }; skillreq = { "Tailoring" }; Fire("TRAINER_SHOW"); px, py = 0.50, 0.50; Fire("BAG_UPDATE_DELAYED")')
    assert tip()[-1] == "The arrow points at the nearest: Tailoring trainer: Thrallson, 300 yd."
    lua.execute("ForeverWowCraftArrow.tex.SetRotation = function(t, r) t.rotation = r end; ForeverWowCraftArrow.scripts.OnUpdate(ForeverWowCraftArrow, 1)")
    assert arrow().shown is True and arrow().text.text == "Tailoring\nTrainer: Thrallson\n300 yd\n(Learn Brown Linen Vest first)"
    import math
    assert abs(lua.eval("ForeverWowCraftArrow.tex.rotation") - (-math.pi)) < 1e-9
    # the window closed with Keep arrow ticked: the trainer's arrow stays, though without the panel
    # nothing says the vest is unknown (the bags would make 12)
    lua.execute('Fire("TRADE_SKILL_CLOSE")')
    assert arrow().shown is True and arrow().text.text.startswith("Tailoring\nTrainer: Thrallson")
    # the vest learned at the trainer, the window still closed: the spellbook knows it, and the
    # arrow moves on to what is next (the bags make 12: the words, under a hammer)
    lua.execute('IsPlayerSpell = function(s) return s == 2385 end; Fire("NEW_RECIPE_LEARNED", 2385)')
    assert arrow().shown is True and arrow().text.text == "Tailoring\nMake 12 Brown Linen Vest"
    # the spellbook's no is a no: a recipe not known is not offered to make, the trainer is
    lua.execute('IsPlayerSpell = function(s) return false end; Fire("BAG_UPDATE_DELAYED")')
    assert arrow().text.text.startswith("Tailoring\nTrainer: Thrallson") and arrow().text.text.endswith("(Learn Brown Linen Vest first)")
    lua.execute('IsPlayerSpell = nil; Fire("TRADE_SKILL_SHOW")')
    # learned, but the vest needs an anvil: none seen, so the panel at an anvil notes one
    lua.execute('learned[2385] = true; reqs[2385] = { { name = "Anvil", met = false, type = 2 } }; Enum.RecipeRequirementType = { Totem = 0, Spell = 1, Area = 2 }; Fire("TRADE_SKILL_LIST_UPDATE")')
    assert text() == "Needs Anvil" and tip()[-1].startswith("No anvil seen yet")
    assert arrow().shown is True and arrow().text.text == "Tailoring\nNo anvil seen yet\n(Needs Anvil)"   # a question mark, and the words
    lua.execute('px, py = 0.52, 0.50; reqs[2385] = { { name = "Anvil", met = true, type = 2 } }; Fire("TRADE_SKILL_LIST_UPDATE")')
    assert text() == "Make 12 Brown Linen Vest"
    assert [p["kind"] for p in [dict(p) for p in lua.eval("FWCS_DB.__places").values()]] == ["trainer", "station"]
    # away from it again: the arrow points at the anvil just noted, 20 yd east
    lua.execute('px = 0.50; reqs[2385] = { { name = "Anvil", met = false, type = 2 } }; Fire("TRADE_SKILL_LIST_UPDATE")')
    assert text() == "Needs Anvil" and tip()[-1] == "The arrow points at the nearest: Anvil, 20 yd."
    # a reload: the arrow is back as it was for this character, before any window opens (the pass
    # without the panel cannot know of the anvil, and leaves it)
    assert lua.eval('FWCS_DB.__chars["Stonespine|Thrallson"].arrow.title') == "Anvil"
    lua.execute('ns.ClearArrow(); Fire("PLAYER_ENTERING_WORLD"); RunTimers()')
    assert arrow().shown is True and arrow().text.text == "Tailoring\nAnvil\n20 yd\n(Needs Anvil)"
    # a tool is not a place
    lua.execute('reqs[2385] = { { name = "Blacksmith Hammer", met = false, type = 0 } }; Fire("TRADE_SKILL_LIST_UPDATE")')
    assert text() == "Buy Blacksmith Hammer first" and "a vendor sells it" in tip()[-1]
    assert arrow().shown is True and arrow().text.text == "Tailoring\nBuy Blacksmith Hammer first"            # the words stay up
    # the item known by name: bought at the house, the auctioneer pointed at, on the list
    lua.execute('GetItemInfoInstant = function(name) if name == "Blacksmith Hammer" then return 5956 end end; Fire("TRADE_SKILL_LIST_UPDATE")')
    assert text() == "Buy Blacksmith Hammer first" and tip()[-1].startswith("No auctioneer seen yet")
    assert lua.eval("ForeverWowCraftMake.verdict.shopping.title") == "Blacksmith Hammer, to make Brown Linen Vest"
    assert lua.eval('FWCS_DB.__chars["Stonespine|Thrallson"].tool.item') == 5956
    lua.execute('GetItemInfoInstant = nil')
    # a recipe of the profession makes it but is not known: the trainer first
    lua.execute('names = { [9999] = "Blacksmith Hammer" }; C_TradeSkillUI.GetAllRecipeIDs = function() return { 2385, 9999 } end; '
                'C_TradeSkillUI.GetRecipeInfo = function(id) return { recipeID = id, name = names[id], learned = learned[id] or false } end; Fire("TRADE_SKILL_LIST_UPDATE")')
    assert text() == "Learn Blacksmith Hammer first" and tip()[-1].startswith("The arrow points at the nearest: Tailoring trainer")
    assert lua.eval('FWCS_DB.__chars["Stonespine|Thrallson"].tool') is None
    # a tool lacking comes before the walk: the hammer the profession makes is made first, at its
    # own anvil; made, the vest's anvil is next
    lua.execute('''
      reqs[2385] = { { name = "Anvil", met = false, type = 0 }, { name = "Blacksmith Hammer", met = false, type = 1 } }
      names = { [9999] = "Blacksmith Hammer" }
      C_TradeSkillUI.GetAllRecipeIDs = function() return { 2385, 9999 } end
      C_TradeSkillUI.GetRecipeInfo = function(id) return { recipeID = id, name = names[id], learned = learned[id] or false } end
      learned[9999] = true; reqs[9999] = { { name = "Anvil", met = false, type = 0 } }
      Fire("TRADE_SKILL_LIST_UPDATE")
    ''')
    assert text() == "Needs Anvil to make Blacksmith Hammer" and tip()[-1] == "The arrow points at the nearest: Anvil, 20 yd."
    lua.execute('reqs[9999] = {}; Fire("TRADE_SKILL_LIST_UPDATE")')
    assert text() == "Make 1 Blacksmith Hammer first"
    lua.execute("ForeverWowCraftMake.scripts.OnClick(ForeverWowCraftMake)")
    assert [list(r.values()) for r in lua.eval("crafted").values()][-1] == [9999, 1]
    # a place the client asks for that a recipe of the profession makes is a camp object (Forever,
    # 6 Nov 2026): made here, not looked for in the world; made and in the bags, placed
    lua.execute('''
      reqs[2385] = { { name = "Tanning Rack", met = false, type = 2 } }
      names = { [9998] = "Tanning Rack" }
      C_TradeSkillUI.GetAllRecipeIDs = function() return { 2385, 9998 } end
      learned[9998] = true; reqs[9998] = {}
      Fire("TRADE_SKILL_LIST_UPDATE")
    ''')
    assert text() == "Make 1 Tanning Rack first" and lua.eval("ForeverWowCraftMake.verdict.place") is None
    lua.execute('GetItemInfoInstant = function(name) if name == "Tanning Rack" then return 279941 end end; bags[0][5] = { 279941, 1 }; Fire("BAG_UPDATE_DELAYED")')
    assert text() == "Place Tanning Rack first" and lua.eval("ForeverWowCraftMake.mode") == "Place"
    assert tip()[-1] == "Brown Linen Vest needs Tanning Rack beside you: it is in your bags, place it at your camp."
    lua.execute('GetItemInfoInstant = nil; bags[0][5] = nil; learned[9998] = false; Fire("BAG_UPDATE_DELAYED")')
    assert text() == "Learn Tanning Rack first"                                        # not known: the trainer first, as a tool's recipe
    lua.execute('reqs[2385] = {}; learned[9998] = true; C_TradeSkillUI.GetAllRecipeIDs = function() return { 2385 } end; Fire("TRADE_SKILL_LIST_UPDATE")')
    lua.execute('reqs[2385] = { { name = "Anvil", met = false, type = 0 }, { name = "Blacksmith Hammer", met = true, type = 1 } }; Fire("TRADE_SKILL_LIST_UPDATE")')
    assert text() == "Needs Anvil"
    lua.execute('C_TradeSkillUI.GetAllRecipeIDs = nil; reqs[2385] = { { name = "Blacksmith Hammer", met = false, type = 1 } }; Fire("TRADE_SKILL_LIST_UPDATE")')
    # a station named by the client with another type is a place all the same
    lua.execute('reqs[2385] = { { name = "Forge", met = false, type = 0 } }; Fire("TRADE_SKILL_LIST_UPDATE")')
    assert text() == "Needs Forge" and tip()[-1].startswith("No forge seen yet")
    # something to buy from a vendor: the one seen selling it; from the auction house: the auctioneer
    lua.execute('bags[0] = {}; reqs[2385] = {}; Fire("BAG_UPDATE_DELAYED")')
    assert text() == "Buy at the auction house (1) and a vendor (1)" and tip()[-1].startswith("No auctioneer seen yet")
    lua.execute('px, py = 0.50, 0.40; Fire("AUCTION_HOUSE_SHOW"); px, py = 0.50, 0.50; Fire("BAG_UPDATE_DELAYED")')
    # a recipe to learn and reagents to buy: the nearer trip first, the other a note under the
    # arrow. The auctioneer 100 yd north, the trainer 300 yd south: buy first; by the trainer: learn first
    lua.execute('Fire("AUCTION_HOUSE_CLOSED"); learned[2385] = false; Fire("TRADE_SKILL_LIST_UPDATE")')     # the house closed: distances decide
    assert text().startswith("Buy") and lua.eval("ForeverWowCraftMake.verdict.aside.text") == "Then learn Brown Linen Vest at the trainer"
    lua.execute('px, py = 0.50, 0.78; Fire("TRADE_SKILL_LIST_UPDATE")')
    assert text() == "Learn Brown Linen Vest first" and lua.eval("ForeverWowCraftMake.verdict.aside.text") == "Then buy at the auction house (1) and a vendor (1)"
    lua.execute('px, py = 0.50, 0.50; learned[2385] = true; Fire("TRADE_SKILL_LIST_UPDATE")')
    assert tip()[-1] == "The arrow points at the nearest: Auctioneer, 100 yd."
    # put away by a right-click; ticking Keep arrow brings it back
    lua.execute('ForeverWowCraftArrow.scripts.OnMouseUp(ForeverWowCraftArrow, "RightButton")')
    assert arrow().shown is False
    lua.execute('ForeverWowCraftKeepArrow.scripts.OnClick(ForeverWowCraftKeepArrow)')
    assert arrow().shown is True and arrow().text.text.endswith("(Buy at the auction house (1) and a vendor (1))")
    # the overview page, no profession open: the tab says so and the arrow stays
    lua.execute('local was = C_TradeSkillUI.GetBaseProfessionInfo; C_TradeSkillUI.GetBaseProfessionInfo = function() return nil end; '
                'Fire("BAG_UPDATE_DELAYED"); C_TradeSkillUI.GetBaseProfessionInfo = was')
    assert text() == "No profession open" and arrow().shown is True
    lua.execute('Fire("BAG_UPDATE_DELAYED")')
    # Keep arrow unticked: the window closed takes the arrow; opened again on its overview page,
    # the arrow is the profession's last shown, all the same (the dashboard is no profession)
    lua.execute('ForeverWowCraftKeepArrow.GetChecked = function() return false end; ForeverWowCraftKeepArrow.scripts.OnClick(ForeverWowCraftKeepArrow); Fire("TRADE_SKILL_CLOSE")')
    assert arrow().shown is False
    lua.execute('local was = C_TradeSkillUI.GetBaseProfessionInfo; C_TradeSkillUI.GetBaseProfessionInfo = function() return nil end; '
                'Fire("TRADE_SKILL_SHOW"); C_TradeSkillUI.GetBaseProfessionInfo = was')
    assert text() == "No profession open" and arrow().shown is True and arrow().text.text.startswith("Tailoring")
    lua.execute('ForeverWowCraftKeepArrow.GetChecked = function() return true end; ForeverWowCraftKeepArrow.scripts.OnClick(ForeverWowCraftKeepArrow); Fire("TRADE_SKILL_SHOW")')
    # the window closed with the box ticked: the arrow stays; and a reload (the world entered
    # again) brings it back by itself, from the profession last served, with no window opened
    lua.execute('Fire("TRADE_SKILL_CLOSE")')
    assert arrow().shown is True
    lua.execute('ns.ClearArrow(); Fire("PLAYER_ENTERING_WORLD"); RunTimers()')
    assert arrow().shown is True and arrow().text.text.startswith("Tailoring\nAuctioneer\n100 yd\n(Buy")
    # the skill list empty, as in the first moments of a login: nothing is read into it, the arrow stays
    lua.execute('GetNumSkillLines = function() return 0 end; Fire("SKILL_LINES_CHANGED"); RunTimers()')
    assert arrow().shown is True and lua.eval("ns.inv.Char().making") == "tailoring"
    lua.execute('GetNumSkillLines = function() return 2 end')
    # the profession unlearned (the skill line gone): the arrow set for it goes, and the button's
    # profession is forgotten; learned again, the pass without the window serves it anew
    lua.execute('GetSkillLineInfo = function() return "Professions", true end; Fire("SKILL_LINES_CHANGED")')
    assert arrow().shown is False and lua.eval("ns.inv.Char().making") is None
    lua.execute('GetSkillLineInfo = function(i) if i == 1 then return "Professions", true end return "Tailoring", false, false, skill end; Fire("SKILL_LINES_CHANGED")')
    assert arrow().shown is True and arrow().text.text.startswith("Tailoring\nAuctioneer\n100 yd\n(Buy")
    # at the auctioneer: no line for the way
    lua.execute('px, py = 0.50, 0.40; ForeverWowCraftArrow.scripts.OnUpdate(ForeverWowCraftArrow, 1)')
    assert arrow().text.text.startswith("Tailoring\nAuctioneer\n(Buy")
    lua.execute('px, py = 0.50, 0.50; ForeverWowCraftArrow.scripts.OnUpdate(ForeverWowCraftArrow, 1)')
    # unticked with the window closed: the arrow goes, and a reload leaves it be
    lua.execute('ForeverWowCraftKeepArrow.GetChecked = function() return false end; ForeverWowCraftKeepArrow.scripts.OnClick(ForeverWowCraftKeepArrow)')
    assert arrow().shown is False
    lua.execute('Fire("PLAYER_ENTERING_WORLD"); RunTimers()')
    assert arrow().shown is False
    lua.execute('ForeverWowCraftKeepArrow.GetChecked = function() return true end; ForeverWowCraftKeepArrow.scripts.OnClick(ForeverWowCraftKeepArrow)')
    assert arrow().shown is True
    lua.execute('Fire("TRADE_SKILL_SHOW")')
    # the overview tile fires "closed" with the window still shown: with Keep arrow unticked the
    # arrow stays, and goes only when the window itself hides
    lua.execute('ForeverWowCraftKeepArrow.GetChecked = function() return false end; ForeverWowCraftKeepArrow.scripts.OnClick(ForeverWowCraftKeepArrow); '
                'ProfessionsFrame.IsShown = function() return true end; Fire("TRADE_SKILL_CLOSE")')
    assert arrow().shown is True
    lua.execute('ProfessionsFrame.IsShown = function() return false end; Fire("TRADE_SKILL_CLOSE")')
    assert arrow().shown is False
    lua.execute('ProfessionsFrame.IsShown = nil; ForeverWowCraftKeepArrow.GetChecked = function() return true end; ForeverWowCraftKeepArrow.scripts.OnClick(ForeverWowCraftKeepArrow); Fire("TRADE_SKILL_SHOW")')
    # /fwcs arrow says where it points; off: nothing is pointed at
    lua.execute('ns.ArrowCommand("")')
    assert lua.eval("printed[#printed]").endswith("the arrow points at Auctioneer, 100 yd. /fwcs arrow off turns it off.")
    # dragged, it keeps where it was put, across reloads (the setting), and /fwcs arrow reset puts it back
    lua.execute('ForeverWowCraftArrow.SetPoint = function(a, ...) a.point = { ... } end; ForeverWowCraftArrow.GetPoint = function() return "TOPLEFT", UIParent, "TOPLEFT", 40, -300 end; '
                'ForeverWowCraftArrow.scripts.OnDragStart(ForeverWowCraftArrow); ForeverWowCraftArrow.scripts.OnDragStop(ForeverWowCraftArrow)')
    assert list(lua.eval("ns.Settings().arrowPos").values()) == ["TOPLEFT", "TOPLEFT", 40, -300]
    lua.execute('ns.ArrowCommand("reset")')
    assert lua.eval("ns.Settings().arrowPos") is None and list(lua.eval("ForeverWowCraftArrow.point").values())[2:] == ["TOP", 0, -120]
    assert lua.eval("printed[#printed]").endswith("the arrow is back at the top of the screen")
    lua.execute('ns.ArrowCommand("off"); Fire("BAG_UPDATE_DELAYED")')
    assert arrow().shown is False and lua.eval("printed[#printed]").endswith("the arrow is off (/fwcs arrow on brings it back)")
    lua.execute('ns.ArrowCommand("")')
    assert lua.eval("printed[#printed]").endswith("the arrow is off: /fwcs arrow on brings it back")


def test_a_trainer_that_says_how_far_it_teaches_comes_first_for_a_rank():
    lua = _game()
    lua.execute(PLACES_GAME)
    # two trainers noted: the near one says nothing of how far it teaches, the far one teaches to 200
    lua.execute('px, py = 0.50, 0.50; ns.NotePlace("trainer", "tailoring", { name = "Near, unsure" }); '
                'px, py = 0.50, 0.70; ns.NotePlace("trainer", "tailoring", { name = "Far, artisan", upto = 200 }); px, py = 0.50, 0.50')
    assert lua.eval('(ns.NearestPlace("trainer", "tailoring", nil, 76))').name == "Far, artisan"     # a rank past 75: the one that teaches it
    assert lua.eval('(ns.NearestPlace("trainer", "tailoring"))').name == "Near, unsure"              # a recipe: the nearest
    # a visited trainer keeps the highest skill its services ask for
    lua.execute('px, py = 0.50, 0.50; services = { "Brown Linen Vest" }; skillreq = { "Tailoring" }; '
                'GetTrainerServiceSkillReq = function(i) return skillreq[i], 125 end; Fire("TRAINER_SHOW")')
    near = lua.eval('(ns.NearestPlace("trainer", "tailoring", nil, 100))')                          # the visit merged into the near one, named now
    assert near.name == "Thrallson" and near.upto == 125
    # a rank training among the services says how far the trainer teaches, whatever its recipes
    # ask for (a specialist's recipes at 240 are not a rank); the seed knows the names
    lua.execute('services = { "Brown Linen Vest", "Expert Tailoring" }; skillreq = { "Tailoring", "Tailoring" }; '
                'GetTrainerServiceSkillReq = function(i) return skillreq[i], 240 end; Fire("TRAINER_SHOW")')
    assert lua.eval('(ns.NearestPlace("trainer", "tailoring", nil, 100))').upto == 225
    lua.execute('services = { "Expertenschneiderei" }; skillreq = { "Tailoring" }; Fire("TRAINER_SHOW")')
    assert lua.eval('(ns.NearestPlace("trainer", "tailoring", nil, 100))').upto == 225


# ---- what the list and the arrow serve: a profession the character has --------------------------------
def test_the_list_and_the_arrow_serve_only_a_profession_the_character_has():
    lua = _game()
    lua.execute(PLACES_GAME)
    lua.execute('C_Item.GetItemCount = GetItemCount; GetItemCount = nil; skill = 44; bags[0] = {}')
    # the character is a tailor: the list is tailoring's, and so is the profession served
    assert lua.eval("ns.OwnProfession()") == "tailoring" and lua.eval("ns.craft.Shopping().title").startswith("White Linen Shirt")
    # a cook too, nothing picked or shown: the primary profession is served, not the secondary that sorts first
    lua.execute('GetNumSkillLines = function() return 3 end; GetSkillLineInfo = function(i) if i == 1 then return "Professions", true end '
                'if i == 2 then return "Cooking", false, false, 10 end return "Tailoring", false, false, skill end; ns.inv.NoteSkills()')
    assert lua.eval("ns.inv.Char().skills[185]") == 10 and lua.eval("ns.OwnProfession()") == "tailoring"
    # the window's pick is a profession the character does not have: the window may show it, the list and the arrow do not follow
    lua.execute('ns.inv.Char().picked = "enchanting"')
    assert lua.eval("ns.ChosenProfession()") == "enchanting" and lua.eval("ns.OwnProfession()") == "tailoring"
    assert lua.eval("ns.craft.Shopping().title").startswith("White Linen Shirt")
    # tailoring unlearned (no skill line): nothing is served, and the list is empty rather than a route from skill 1
    lua.execute('GetSkillLineInfo = function() return "Professions", true end; ns.inv.Char().picked = "tailoring"; ns.inv.NoteSkills()')
    assert lua.eval("ns.OwnProfession()") is None and lua.eval("#ns.craft.Shopping()") == 0
    # the button's last profession is checked the same way
    lua.execute('ns.inv.Char().making = "tailoring"')
    assert lua.eval("#ns.craft.Shopping()") == 0


# ---- the buying first, the scan after -----------------------------------------------------------------
def test_the_snapshot_by_itself_waits_while_the_shopping_list_has_buying_to_do():
    lua = _game()
    lua.execute(PLACES_GAME)
    # the house open with the list up (the cloth to buy here), the bar hidden (so the snapshot
    # is taken by itself), the cooldown over; the house's search calls as the shop test has them
    lua.execute('''
      C_Item.GetItemCount = GetItemCount; GetItemCount = nil
      C_AuctionHouse.MakeItemKey = function(item) return { itemID = item } end
      C_AuctionHouse.GetItemKeyInfo = function(key) return { isCommodity = true } end
      C_AuctionHouse.IsThrottledMessageSystemReady = function() return true end
      C_AuctionHouse.SendSearchQuery = function(key) end
      C_AuctionHouse.ReplicateItems = function() end
      AuctionHouseFrame = CreateFrame("Frame"); AuctionHouseFrame.shown = true
      FWCS_FRESH = {}; skill = 44; bags[0] = { { 2589, 4 } }
      Fire("AUCTION_HOUSE_SHOW")
    ''')
    assert lua.eval("ForeverWowCraftShop.shown") is True and lua.eval("ns.ShoppingBusy()") is True
    started = lambda: any("full AH snapshot requested" in p for p in lua.eval("printed").values())  # noqa: E731
    lua.execute("RunTimers()")                                                 # a second after the house opened: the list is busy
    assert not started()
    lua.execute("RunTimers()")                                                 # and two seconds later still
    assert not started() and len(lua.eval("timers")) == 1
    # the cloth had: nothing left to buy here, the snapshot starts at the next look
    lua.execute('bags[0] = { { 2589, 14 } }; Fire("BAG_UPDATE_DELAYED")')
    assert lua.eval("ns.ShoppingBusy()") is False
    lua.execute("RunTimers()")
    assert started()
    # the list closed counts the same; and a vendor's row, or one nobody lists, is no buying to do here
    lua.execute('bags[0] = { { 2589, 4 } }; Fire("AUCTION_HOUSE_CLOSED"); Fire("AUCTION_HOUSE_SHOW")')
    assert lua.eval("ns.ShoppingBusy()") is True
    lua.execute("ForeverWowCraftShop:Hide()")
    assert lua.eval("ns.ShoppingBusy()") is False
    lua.execute('Fire("AUCTION_HOUSE_CLOSED")')


# ---- the arrow's switch in the window ------------------------------------------------------------------
def test_the_window_has_a_box_that_turns_the_arrow_off_and_on():
    lua = _game()
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("")')
    assert lua.eval("ForeverWowCraftArrowBox.shown") is True and lua.eval("ForeverWowCraftArrowBox.label.text") == "Arrow"
    assert lua.eval("ns.Settings().arrow") is None                                   # on, as the addon comes
    lua.execute('ForeverWowCraftArrowBox.GetChecked = function() return false end; ForeverWowCraftArrowBox.scripts.OnClick(ForeverWowCraftArrowBox)')
    assert lua.eval("ns.Settings().arrow") is False and lua.eval("printed[#printed]").endswith("the arrow is off (/fwcs arrow on brings it back)")
    lua.execute('ForeverWowCraftArrowBox.GetChecked = function() return true end; ForeverWowCraftArrowBox.scripts.OnClick(ForeverWowCraftArrowBox)')
    assert lua.eval("ns.Settings().arrow") is None and "the arrow is on" in lua.eval("printed[#printed]")
    # the command and the box are one switch: the box follows the command at the next draw
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("arrow off"); ForeverWowCraftArrowBox.SetChecked = function(s, on) s.checked = on end; '
                'SlashCmdList.FOREVERWOWCRAFT(""); SlashCmdList.FOREVERWOWCRAFT("")')         # closed and opened again: drawn again
    assert lua.eval("ForeverWowCraftArrowBox.checked") is False


# ---- a snapshot lost with the window is let go when the house opens again -----------------------------
def test_a_snapshot_awaited_when_the_house_closes_is_let_go_when_it_opens_again():
    lua = _game()
    lua.execute(PLACES_GAME)
    lua.execute('''
      C_Item.GetItemCount = GetItemCount; GetItemCount = nil
      C_AuctionHouse.MakeItemKey = function(item) return { itemID = item } end
      C_AuctionHouse.GetItemKeyInfo = function(key) return { isCommodity = true } end
      C_AuctionHouse.IsThrottledMessageSystemReady = function() return true end
      C_AuctionHouse.SendSearchQuery = function(key) end
      replicated, shift = 0, false
      C_AuctionHouse.ReplicateItems = function() replicated = replicated + 1 end
      function IsShiftKeyDown() return shift end
      AuctionHouseFrame = CreateFrame("Frame"); AuctionHouseFrame.shown = true
      FWCS_FRESH = {}; skill = 44; bags[0] = { { 2589, 14 } }
      Fire("AUCTION_HOUSE_SHOW"); RunTimers()
    ''')
    assert lua.eval("replicated") == 1 and lua.eval("ns.scanner.Running()") is True
    assert lua.eval("ForeverWowCraftAHButton.text") == "Scanning..."
    # closed before the server answered, opened again: the wait is let go at once, the cooldown
    # shown from the ask (not two minutes of "Scanning..." first), no second ask by itself
    lua.execute('Fire("AUCTION_HOUSE_CLOSED"); Fire("AUCTION_HOUSE_SHOW"); RunTimers()')
    assert "the snapshot awaited was lost with the window" in lua.eval("printed[#printed]") and "shift-click the button to try sooner" in lua.eval("printed[#printed]")
    assert lua.eval("replicated") == 1 and lua.eval("ns.scanner.Running()") is False
    assert abs(lua.eval("FWCS_DB.__ui.lastFullRefused") - lua.eval("time()")) <= 1
    assert re.match(r"\|cff808080Prices in 1[45]:\d\d\|r$", lua.eval("ForeverWowCraftAHButton.text"))
    # the first ask's timers fire later: they belong to the ask let go, and change nothing
    lua.execute("RunTimers()")
    assert lua.eval("ns.scanner.Running()") is False and lua.eval("replicated") == 1
    # a shift-click tries sooner, for whoever wants to see whether the server answers
    lua.execute("shift = true; ForeverWowCraftAHButton.scripts.OnClick(ForeverWowCraftAHButton)")
    assert lua.eval("replicated") == 2 and lua.eval("ns.scanner.Running()") is True
    lua.execute('Fire("AUCTION_HOUSE_CLOSED")')


# ---- the freshness gate: no scan box while the house's newest scan is fresh --------------------------
def test_the_scan_box_is_not_offered_while_the_house_was_scanned_lately_by_anyone():
    lua = _game()
    lua.execute(PLACES_GAME)
    box = lambda: lua.eval('rawget(ForeverWowCraftScannerStatus, "mode")')  # noqa: E731
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("bar")')                  # the stand-in keeps the bar hidden: shown here
    assert lua.eval("printed[#printed]").endswith("the scanner's bar is shown (FULL / SCAN / SAVE)")
    # nothing from the pipe: the box every time
    lua.execute('FWCS_FRESH = {}; Fire("AUCTION_HOUSE_SHOW")')
    assert box() == "scan"
    # the house's newest scan is fresh, told lately: no box this visit; /fwcs offer brings it
    lua.execute('FWCS_FRESH = { written = time() - 60, fresh = 600, houses = { Stonespine = { Horde = { newest = time() - 120 } } } }; '
                'Fire("AUCTION_HOUSE_CLOSED"); Fire("AUCTION_HOUSE_SHOW")')
    assert box() is None
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("offer")')
    assert box() == "scan" and lua.eval("printed[#printed]").endswith("the FULL / SCAN box is offered this visit")
    # decided once a visit: the scan going stale meanwhile changes nothing until the house is opened again
    lua.execute('Fire("AUCTION_HOUSE_CLOSED"); Fire("AUCTION_HOUSE_SHOW")')
    assert box() is None
    lua.execute('FWCS_FRESH.houses.Stonespine.Horde.newest = time() - 700; Fire("BAG_UPDATE_DELAYED")')
    assert box() is None
    lua.execute('Fire("AUCTION_HOUSE_CLOSED"); Fire("AUCTION_HOUSE_SHOW")')
    assert box() == "scan"
    # told long ago (the helper not running): the freshness is not trusted, the box shows
    lua.execute('FWCS_FRESH.written = time() - 7200; FWCS_FRESH.houses.Stonespine.Horde.newest = time() - 60; Fire("AUCTION_HOUSE_CLOSED"); Fire("AUCTION_HOUSE_SHOW")')
    assert box() == "scan"
    # away from the house, /fwcs offer says when it was scanned and whether the box would show
    lua.execute('FWCS_FRESH.written = time() - 60; Fire("AUCTION_HOUSE_CLOSED"); SlashCmdList.FOREVERWOWCRAFTSCANNER("offer")')
    assert "Stonespine (Horde) was last scanned by anyone 1 min ago: fresh for 9 min more, so no box until then" in lua.eval("printed[#printed]")
    # the house of a faction the pipe did not name falls to the realm's unnamed one; another realm: every time
    lua.execute('FWCS_FRESH.houses.Stonespine = { [""] = { newest = time() - 10 } }; Fire("AUCTION_HOUSE_SHOW")')
    assert box() is None
    lua.execute('Fire("AUCTION_HOUSE_CLOSED"); FWCS_FRESH.houses = { Elsewhere = { Horde = { newest = time() - 10 } } }; Fire("AUCTION_HOUSE_SHOW")')
    assert box() == "scan"
    lua.execute('Fire("AUCTION_HOUSE_CLOSED")')


def test_the_shopping_list_goes_on_during_a_full_snapshot_once_the_house_is_free():
    lua = _game()
    lua.execute(PLACES_GAME)
    # the house open with the list up and a snapshot started by hand; the house not free (the
    # client's throttled message system) until the test says so
    lua.execute('''
      C_Item.GetItemCount = GetItemCount; GetItemCount = nil
      searched, started, ready = {}, {}, false
      C_AuctionHouse.MakeItemKey = function(item) return { itemID = item } end
      C_AuctionHouse.GetItemKeyInfo = function(key) return { isCommodity = true } end
      C_AuctionHouse.IsThrottledMessageSystemReady = function() return ready end
      C_AuctionHouse.SendSearchQuery = function(key) table.insert(searched, key.itemID) end
      C_AuctionHouse.GetNumCommoditySearchResults = function(item) return item == 2589 and 3 or 0 end
      C_AuctionHouse.GetCommoditySearchResultInfo = function(item, i) return { quantity = 4 } end
      C_AuctionHouse.StartCommoditiesPurchase = function(item, n) table.insert(started, { item, n }) end
      C_AuctionHouse.ReplicateItems = function() end
      AuctionHouseFrame = CreateFrame("Frame"); AuctionHouseFrame.shown = true
      FWCS_FRESH = {}; skill = 44; bags[0] = { { 2589, 4 } }
      Fire("AUCTION_HOUSE_SHOW")
      SlashCmdList.FOREVERWOWCRAFTSCANNER("full force")
      table.remove(timers); table.remove(timers)      -- the snapshot's own patience and timeout, queued last: not run here
    ''')
    shop = lambda path: lua.eval("ForeverWowCraftShop." + path)  # noqa: E731
    said = lambda text: any(text in p for p in lua.eval("printed").values())  # noqa: E731
    click = lambda: lua.execute("ForeverWowCraftShop.rows[1].buy.scripts.OnClick(ForeverWowCraftShop.rows[1].buy)")  # noqa: E731
    assert lua.eval("ns.scanner.Snapshot()") is True and said("full AH snapshot requested")
    # the list's search of the cloth waits for the house, says so once, and keeps waiting
    lua.execute("RunTimers()")
    assert shop("rows[1].status.text") == "waiting for the house..." and said("the house is answering the snapshot: the list goes on when it is free")
    assert list(lua.eval("searched").values()) == []
    lua.execute("RunTimers()")
    once = lambda text: sum(text in p for p in lua.eval("printed").values())  # noqa: E731
    assert shop("rows[1].status.text") == "waiting for the house..." and once("the house is answering the snapshot") == 1
    click()                                                                                  # a click meanwhile: told, nothing sent
    assert said("the row says Buy when it is free") and len(lua.eval("started")) == 0
    # the house free (the snapshot answered, or refused): the search goes, the wait is told
    lua.execute("ready = true; RunTimers()")
    assert list(lua.eval("searched").values()) == [2589] and shop("rows[1].status.text") == "searching..."
    assert said("the house is free again after 0 s: the list goes on")
    lua.execute('Fire("COMMODITY_SEARCH_RESULTS_UPDATED", 2589)')
    assert shop("rows[1].buy.text") == "Buy 10"
    # a buy while the house is busy again is held back; free, it goes, the snapshot still running
    lua.execute("ready = false")
    click()
    assert said("the house is busy answering the snapshot: a moment, then click again") and len(lua.eval("started")) == 0
    lua.execute("ready = true")
    click()
    assert [list(r.values()) for r in lua.eval("started").values()] == [[2589, 10]] and lua.eval("ns.scanner.Running()") is True
    lua.execute('Fire("AUCTION_HOUSE_CLOSED")')


def test_a_snapshot_already_answered_is_read_on_after_the_house_closes():
    lua = _game()
    lua.execute(PLACES_GAME)
    # a snapshot by hand, answered with 600 auctions (read 500 a frame), every one 5 of the
    # cloth for 50c: the count is the 3rd of GetReplicateItemInfo's values, the buyout the 10th,
    # the item the 17th
    lua.execute('''
      FrameUtil = { RegisterFrameForEvents = function(f, evs) for _, e in ipairs(evs) do f:RegisterEvent(e) end end,
                    UnregisterFrameForEvents = function(f, evs) for _, e in ipairs(evs) do f:UnregisterEvent(e) end end }
      C_AuctionHouse.ReplicateItems = function() end
      listed = 600
      C_AuctionHouse.GetNumReplicateItems = function() return listed end
      C_AuctionHouse.GetReplicateItemInfo = function(i)
        return "Linen Cloth", nil, 5, nil, nil, nil, nil, nil, nil, 50, nil, nil, nil, nil, nil, nil, 2589, true
      end
      AuctionHouseFrame = CreateFrame("Frame"); AuctionHouseFrame.shown = true
      FWCS_FRESH = {}
      Fire("AUCTION_HOUSE_SHOW")
      SlashCmdList.FOREVERWOWCRAFTSCANNER("full force")
      table.remove(timers); table.remove(timers)      -- the snapshot's own patience and timeout: not run here
      Fire("REPLICATE_ITEM_LIST_UPDATE")
    ''')
    said = lambda text: any(text in p for p in lua.eval("printed").values())  # noqa: E731
    assert lua.eval("ns.scanner.Running()") is True and lua.eval("ns.scanner.Dirty()") is False
    # the house closes with 500 of the 600 read: the reading goes on, and ends with the record
    lua.execute('Fire("AUCTION_HOUSE_CLOSED")')
    assert lua.eval("ns.scanner.Running()") is True and said("closed while the snapshot is read (500 of 600 auctions): reading on")
    lua.execute("RunTimers()")
    assert lua.eval("ns.scanner.Running()") is False and lua.eval("ns.scanner.Dirty()") is True
    # SAVE: a secure button over the bar with a macro of its own, /reload, shown with the save mode (Forever's
    # client lets no addon call ReloadUI, 6 Nov 2026); gone again when the bar is something else
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("bar"); ns.scanner.Refresh()')
    assert lua.eval("printed[#printed]").endswith("the scanner's bar is shown (FULL / SCAN / SAVE)")
    assert lua.eval('rawget(ForeverWowCraftScannerStatus, "mode")') == "save" and lua.eval("ForeverWowCraftScannerSave.shown") is True
    assert "SecureActionButtonTemplate" in lua.eval("ForeverWowCraftScannerSave.template")
    assert lua.eval("ForeverWowCraftScannerSave.attributes.macrotext") == "/reload" and lua.eval("ForeverWowCraftScannerSave.attributes.type") == "macro"
    assert said("the snapshot was read after the auction house closed: that works")
    assert said("snapshot finished") and not said("aborted")
    # the list gone with the window (the client cleared it): the reading stops and says so, nothing recorded
    lua.execute('''
      Fire("AUCTION_HOUSE_SHOW")
      SlashCmdList.FOREVERWOWCRAFTSCANNER("full force")
      table.remove(timers); table.remove(timers)
      Fire("REPLICATE_ITEM_LIST_UPDATE")
      Fire("AUCTION_HOUSE_CLOSED")
      listed = 0
      RunTimers()
    ''')
    assert lua.eval("ns.scanner.Running()") is False
    assert said("the auction list went with the window: the snapshot is lost") and said("aborted (the auction list went with the window)")
    # closed before the answer came: the snapshot waits on, and reads the answer when it comes
    lua.execute('''
      Fire("AUCTION_HOUSE_SHOW")
      SlashCmdList.FOREVERWOWCRAFTSCANNER("full force")
      table.remove(timers); table.remove(timers)
      Fire("AUCTION_HOUSE_CLOSED")
    ''')
    assert lua.eval("ns.scanner.Running()") is True and said("closed while the snapshot is awaited")
    lua.execute('listed = 600; Fire("REPLICATE_ITEM_LIST_UPDATE"); RunTimers()')
    assert lua.eval("ns.scanner.Running()") is False and lua.eval("printed[#printed]").find("snapshot finished") >= 0
    assert not said("aborted (auction house closed)")
    # SAVE in a fight: the secure button is left as it is (a protected frame is neither shown nor hidden in
    # combat), and set as the bar is when the fight ends
    lua.execute("ns.scanner.Refresh()")
    assert lua.eval('rawget(ForeverWowCraftScannerStatus, "mode")') == "save" and lua.eval("ForeverWowCraftScannerSave.shown") is True
    lua.execute('''
      InCombatLockdown = function() return true end
      Fire("AUCTION_HOUSE_SHOW")
      SlashCmdList.FOREVERWOWCRAFTSCANNER("full force")
      table.remove(timers); table.remove(timers)
    ''')
    assert lua.eval("ns.scanner.Running()") is True and lua.eval("ForeverWowCraftScannerSave.shown") is True
    lua.execute('InCombatLockdown = function() return false end; Fire("PLAYER_REGEN_ENABLED")')
    assert lua.eval("ForeverWowCraftScannerSave.shown") is False


# ---- buying at the auction house (Shop.lua) ---------------------------------------------------
def test_the_shopping_list_buys_from_a_vendor_a_stack_a_click():
    lua = _game()
    lua.execute(PLACES_GAME)
    # a merchant selling the thread (10c, singly, five a purchase) and a sword, not the dye;
    # the cloth is had, so the step needs the thread and the dye
    lua.execute('''
      C_Item.GetItemCount = GetItemCount; GetItemCount = nil
      bought = {}
      wares = { 2320, 25 }
      function GetMerchantItemInfo(i) if i == 1 then return "Coarse Thread", "tex", 10, 1, -1, true, true end return "Sword", "tex", 500, 1, -1, true, true end
      function GetMerchantItemMaxStack(i) return 5 end
      function BuyMerchantItem(i, n) table.insert(bought, { i, n }) end
      MerchantFrame = CreateFrame("Frame")
      skill = 44
      bags[0] = { { 2589, 14 } }
      Fire("MERCHANT_SHOW")
    ''')
    shop = lambda path: lua.eval("ForeverWowCraftShop." + path)  # noqa: E731
    plain = lambda path: re.sub(r"\|c[0-9a-fA-F]{8}|\|r", "", shop(path))  # noqa: E731
    click = lambda i=1: lua.execute(f"ForeverWowCraftShop.rows[{i}].buy.scripts.OnClick(ForeverWowCraftShop.rows[{i}].buy)")  # noqa: E731
    # the list opened with the merchant, docked: the thread with a button for a stack, the dye not here
    assert shop("shown") is True and shop("docked") is True and shop("title.text") == "White Linen Shirt, skill 44 to 51, needs"
    assert shop("rows[1].name.text") == "Coarse Thread" and shop("rows[1].need.text") == "need 7, have 0"
    assert shop("rows[1].buy.text") == "Buy 5" and shop("rows[1].buy.shown") is True and plain("rows[1].status.text") == "50c"
    assert shop("rows[2].name.text") == "Bleach" and shop("rows[2].status.text") == "not here" and shop("rows[2].buy.shown") is False
    assert "up to a stack a click" in shop("note.text")
    # a click: five bought in one call, the button dead until the bags say; then the two left
    click()
    assert [list(r.values()) for r in lua.eval("bought").values()] == [[1, 5]] and shop("rows[1].buy.enabled") is False
    click()
    assert len(lua.eval("bought")) == 1
    lua.execute('bags[0] = { { 2589, 14 }, { 2320, 5 } }; Fire("BAG_UPDATE_DELAYED")')
    assert shop("rows[1].name.text") == "Bleach"                                        # the one with more missing comes first now
    assert shop("rows[2].need.text") == "need 7, have 5" and shop("rows[2].buy.text") == "Buy 2" and shop("rows[2].buy.enabled") is True and plain("rows[2].status.text") == "20c"
    click(2)
    assert [list(r.values()) for r in lua.eval("bought").values()] == [[1, 5], [1, 2]]
    lua.execute('bags[0] = { { 2589, 14 }, { 2320, 7 } }; Fire("BAG_UPDATE_DELAYED")')
    assert shop("rows[1].name.text") == "Bleach" and shop("rows[1].status.text") == "not here"
    # the merchant closed: the list goes with it; a merchant selling nothing of the step opens none
    lua.execute('Fire("MERCHANT_CLOSED")')
    assert shop("shown") is False
    lua.execute('wares = { 25 }; Fire("MERCHANT_SHOW")')
    assert shop("shown") is False
    # one selling in bundles of five, two bundles a click: the seven missing are two bundles, ten
    lua.execute('wares = { 2324 }; GetMerchantItemInfo = function(i) return "Bleach", "tex", 25, 5, -1, true, true end; GetMerchantItemMaxStack = function() return 10 end; '
                'Fire("MERCHANT_CLOSED"); Fire("MERCHANT_SHOW")')
    assert shop("shown") is True and shop("rows[1].name.text") == "Bleach" and shop("rows[1].buy.text") == "Buy 10" and plain("rows[1].status.text") == "50c"
    click()
    assert list(lua.eval("bought[3]").values()) == [1, 2]
    lua.execute('Fire("MERCHANT_CLOSED")')


def test_the_shopping_list_buys_at_the_auction_house_a_click_and_a_confirm_each():
    lua = _game()
    lua.execute(PLACES_GAME)
    # the house's buying calls, recorded; every reagent is a commodity. The bags are counted as
    # Forever's client has it: C_Item.GetItemCount, and no GetItemCount global
    lua.execute('''
      C_Item.GetItemCount = GetItemCount; GetItemCount = nil
      searched, started, confirmed = {}, {}, {}
      C_AuctionHouse.MakeItemKey = function(item) return { itemID = item } end
      C_AuctionHouse.GetItemKeyInfo = function(key) return { isCommodity = true } end
      C_AuctionHouse.IsThrottledMessageSystemReady = function() return true end
      C_AuctionHouse.SendSearchQuery = function(key) table.insert(searched, key.itemID) end
      C_AuctionHouse.GetNumCommoditySearchResults = function(item) return item == 2589 and 3 or 0 end
      qty = 4
      C_AuctionHouse.GetCommoditySearchResultInfo = function(item, i) return { quantity = qty } end
      C_AuctionHouse.StartCommoditiesPurchase = function(item, n) table.insert(started, { item, n }) end
      C_AuctionHouse.ConfirmCommoditiesPurchase = function(item, n) table.insert(confirmed, { item, n }) end
      AuctionHouseFrame = CreateFrame("Frame")
      -- the character is a tailor at 44 with 4 of the 14 cloth; the window shows tailoring
      skill = 44
      bags[0] = { { 2589, 4 } }
      Fire("AUCTION_HOUSE_SHOW")
    ''')
    shop = lambda path: lua.eval("ForeverWowCraftShop." + path)  # noqa: E731
    plain = lambda path: re.sub(r"\|c[0-9a-fA-F]{8}|\|r", "", shop(path))  # noqa: E731
    click = lambda: lua.execute("ForeverWowCraftShop.rows[1].buy.scripts.OnClick(ForeverWowCraftShop.rows[1].buy)")  # noqa: E731
    # the list opened with the house, docked, the step's needs less the bags; the cloth searched ahead
    assert shop("shown") is True and shop("docked") is True
    assert shop("title.text") == "White Linen Shirt, skill 44 to 51, needs"
    assert shop("rows[1].name.text") == "Linen Cloth" and shop("rows[1].need.text") == "need 14, have 4"
    assert shop("rows[2].status.text") == "vendor" and shop("rows[2].buy.shown") is False
    assert list(lua.eval("searched").values()) == [2589] and shop("rows[1].status.text") == "searching..."
    lua.execute('Fire("COMMODITY_SEARCH_RESULTS_UPDATED", 2589)')
    assert plain("rows[1].status.text") == "about 3s 00c" and shop("rows[1].buy.text") == "Buy 10" and shop("rows[1].buy.shown") is True
    # Buy 10, a click: the price asked for the 10 missing (a hardware event: never from an event handler)
    assert lua.eval("started[1]") is None
    click()
    assert [list(r.values()) for r in lua.eval("started").values()] == [[2589, 10]]
    assert shop("rows[1].buy.text") == "..." and len(lua.eval("started")) == 1
    click()                                                                                  # a click while the house prices: nothing more asked
    assert len(lua.eval("started")) == 1
    # the house silent (a call the client refused): given up after a while, the row takes a click again
    lua.execute('local f = table.remove(timers); f()')                                       # the give-up timer, queued last
    assert shop("rows[1].status.text") == "the house did not answer" and shop("rows[1].buy.enabled") is True and shop("rows[1].buy.text") == "Buy 10"
    click()
    lua.execute('Fire("COMMODITY_PRICE_UPDATED", 35, 350)')
    assert plain("rows[1].status.text") == "10 for 3s 50c (35c each)" and shop("rows[1].buy.text") == "Confirm" and shop("rows[1].buy.enabled") is True
    # Confirm, a click: bought, the button dead until the house says so; the bags then say done
    click()
    assert [list(r.values()) for r in lua.eval("confirmed").values()] == [[2589, 10]] and shop("rows[1].buy.enabled") is False
    click()                                                                                  # a second click buys nothing more
    assert len(lua.eval("confirmed")) == 1
    lua.execute('Fire("COMMODITY_PURCHASE_SUCCEEDED")')
    assert shop("rows[1].status.text") == "bought" and shop("rows[1].buy.enabled") is False and shop("rows[1].buy.text") == "Bought"
    # the bags not yet caught up: the row stays bought, its button dead, through a relabel
    lua.execute('Fire("BAG_UPDATE_DELAYED")')
    assert shop("rows[1].status.text") == "bought" and shop("rows[1].buy.enabled") is False
    # the bags changed: the list is the step's needs again, and the cloth, had, is off it
    lua.execute('bags[0] = { { 2589, 14 } }; Fire("BAG_UPDATE_DELAYED")')
    assert shop("rows[1].name.text") == "Coarse Thread" and shop("rows[1].need.text") == "need 7, have 0" and shop("rows[1].buy.shown") is False
    # the skill moved on with no skill event (as a vendor sale moves the bags): the bags' change alone
    # takes the list to the next step's needs, and back
    lua.execute('skill = 51; Fire("BAG_UPDATE_DELAYED")')
    assert shop("title.text") == "Brown Linen Vest, skill 51 to 60, needs"
    lua.execute('skill = 44; Fire("BAG_UPDATE_DELAYED")')
    assert shop("title.text") == "White Linen Shirt, skill 44 to 51, needs"
    # another profession opened in the professions book while the house is open: the list is
    # that one's, at once; and the first one's again when the book goes back to it
    lua.execute('''
      C_TradeSkillUI = { GetBaseProfessionInfo = function() return { professionID = 333, professionName = "Enchanting", skillLevel = 1 } end,
                         GetRecipeInfo = function() return { learned = true } end, GetRecipeRequirements = function() return {} end }
      ProfessionsFrame = { CraftingPage = { CreateAllButton = CreateFrame("Button") } }
      Fire("ADDON_LOADED", "Blizzard_Professions"); Fire("TRADE_SKILL_SHOW")
    ''')
    assert shop("title.text") == "Enchant Bracer - Minor Health, skill 1 to 60, needs" and shop("rows[1].name.text") == "Strange Dust"
    lua.execute('C_TradeSkillUI.GetBaseProfessionInfo = function() return { professionID = 197, professionName = "Tailoring", skillLevel = 44 } end; Fire("TRADE_SKILL_SHOW")')
    assert shop("title.text") == "White Linen Shirt, skill 44 to 51, needs"
    lua.execute('Fire("TRADE_SKILL_CLOSE")')
    # short again: searched afresh (the purchase changed what is listed); fewer units listed than
    # missing: the buy is of all that is listed, and the house saying the price moved has the
    # item searched again by itself
    # (the house closed and opened again: a buy of the cloth is allowed once more)
    lua.execute('bags[0] = {}; qty = 2; Fire("AUCTION_HOUSE_CLOSED"); Fire("AUCTION_HOUSE_SHOW")')
    cloth = lambda: [x for x in lua.eval("searched").values() if x == 2589]  # noqa: E731
    assert shop("shown") is True and cloth() == [2589, 2589]
    lua.execute('Fire("COMMODITY_SEARCH_RESULTS_UPDATED", 2589)')
    assert shop("rows[1].buy.text") == "Buy 6" and shop("rows[1].status.text") == "only 6 listed"
    click()
    assert [list(r.values()) for r in lua.eval("started").values()][-1] == [2589, 6]
    lua.execute('Fire("COMMODITY_PRICE_UNAVAILABLE")')
    assert shop("rows[1].status.text") == "searching..." and cloth() == [2589, 2589, 2589]
    # and now nobody lists it
    lua.execute('C_AuctionHouse.GetNumCommoditySearchResults = function() return 0 end')
    lua.execute('Fire("COMMODITY_SEARCH_RESULTS_UPDATED", 2589)')
    assert shop("rows[1].status.text") == "none listed" and shop("rows[1].buy.shown") is False
    # the house closed: the docked list goes; /fwcs shop off keeps it from opening
    lua.execute('Fire("AUCTION_HOUSE_CLOSED")')
    assert shop("shown") is False
    lua.execute('ns.ShopCommand("off"); Fire("AUCTION_HOUSE_SHOW")')
    assert shop("shown") is False
    lua.execute('ns.ShopCommand("")')
    assert "does not open with the auction house" in lua.eval("printed[#printed]")


if __name__ == "__main__":
    if lupa is None:
        print("skipped: no Lua here (pip install lupa); tests/lua_check.py still reads the addon's files")
        sys.exit(0)
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)


# ---- the reload reminder (Remind.lua) ---------------------------------------------------------
def test_the_reminder_to_reload_comes_when_due_and_waits_while_busy():
    lua = _game()
    r = lambda: lua.eval("ns.remind")  # noqa: E731
    assert r().Enabled() is True and lua.eval("ForeverWowCraftReload") is None            # nothing built until needed
    # not due yet: a quarter of an hour after the load
    lua.execute("ns.remind.Check()")
    assert lua.eval("ForeverWowCraftReload") is None
    # due, the helper runs (the routes may be newer): the box, with why; a sound once
    lua.execute("time = function() return os.time() + ns.remind.Every + 1 end; ns.remind.Check()")
    assert lua.eval("ForeverWowCraftReload.shown") is True
    assert lua.eval("ForeverWowCraftReload.why.text") == "the routes may have changed on the site."
    assert lua.eval("ForeverWowCraftReloadNow.text") == "Reload now"
    # a fight starts: the box goes, and is back as soon as it is over
    lua.execute("InCombatLockdown = function() return true end; ns.remind.Check()")
    assert lua.eval("ForeverWowCraftReload.shown") is False
    lua.execute("InCombatLockdown = function() return false end; ns.remind.Check()")
    assert lua.eval("ForeverWowCraftReload.shown") is True
    # Later: gone for a quarter of an hour
    lua.execute("ForeverWowCraftReloadLater.scripts.OnClick(ForeverWowCraftReloadLater); ns.remind.Check()")
    assert lua.eval("ForeverWowCraftReload.shown") is False
    lua.execute("time = function() return os.time() + 2 * ns.remind.Every + 2 end; ns.remind.Check()")
    assert lua.eval("ForeverWowCraftReload.shown") is True
    # a merchant window open: not now
    lua.execute("ForeverWowCraftReload:Hide(); MerchantFrame = CreateFrame('Frame'); MerchantFrame:Show(); ns.remind.Check()")
    assert lua.eval("ForeverWowCraftReload.shown") is False
    lua.execute("MerchantFrame:Hide(); ns.remind.Check()")
    assert lua.eval("ForeverWowCraftReload.shown") is True
    # Reload now is a secure button with a macro of its own, /reload (the game lets no addon call ReloadUI on
    # Forever's client, 6 Nov 2026): no OnClick of the addon's; the box goes with the click
    assert "SecureActionButtonTemplate" in lua.eval("ForeverWowCraftReloadNow.template")
    assert lua.eval("ForeverWowCraftReloadNow.attributes.type") == "macro" and lua.eval("ForeverWowCraftReloadNow.attributes.macrotext") == "/reload"
    assert lua.eval("ForeverWowCraftReloadNow.scripts.OnClick") is None
    lua.execute("ForeverWowCraftReloadNow.scripts.PostClick(ForeverWowCraftReloadNow)")
    assert lua.eval("ForeverWowCraftReload.shown") is False
    # the scanner's own try (the typed /fwcs save): ReloadUI when the client has it, else C_UI.Reload; a refusal is said
    lua.execute("reloaded = 0; C_UI = { Reload = function() reloaded = reloaded + 1 end }; ns.scanner.Reload()")
    assert lua.eval("reloaded") == 1
    lua.execute("ReloadUI = function() reloaded = reloaded + 10 end; ns.scanner.Reload()")
    assert lua.eval("reloaded") == 11
    lua.execute("ReloadUI = function() error('blocked') end; ns.scanner.Reload()")
    assert lua.eval("reloaded") == 11 and "the reload was refused" in lua.eval("printed[#printed]") and "/reload" in lua.eval("printed[#printed]")
    lua.execute("ReloadUI = nil")
    # nothing to say without the helper and nothing recorded: no box; something met: a reason
    lua.execute("FWCS_PLANS_WRITTEN = nil; time = function() return os.time() + 4 * ns.remind.Every end; ns.remind.Check()")
    assert lua.eval("ForeverWowCraftReload.shown") is False
    assert list(lua.eval("ns.remind.Reasons()").values()) == []
    lua.execute("ns.notedAt = time(); time = function() return os.time() + 6 * ns.remind.Every end; ns.remind.Check()")
    assert lua.eval("ForeverWowCraftReload.why.text") == "something noted, not yet saved." and lua.eval("ForeverWowCraftReload.shown") is True
    assert "vendor" not in lua.eval("ForeverWowCraftReload.why.text") and "place" not in lua.eval("ForeverWowCraftReload.why.text")
    # off, by the box's own button: no more; on again by the command; the options page has the switch
    lua.execute("ForeverWowCraftReloadOff.scripts.OnClick(ForeverWowCraftReloadOff)")
    assert lua.eval("ForeverWowCraftReload.shown") is False and lua.eval("FWCS_DB.__ui.remind") is False and r().Enabled() is False
    lua.execute("time = function() return os.time() + 8 * ns.remind.Every end; ns.remind.Check()")
    assert lua.eval("ForeverWowCraftReload.shown") is False
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("remind on")')
    assert r().Enabled() is True and "reload reminder on" in lua.eval("printed[#printed]")
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("remind now")')
    assert lua.eval("ForeverWowCraftReload.shown") is True
    lua.execute("time = os.time")


def test_the_window_says_which_camp_object_the_route_makes():
    doc = document()
    doc["plans"]["tailoring-trainer"]["camp"] = [[279941, 44, "Tanning Rack"]]
    doc["items"]["279941"] = "Tanning Rack"
    lua = _game(doc)
    lua.execute("ns.ToggleWindow()")
    text = lua.eval("ForeverWowCraftWindow.notice.text") if lua.eval("ForeverWowCraftWindow.notice") is not None else lua.globals().AllText()
    assert "At your camp:" in text and "makes Tanning Rack once, from skill 44" in text

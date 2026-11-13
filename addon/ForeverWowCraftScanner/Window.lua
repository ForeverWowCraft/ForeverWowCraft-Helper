-- The /fwc window: the site's routes for this character's auction house, less what the
-- character has (Inventory.lua), walked by Tailor.lua.
--
-- FWCS_PLANS (Plans.lua, written by the helper from the site) holds the routes.

local _, ns = ...
local Char, House, CountBags, CountBank, CountMail, NoteSkills, Have, PLACES =
  ns.inv.Char, ns.inv.House, ns.inv.CountBags, ns.inv.CountBank, ns.inv.CountMail,
  ns.inv.NoteSkills, ns.inv.Have, ns.inv.PLACES
local Button, RangeSlider = ns.Button, ns.RangeSlider

-- The skill range: two sliders that plan a part of the route (the site's slider). Meant to be
-- behind a subscription at go-live: with RANGE false the sliders are not built and the route
-- runs from the character's skill to its end, as before.
local RANGE = true

local WIDTH, HEIGHT, ROW = 760, 588 + (RANGE and 66 or 0), 17
local NOTICE_TOP = 152 + (RANGE and 66 or 0)        -- where the notices start, under the summary; the list starts under them
local PROF_WIDTH, PROF_GAP = 83, 4                  -- the row of profession buttons: eight across the window
local COLS = { 104, 64, 64, 64 }           -- the four number columns, right to left: cost, buy, have, need
local REFRESH_DELAY = 0.4                  -- seconds bag changes are gathered for before the window is drawn again

local win, Refresh, SetSliders, ShowRange, picker, DrawPicker, DrawProfessions
local reloadSwitchesOn = false        -- the empty window is in state A and the client can enable an addon: the Reload button also switches the Plans addon on (set by Refresh)
local last      -- what the window shows: { house, plan, mine = the route less what is had, from }

-- the window drawn again after a click that changes the route, and the arrow, the Make button
-- and the shopping list moved to it at once (Craft.lua)
local function Repoint()
  Refresh()
  if ns.RoutePicked then ns.RoutePicked() end
end

-- ================================================================ text
local function Money(copper)
  if not copper then return "|cff808080?|r" end
  local sign = copper < 0 and "-" or ""
  copper = math.floor(math.abs(copper) + 0.5)
  local g, s, c = math.floor(copper / 10000), math.floor(copper % 10000 / 100), copper % 100
  if g > 0 then return string.format("%s|cffffd700%dg|r |cffc7c7cf%02ds|r", sign, g, s) end
  if s > 0 then return string.format("%s|cffc7c7cf%ds|r |cffeda55f%02dc|r", sign, s, c) end
  return string.format("%s|cffeda55f%dc|r", sign, c)
end
ns.Money = Money

-- the same without colour, for an edit box: "12g 40s", "5c"
local function PlainMoney(copper)
  copper = math.floor(math.max(0, copper or 0) + 0.5)
  local g, s, c = math.floor(copper / 10000), math.floor(copper % 10000 / 100), copper % 100
  local parts = {}
  if g > 0 then table.insert(parts, g .. "g") end
  if s > 0 then table.insert(parts, s .. "s") end
  if c > 0 or #parts == 0 then table.insert(parts, c .. "c") end
  return table.concat(parts, " ")
end

-- an amount as typed: "12g 40s 5c", "12g40s", "40s", a bare number is gold ("12", "12.5").
-- Nil for nothing or nonsense.
local function ParseMoney(text)
  text = (text or ""):lower():gsub(",", "")
  if text:match("^%s*$") or text:match("[^%d%.%sgsc]") then return nil end
  local copper, any = 0, false
  for n, unit in text:gmatch("(%d+%.?%d*)%s*([gsc]?)") do
    any = true
    copper = copper + tonumber(n) * (unit == "s" and 100 or unit == "c" and 1 or 10000)
  end
  return any and math.floor(copper + 0.5) or nil
end

local function Age(t)
  if not t or t == 0 then return "never" end
  local mins = math.floor((time() - t) / 60)
  if mins < 90 then return mins .. " min ago" end
  if mins < 48 * 60 then return math.floor(mins / 60) .. " h ago" end
  return math.floor(mins / 1440) .. " days ago"
end
ns.Age = Age

local function Title(profession)
  return (profession:gsub("%-", " "):gsub("(%a)(%a*)", function(a, b) return a:upper() .. b end))
end
ns.Title = Title

-- ================================================================ names in the client's language
-- The routes come with English names. The client knows every item's name in its own language,
-- but only hands it over for an item it has met since login (`GetItemInfo` is nil for the
-- rest): so the window asks for the rest and is drawn again as they come, English in the
-- meantime. Recipes are spells, which the client knows at once.
local asked = {}                             -- item ids the client was asked to load

-- a client in another language, where the English names are not what it shows
local function Foreign()
  local locale = GetLocale and GetLocale() or "enUS"
  return locale ~= "enUS" and locale ~= "enGB"
end

-- the item's name as this client shows it, and whether it is the client's (else the English one)
local function ItemName(item, english)
  local get = C_Item and C_Item.GetItemInfo or GetItemInfo
  local name = get and get(item)
  if name and name ~= "" then return name, true end
  if not asked[item] and C_Item and C_Item.RequestLoadItemDataByID then
    asked[item] = true
    pcall(C_Item.RequestLoadItemDataByID, item)
  end
  return english or ("item " .. item), false
end
ns.ItemName = ItemName

local function RecipeName(step)
  if step.spell then
    local name = C_Spell and C_Spell.GetSpellName and C_Spell.GetSpellName(step.spell) or GetSpellInfo and GetSpellInfo(step.spell)
    if name and name ~= "" then return name end
  end
  return step.recipe
end
ns.RecipeName = RecipeName

-- what of the character's own a stretch's recipe uses, in words: "Using your 40 Briarthorn and
-- 12 Mageroyal" (lower: "using your ..."); a third and more are "+N more". `name` gives an
-- item's name (the house's English one until the client has it)
function ns.UsingText(step, name, lower)
  local parts = {}
  for i, m in ipairs(step.mine or {}) do
    if i > 2 then parts[#parts] = parts[#parts] .. string.format(" (+%d more)", #step.mine - 2); break end
    table.insert(parts, m[2] .. " " .. name(m[1]))
  end
  return (lower and "using your " or "Using your ") .. table.concat(parts, " and ")
end

-- the window drawn again in a moment, once, however many changes come before then
local due = false
local function RedrawSoon()
  if due or not win or not win:IsShown() then return end
  due = true
  C_Timer.After(REFRESH_DELAY, function() due = false; Refresh() end)
end

local loads = CreateFrame("Frame")          -- an item's data came: draw again if it was asked for
for _, event in ipairs({ "ITEM_DATA_LOAD_RESULT", "GET_ITEM_INFO_RECEIVED" }) do pcall(loads.RegisterEvent, loads, event) end
loads:SetScript("OnEvent", function(_, _, item) if asked[item] then RedrawSoon() end end)

-- ================================================================ the gold ceiling
-- What the character can afford: the gold in the bags, or an amount typed in. The summary says
-- how far it reaches; with the box ticked the route is cut there.
local purse = CreateFrame("Frame")          -- the gold changed: draw again while it is what counts
pcall(purse.RegisterEvent, purse, "PLAYER_MONEY")
purse:SetScript("OnEvent", function() if not Char().budget.copper then RedrawSoon() end end)

local function Budget()
  local b = Char().budget or {}
  return b.copper or (GetMoney and GetMoney()) or 0, b.copper == nil
end

-- the highest skill, up to `upto`, the route from `from` with `have` in hand can be bought up to
-- for `budget` (what it spends grows with the skill; a search by halves). `from` when not even
-- the first point.
local function Reach(plan, from, have, upto, budget)
  if ns.Tailor(plan, from, have, upto).spent <= budget then return upto end
  local lo, hi = from, upto                 -- lo is within the budget, hi is not
  while hi - lo > 1 do
    local mid = math.floor((lo + hi) / 2)
    if ns.Tailor(plan, from, have, mid).spent <= budget then lo = mid else hi = mid end
  end
  return lo
end

-- The skill the gold reaches from `from` with `have` in hand, when the window's "only as far as
-- the gold goes" box is ticked; nil when it is not. The Make button and the shopping list cut
-- the step there too, so that the list asks for what the gold buys and no more (the user,
-- 7 Nov 2026: 56 venom sacs for 50s asked of a 20s cap).
function ns.BudgetReach(plan, from, have)
  local b = Char().budget
  if not RANGE or not (b and b.on) then return nil end
  return Reach(plan, from, have, plan.target, (Budget()))
end

-- ================================================================ the window
local function ShowItemTip(row)
  if not row.item then return end
  GameTooltip:SetOwner(row, "ANCHOR_RIGHT")
  if GameTooltip.SetItemByID then GameTooltip:SetItemByID(row.item) else GameTooltip:AddLine(row.name:GetText() or "") end
  local spots = last and ns.Catches(last.plan, row.item) and ns.CatchSpots(last.plan, row.item)       -- the fishing route: where the fish is caught
  if spots then
    GameTooltip:AddLine("Catch: " .. spots, 0.6, 0.9, 0.6, true)
    GameTooltip:AddLine(ns.CATCH_NOTE, 0.7, 0.7, 0.7, true)
  end
  -- the characters that can hand things to this one: the same auction house and faction
  local me, alts = Char(), ns.Settings().alts ~= false
  for _, c in pairs(FWCS_DB.__chars or {}) do
    local n = c.items and c.items[row.item]
    if n and c.house == me.house and c.faction == me.faction then
      local where = {}
      for i, place in ipairs(PLACES) do
        if (n[i] or 0) > 0 then table.insert(where, n[i] .. " in " .. place) end
      end
      GameTooltip:AddDoubleLine(c.name .. (c == me and "" or (alts and " (counted)" or " (not counted: 'other characters' is off)")),
        table.concat(where, ", "), 0.6, 0.8, 1, 1, 1, 1)
    end
  end
  GameTooltip:Show()
end


local function Build()
  win = CreateFrame("Frame", "ForeverWowCraftWindow", UIParent, "BackdropTemplate")
  win:SetSize(WIDTH, HEIGHT)
  win:SetFrameStrata("HIGH")
  win:SetClampedToScreen(true)
  win:SetMovable(true)
  win:EnableMouse(true)
  win:RegisterForDrag("LeftButton")
  win:SetBackdrop({ bgFile = "Interface\\Tooltips\\UI-Tooltip-Background", edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
    edgeSize = 14, insets = { left = 3, right = 3, top = 3, bottom = 3 } })
  win:SetBackdropColor(0.03, 0.03, 0.05, 0.94)
  win:SetScript("OnDragStart", win.StartMoving)
  win:SetScript("OnDragStop", function(self)
    self:StopMovingOrSizing()
    local point, _, relPoint, x, y = self:GetPoint()
    ns.Settings().winPos = { point, relPoint, x, y }
  end)
  local pos = ns.Settings().winPos
  if pos then win:SetPoint(pos[1], UIParent, pos[2], pos[3], pos[4]) else win:SetPoint("CENTER") end
  table.insert(UISpecialFrames, "ForeverWowCraftWindow")      -- Escape closes it

  win.title = win:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
  win.title:SetPoint("TOPLEFT", 14, -12)
  win.title:SetText("|cff" .. ns.BRAND.gold .. "ForeverWowCraft|r")
  local close = CreateFrame("Button", nil, win, "UIPanelCloseButton")
  close:SetPoint("TOPRIGHT", -2, -2)
  win.feedback = Button(win, 84, "Feedback")               -- the project's Discord (ShowFeedback)
  win.feedback:SetPoint("RIGHT", close, "LEFT", 2, 0)
  win.feedback:SetScript("OnClick", function() ns.ShowFeedback() end)
  -- the arrow on or off: a box by the Feedback button, the same switch as /fwcs arrow on|off
  -- (the user, 6 Nov 2026: an easy way to it, in this window)
  win.arrowBox = CreateFrame("CheckButton", "ForeverWowCraftArrowBox", win, "UICheckButtonTemplate")
  win.arrowBox:SetSize(22, 22)
  win.arrowBox:SetPoint("RIGHT", win.feedback, "LEFT", -4, 0)
  win.arrowBox.label = win:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  win.arrowBox.label:SetPoint("RIGHT", win.arrowBox, "LEFT", -2, 0)
  win.arrowBox.label:SetText("Arrow")
  win.arrowBox:SetChecked(ns.Settings().arrow ~= false)
  win.arrowBox:SetScript("OnClick", function(s) ns.ArrowCommand(s:GetChecked() and "on" or "off") end)
  win.gethelper = Button(win, 110, "Get the helper")        -- shown while no helper has written to the addon (ShowHelper)
  win.gethelper:SetPoint("RIGHT", win.arrowBox.label, "LEFT", -6, 0)
  win.gethelper:SetScript("OnClick", function() ns.ShowHelper() end)
  win.gethelper:Hide()
  -- the empty window's way on: a reload (a secure button running /reload: the game lets no addon call
  -- ReloadUI). Shown while the helper runs and this character's house has no routes here yet. While the Plans
  -- addon is there but off (state A) it reads "Switch on and reload" and its PreClick enables the addon first, so one
  -- click does both; the secure OnClick is left alone. PreClick reads the state Refresh set, never EmptyState().
  win.reload = CreateFrame("Button", "ForeverWowCraftWindowReload", win, "SecureActionButtonTemplate, UIPanelButtonTemplate")
  win.reload:SetSize(120, 24)
  win.reload:SetText("Reload now")
  win.reload:SetPoint("BOTTOM", win, "BOTTOM", 0, 18)
  win.reload:SetAttribute("type", "macro")
  win.reload:SetAttribute("macrotext", "/reload")
  win.reload:RegisterForClicks("AnyDown", "AnyUp")
  win.reload:SetScript("PreClick", function()
    if reloadSwitchesOn then ns.EnablePlans() end
  end)
  win.reload:Hide()

  -- the first row: a button per profession the routes cover, made as they are known (DrawProfessions)
  win.profs = {}
  -- the second: the profession counted beside it, what the route is for, other characters,
  -- Auctionator (until 2 Nov 2026 a button between the first two chose whether the route may
  -- buy recipes; every route may now)
  win.also = Button(win, 150, "", "ForeverWowCraftAlso")
  win.also:SetPoint("TOPLEFT", 12, -66)
  win.focus = Button(win, 150, "", "ForeverWowCraftFocus")      -- "Mode: Fishing only" fits; the row is 12 + 150 + 6 + 150 + 6 + 154 + 6 + 100 = 584 of WIDTH
  win.focus:SetPoint("LEFT", win.also, "RIGHT", 6, 0)
  win.alts = Button(win, 154, "")
  win.alts:SetPoint("LEFT", win.focus, "RIGHT", 6, 0)
  win.auctionator = Button(win, 100, "Auctionator")
  win.auctionator:SetPoint("LEFT", win.alts, "RIGHT", 6, 0)

  if RANGE then
    win.range = RangeSlider(win, 420)
    win.range:SetPoint("TOPLEFT", 104, -94)
    win.skillLabel = win:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    win.skillLabel:SetPoint("RIGHT", win.range, "LEFT", -54, 0)
    win.skillLabel:SetText("Skill")
    -- the two numbers, typed as well as dragged: Enter takes the number, Escape leaves it
    local function NumberBox(which, point, rel, x)
      local e = CreateFrame("EditBox", nil, win, "InputBoxTemplate")
      e:SetSize(40, 20)
      e:SetPoint(point, win.range, rel, x, 0)
      e:SetAutoFocus(false)
      e:SetNumeric(true)
      e:SetMaxLetters(3)
      e:SetJustifyH("CENTER")
      e:SetScript("OnEnterPressed", function(self)
        local v = tonumber(self:GetText())
        if v then win.range:Moved(which, v) end
        self:SetText(win.range[which])
        self:ClearFocus()
      end)
      e:SetScript("OnEscapePressed", function(self) self:SetText(win.range[which]); self:ClearFocus() end)
      e:SetScript("OnEditFocusLost", function(self) self:SetText(win.range[which]) end)
      return e
    end
    win.range.fromText = NumberBox("from", "RIGHT", "LEFT", -6)
    win.range.uptoText = NumberBox("upto", "LEFT", "RIGHT", 10)
    win.reset = Button(win, 60, "Reset", "ForeverWowCraftReset")
    win.reset:SetPoint("LEFT", win.range.uptoText, "RIGHT", 6, 0)

    -- the gold ceiling: the amount, typed or from the bags; and whether the route is cut at it
    win.goldLabel = win:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    win.goldLabel:SetPoint("TOPLEFT", 14, -126)
    win.goldLabel:SetText("Gold")
    win.gold = CreateFrame("EditBox", "ForeverWowCraftGold", win, "InputBoxTemplate")
    win.gold:SetSize(110, 20)
    win.gold:SetPoint("LEFT", win.goldLabel, "RIGHT", 52, 0)
    win.gold:SetAutoFocus(false)
    win.gold:SetMaxLetters(24)
    win.gold:SetScript("OnEnterPressed", function(self)
      local text = self:GetText() or ""
      Char().budget.copper = ParseMoney(text)   -- nil for empty or nonsense: the bags again
      self:ClearFocus()
      Refresh()
    end)
    win.gold:SetScript("OnEscapePressed", function(self) self:SetText(PlainMoney((Budget()))); self:ClearFocus() end)
    win.gold:SetScript("OnEditFocusLost", function(self) self:SetText(PlainMoney((Budget()))) end)
    win.cap = CreateFrame("CheckButton", "ForeverWowCraftCap", win, "UICheckButtonTemplate")
    win.cap:SetSize(24, 24)
    win.cap:SetPoint("LEFT", win.gold, "RIGHT", 8, 0)
    win.cap:SetScript("OnClick", function()
      local b = Char().budget
      b.on = not b.on or nil
      Refresh()
    end)
    win.capLabel = win:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    win.capLabel:SetPoint("LEFT", win.cap, "RIGHT", 2, 0)
    win.capLabel:SetText("only as far as this gold goes")
  end

  win.summary = win:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
  win.summary:SetPoint("TOPLEFT", 14, -(RANGE and 152 or 96))
  win.summary:SetWidth(WIDTH - 28)
  win.summary:SetJustifyH("LEFT")
  win.summary:SetSpacing(3)

  -- what needs doing before the numbers are right: a profession to pick, the bank to open
  win.notice = win:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  win.notice:SetPoint("TOPLEFT", 14, -NOTICE_TOP)
  win.notice:SetWidth(WIDTH - 28)
  win.notice:SetJustifyH("LEFT")
  win.notice:SetSpacing(2)
  win.notice:SetWordWrap(true)

  -- the small print, wrapped, under the list rather than in it (the rows cut long text off)
  win.foot = win:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  win.foot:SetPoint("BOTTOMLEFT", 14, 10)
  win.foot:SetWidth(WIDTH - 28)
  win.foot:SetJustifyH("LEFT")
  win.foot:SetWordWrap(true)
  win.foot:SetText("Bags are counted as they are. The bank is counted as it was when last open. The mail is counted as it was "
    .. "when a mailbox was last open. Your auctions still up are counted as they were when the auction house was last open. "
    .. "Hover over an item to see which of your characters has it.")

  win.scroll = CreateFrame("ScrollFrame", nil, win)
  win.scroll:SetPoint("TOPLEFT", 12, -NOTICE_TOP)
  win.scroll:SetPoint("BOTTOMRIGHT", -12, 12)
  win.body = CreateFrame("Frame", nil, win.scroll)
  win.body:SetSize(WIDTH - 24, 10)
  win.scroll:SetScrollChild(win.body)
  win.scroll:EnableMouseWheel(true)
  win.scroll:SetScript("OnMouseWheel", function(self, delta)
    local most = math.max(0, win.body:GetHeight() - self:GetHeight())
    self:SetVerticalScroll(math.min(most, math.max(0, self:GetVerticalScroll() - delta * ROW * 3)))
  end)
  win.rows = {}
  win:SetScript("OnShow", function() Refresh() end)
  win:Hide()
end

-- A quiet line about the helper when it is not there or not running (the helper stamps
-- Plans.lua when it writes it): what is recorded stays on the PC until it is. Nil when fine.
local HELPER_STALE = 2 * 86400
local function HelperNote()
  if not FWCS_PLANS_WRITTEN then
    return "|cff808080The helper is not installed on this PC: foreverwowcraft.com/helper. It sends the prices the addon records, and fetches the routes.|r"
  elseif time() - FWCS_PLANS_WRITTEN > HELPER_STALE then
    return string.format("|cff808080The helper last ran %s: start it (the icon by the clock), and what the addon recorded is sent.|r", Age(FWCS_PLANS_WRITTEN))
  end
end

-- ================================================================ why the window is empty
-- When no house is found for the character, the one cause the addon can tell, and its one next step. Worked
-- out only when the window is drawn empty: nothing on a timer, nothing recorded or sent. From the files the helper
-- writes (Plans.lua: FWCS_PLANS_WRITTEN, FWCS_SITE, FWCS_PLANS_PROBLEM) and the game's AddOns list.
local PLANS_ADDON = "ForeverWowCraftPlans"
local COVERED = { regions = { US = true, AU = true, EU = true, TW = true, KR = true },
                  rules = { ["PvE"] = true, ["PvP"] = true, ["RP"] = true, ["RP PvP"] = true } }      -- the core's config.HOUSE_PATTERNS

-- A function of the game's AddOns list: C_AddOns' where the client has it, else the old global, under pcall.
-- Returns pcall's results, or false when the client has no such function.
local function AddOnCall(name, ...)
  local api = (type(C_AddOns) == "table" and C_AddOns[name]) or _G[name]
  if type(api) ~= "function" then return false end
  return pcall(api, ...)
end

-- The Plans addon in the AddOns list: "loaded", "off" (there, not loaded: unticked, or ticked and not yet
-- reloaded), "missing" (no folder), "other" (there, and not loadable for a reason a tick does not mend), or nil when the
-- client cannot say; and the reason the game gave (GetAddOnInfo's fifth value: "DISABLED", "MISSING", ...).
local function PlansAddOnState()
  local ok, first, _, _, _, fifth = AddOnCall("GetAddOnInfo", PLANS_ADDON)
  if not ok then return nil end
  local name, reason = first, fifth
  if type(first) == "table" then name, reason = first.name, first.reason end       -- newer clients answer with a table
  if name == nil or reason == "MISSING" then return "missing", reason end
  local lok, loaded = AddOnCall("IsAddOnLoaded", PLANS_ADDON)
  if not lok then return nil end
  if loaded then return "loaded", reason end
  if reason == nil or reason == "" or reason == "DISABLED" then return "off", reason or "" end
  return "other", reason
end

local function CanSwitchOn()
  return (type(C_AddOns) == "table" and type(C_AddOns.EnableAddOn) == "function") or type(EnableAddOn) == "function"
end

-- Enables the Plans addon (the secure reload button's PreClick, in state A only).
function ns.EnablePlans()
  AddOnCall("EnableAddOn", PLANS_ADDON)
end

local RELOAD = "|cffffd100Reload now|r"
local SWITCH = "|cffffd100Switch on and reload|r"
local PROBLEMS = { reach = true, update = true, unusable = true }

-- { letter, summary, text = {...}, reload = whether the Reload button is the next step, switch = whether that button also
-- switches the Plans addon on (state A with a client that can), debug = what the letter means and its inputs }
local function EmptyState()
  local summary = "No routes for this character's auction house yet."
  if not FWCS_PLANS_WRITTEN then
    local state, reason = PlansAddOnState()
    if state == "off" then
      return { letter = "A", summary = "The ForeverWowCraft Plans addon is switched off.", reload = true, switch = CanSwitchOn(),
               text = CanSwitchOn() and {
                 "The routes are kept in a second addon, ForeverWowCraft Plans, and it is not loaded.",
                 "Click " .. SWITCH .. " below.", "",
                 "Or tick it in the AddOns list (Esc > AddOns) and type /reload." } or {
                 "The routes are kept in a second addon, ForeverWowCraft Plans, and it is not loaded.",
                 "Tick it in the AddOns list (Esc > AddOns, or the AddOns button at character select),",
                 "then click " .. RELOAD .. " below, or type /reload." },
               debug = "plans addon off (reason " .. (reason ~= "" and reason or "none") .. ")" }
    end
    return { letter = "B", summary = summary, text = {
               "The helper on this PC fetches the routes from foreverwowcraft.com and sends the prices the",
               "addon records. Until it is installed, what is recorded stays on this PC." },
             debug = "no helper has written Plans.lua (plans addon: " .. tostring(state) .. ")" }
  end
  local problem = FWCS_PLANS_PROBLEM
  if type(problem) == "table" and PROBLEMS[problem.kind] then
    local when = Age(problem.at)
    local texts = {
      reach = { string.format("The helper on this PC could not reach foreverwowcraft.com (%s).", when),
                "It tries again by itself about every ten minutes.",
                "Then click " .. RELOAD .. " below, or type /reload." },
      update = { "The site's routes need a newer helper than the one on this PC.",
                 "Update it from the helper's icon by the clock, or at foreverwowcraft.com/helper." },
      unusable = { string.format("The helper fetched routes it could not use (%s).", when),
                   "It tries again by itself about every ten minutes. Nothing for you to do." } }
    return { letter = "C", summary = "The helper could not fetch the routes.", reload = problem.kind == "reach", text = texts[problem.kind],
             debug = "helper could not fetch (" .. problem.kind .. ", " .. when .. ")" }
  end
  local realm, faction = GetRealmName() or "?", (UnitFactionGroup and UnitFactionGroup("player")) or ""
  local ruled = ns.inv.Ruled(realm)
  local site = type(FWCS_SITE) == "table" and type(FWCS_SITE.houses) == "table" and FWCS_SITE or nil
  local again = { "Click " .. RELOAD .. " below, or type /reload. The helper sees a new character at its",
                  "first reload and fetches the routes of its auction house within a minute;",
                  "a second reload shows them here.", "" }
  if site and ruled then
    local listed = false
    for _, h in ipairs(site.houses) do
      if type(h) == "table" and h[1] == ruled and h[2] == faction then listed = true end
    end
    if listed then
      table.insert(again, "Still empty after that? Check that the helper is running: its icon is by the clock.")
      return { letter = "D", summary = summary, reload = true, text = again,
               debug = "the site lists this house, Plans.lua does not have it (" .. #site.houses .. " houses listed)" }
    end
    local region, rules = realm:match("^CAMWOW (%a+)%d+ Realm %d+ (.+)$")
    local remedy = { "The site plans them once its prices are recorded: open the auction house",
                     "and click Save Prices." }
    if not COVERED.regions[region or ""] then remedy = { "ForeverWowCraft does not cover this region yet." }
    elseif not COVERED.rules[rules or ""] then remedy = { "ForeverWowCraft does not cover this kind of realm yet." } end
    local out = { string.format("No routes on foreverwowcraft.com for %s (%s).", realm, faction ~= "" and faction or "?") }
    for _, line in ipairs(remedy) do table.insert(out, line) end
    return { letter = "E", summary = "The site has no routes for this auction house right now.", text = out,
             debug = "the site has no routes for this house (" .. #site.houses .. " listed, region " .. tostring(region) .. ")" }
  end
  table.insert(again, site and "Still empty after that? ForeverWowCraft does not cover this realm yet."
                            or "Still empty? Check that the helper is running and up to date: its icon is by the clock.")
  return { letter = "F", summary = summary, reload = true, text = again,
           debug = site and "cannot tell: the realm's name names no auction house" or "cannot tell: Plans.lua has no list of the site's houses" }
end

local debugged
-- the slider set to the plan's range and the part of it shown
SetSliders = function(plan, from, upto)
  win.range:Set(plan.start, plan.target, from, upto)
end

-- the slider, its numbers and Reset: there only while a route is shown
ShowRange = function(on)
  if not RANGE then return end
  for _, f in ipairs({ win.range, win.range.fromText, win.range.uptoText, win.reset, win.skillLabel,
                       win.goldLabel, win.gold, win.cap, win.capLabel }) do
    if on then f:Show() else f:Hide() end
  end
end

-- The notices under the summary, and the list starting under them: a notice's height is only
-- known once it is drawn.
local function SetNotice(text)
  win.notice:SetText(text)
  local h = text ~= "" and (win.notice:GetStringHeight() or 0) or 0
  win.scroll:SetPoint("TOPLEFT", 12, -(NOTICE_TOP + (h > 0 and h + 8 or 0)))
  win.scroll:SetPoint("BOTTOMRIGHT", -12, 14 + math.max(win.foot:GetStringHeight() or 0, 24))
end

-- An addon cannot write the clipboard: the Auctionator import string is put in a box, selected,
-- for Ctrl+C. Two of them to choose from: what is left after what the character has (the
-- default), or everything, as if from nothing.
local copyBox
local function ShowCopyBox(whole)
  local box = copyBox
  if not box then
    box = CreateFrame("Frame", nil, win, "BackdropTemplate")
    copyBox = box
    box:SetSize(WIDTH - 60, 146)
    box:SetPoint("CENTER", win, "CENTER", 0, 40)
    box:SetFrameStrata("DIALOG")
    box:EnableMouse(true)
    box:SetBackdrop({ bgFile = "Interface\\Tooltips\\UI-Tooltip-Background", edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
      edgeSize = 14, insets = { left = 3, right = 3, top = 3, bottom = 3 } })
    box:SetBackdropColor(0.05, 0.05, 0.08, 0.98)
    box.title = box:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    box.title:SetPoint("TOPLEFT", 12, -10)
    box.title:SetText("Auctionator shopping list")
    box.left = Button(box, 190, "")
    box.left:SetPoint("TOPLEFT", 12, -30)
    box.left:SetScript("OnClick", function() ShowCopyBox(false) end)
    box.whole = Button(box, 190, "")
    box.whole:SetPoint("LEFT", box.left, "RIGHT", 6, 0)
    box.whole:SetScript("OnClick", function() ShowCopyBox(true) end)
    box.stats = box:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    box.stats:SetPoint("TOPLEFT", 12, -58)
    box.stats:SetWidth(WIDTH - 84)
    box.stats:SetJustifyH("LEFT")
    box.help = box:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    box.help:SetPoint("TOPLEFT", 12, -78)
    box.help:SetWidth(WIDTH - 84)
    box.help:SetJustifyH("LEFT")
    box.help:SetWordWrap(true)
    box.edit = CreateFrame("EditBox", nil, box, "InputBoxTemplate")
    box.edit:SetSize(WIDTH - 96, 24)
    box.edit:SetPoint("BOTTOMLEFT", 18, 12)
    box.edit:SetAutoFocus(false)
    box.edit:SetScript("OnEscapePressed", function() box:Hide() end)
    box.edit:SetScript("OnTextChanged", function(self)        -- the text is to copy, not to edit
      if self:GetText() ~= box.text then self:SetText(box.text or ""); self:HighlightText() end
    end)
    box.edit:SetScript("OnEditFocusGained", function(self) self:HighlightText() end)
    local close = CreateFrame("Button", nil, box, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT", -2, -2)
    win:HookScript("OnHide", function() box:Hide() end)
  end
  local function mark(on) return on and "|cff40ff40[x]|r " or "[  ] " end
  box.left:SetText(mark(not whole) .. "Less what you have")
  box.whole:SetText(mark(whole) .. "Everything, from nothing")
  local text, sum = ns.AuctionatorImport(whole)
  box.text = text
  box.stats:SetText(string.format("|cff33ccff%d|r distinct item%s, |cff33ccff%s|r units%s, about %s at the route's prices%s",
    sum.items, sum.items == 1 and "" or "s", FormatLargeNumber(sum.units),
    sum.recipes > 0 and string.format(" (%d recipe%s)", sum.recipes, sum.recipes == 1 and "" or "s") or "",
    Money(sum.cost), sum.unpriced > 0 and string.format(" (%d without a price)", sum.unpriced) or ""))
  box.help:SetText((whole and "Every auction house purchase of the route from here, whatever you have. "
      or "What is still to buy on the auction house after your bags and bank. ")
    .. (text == "" and "Nothing: there is nothing to buy." or "Ctrl+C copies it (it is selected). Then Auction House, Shopping tab, Import, paste, Import.")
    .. (sum.english > 0 and string.format("\n|cffff8000%d name%s still in English:|r the game has not handed over its own yet. "
      .. "Close this and open it again in a moment; Auctionator finds an item by the name your game shows.", sum.english, sum.english == 1 and " is" or "s are") or ""))
  box.edit:SetText(box.text)
  box:Show()
  box.edit:SetFocus()
  box.edit:HighlightText()
end

-- A link shown selected, for Ctrl+C (the game opens no browser): the project's Discord for
-- feedback and help (ns.DISCORD), and the helper's page for an install without one (ns.HELPER_URL).
local linkBox
function ns.ShowLink(title, help, link)
  if not win then return end
  local box = linkBox
  if not box then
    box = CreateFrame("Frame", nil, win, "BackdropTemplate")
    linkBox = box
    box:SetSize(440, 110)
    box:SetPoint("CENTER", win, "CENTER", 0, 60)
    box:SetFrameStrata("DIALOG")
    box:EnableMouse(true)
    box:SetBackdrop({ bgFile = "Interface\\Tooltips\\UI-Tooltip-Background", edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
      edgeSize = 14, insets = { left = 3, right = 3, top = 3, bottom = 3 } })
    box:SetBackdropColor(0.05, 0.05, 0.08, 0.98)
    box.title = box:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    box.title:SetPoint("TOPLEFT", 12, -10)
    box.help = box:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    box.help:SetPoint("TOPLEFT", 12, -32)
    box.help:SetWidth(440 - 24)
    box.help:SetJustifyH("LEFT")
    box.help:SetWordWrap(true)
    box.edit = CreateFrame("EditBox", nil, box, "InputBoxTemplate")
    box.edit:SetSize(440 - 36, 24)
    box.edit:SetPoint("BOTTOMLEFT", 18, 12)
    box.edit:SetAutoFocus(false)
    box.edit:SetScript("OnEscapePressed", function() box:Hide() end)
    box.edit:SetScript("OnTextChanged", function(self)        -- the link is to copy, not to edit
      if self:GetText() ~= box.link then self:SetText(box.link); self:HighlightText() end
    end)
    box.edit:SetScript("OnEditFocusGained", function(self) self:HighlightText() end)
    local close = CreateFrame("Button", nil, box, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT", -2, -2)
    win:HookScript("OnHide", function() box:Hide() end)
  end
  box.link = link
  box.title:SetText(title)
  box.help:SetText(help)
  box.edit:SetText(link)
  box:Show()
  box.edit:SetFocus()
  box.edit:HighlightText()
end

function ns.ShowFeedback()
  ns.ShowLink("Feedback and help", "Something wrong, or an idea? Say so on the project's Discord. "
    .. "Ctrl+C copies the link (it is selected); paste it into your browser.", ns.DISCORD)
end

function ns.ShowHelper()
  ns.ShowLink("The helper", "The helper runs beside the game, an icon by the clock: it sends the prices the addon records and fetches "
    .. "the routes /fwc shows. For Windows; it installs the addon too. Ctrl+C copies the address (it is selected); "
    .. "paste it into your browser.", ns.HELPER_URL)
end

local function Row(i)
  local row = win.rows[i]
  if row then return row end
  row = CreateFrame("Frame", nil, win.body)
  row:SetSize(WIDTH - 24, ROW)
  row:SetPoint("TOPLEFT", 0, -(i - 1) * ROW)
  row.cells = {}
  local right = -4
  for n, width in ipairs(COLS) do
    local fs = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    fs:SetSize(width, ROW)
    fs:SetJustifyH("RIGHT")
    fs:SetPoint("RIGHT", row, "RIGHT", right, 0)
    right = right - width - 4
    row.cells[n] = fs
  end
  row.name = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  row.name:SetPoint("LEFT", 4, 0)
  row.name:SetPoint("RIGHT", row, "RIGHT", right, 0)
  row.name:SetJustifyH("LEFT")
  row.name:SetWordWrap(false)
  row:EnableMouse(true)
  row:SetScript("OnEnter", ShowItemTip)
  row:SetScript("OnLeave", GameTooltip_Hide)
  win.rows[i] = row
  return row
end

-- ================================================================ what it shows
local lines     -- the rows being put together: { text, need, have, buy, cost, item = itemID }
-- (last: what the window shows, { house, plan, mine = the route less what is had, from }; declared at the top)

local function Line(text, need, have, buy, cost, item)
  table.insert(lines, { text, need or "", have or "", buy or "", cost or "", item = item })
end

local function Head(text, need, have, buy, cost)
  if #lines > 0 then Line("") end
  local function h(s) return s and ("|cff33ccff" .. s .. "|r") or "" end
  Line(h(text), h(need), h(have), h(buy), h(cost))
end

local function Sorted(t, weight)
  local keys = {}
  for k in pairs(t) do table.insert(keys, k) end
  table.sort(keys, function(a, b)
    local wa, wb = weight(a), weight(b)
    if wa ~= wb then return wa > wb end
    return a < b
  end)
  return keys
end

-- the plans of a house as { profession = { variant = plan } }, and the professions in order:
-- the character's own first
local function Professions(house)
  local by, names = {}, {}
  for _, plan in pairs(house.plans or {}) do
    if not by[plan.profession] then by[plan.profession] = {}; table.insert(names, plan.profession) end
    by[plan.profession][plan.variant] = plan
  end
  local fish = house.fish                      -- the fishing route (Inventory.lua): one more route of its profession, picked apart from the variants
  if fish and by[fish.profession] then by[fish.profession].fishing = fish end
  local skills = Char().skills
  local function rank(name) local _, p = next(by[name]); return skills[p.skill_line] end
  table.sort(names, function(a, b)
    if (rank(a) ~= nil) ~= (rank(b) ~= nil) then return rank(a) ~= nil end
    return a < b
  end)
  return by, names
end

local function Rank(by, name)
  local _, p = next(by[name] or {})
  return p and Char().skills[p.skill_line]
end

-- The secondary professions, by skill line: every character can have them, so they are not
-- a second profession to count (not yet, at least). Cooking, First Aid, Fishing.
local SECONDARY = { [185] = true, [129] = true, [356] = true }
local function IsSecondary(by, name)
  local _, p = next(by[name] or {})
  return p and SECONDARY[p.skill_line] or false
end

-- The second profession counted for a route ("also have" on the site): the one the player
-- picked for this profession, or, left to itself, the other primary one the character has.
-- Returns the name and whether it was picked by the player (false for "none").
local function Companion(profession, by)
  local pick = Char().also[profession]        -- a name; false for none; nil for by itself
  if pick ~= nil then return pick or nil, true end
  local names = {}
  for name in pairs(by) do
    if name ~= profession and Rank(by, name) and not IsSecondary(by, name) then table.insert(names, name) end
  end
  table.sort(names)
  return names[1], false
end

-- the route that counts a companion, where the site found it changes something
local function WithCompanion(house, plan, also)
  return plan and also and house.also and house.also[plan.profession .. "-" .. plan.variant .. "+" .. also] or nil
end

-- A variant of the document, { key, label, recipes, focus }: the recipes a route may use times
-- what it is for (profit: what is made is sold; skill: nothing is). A document from before has
-- two parts: its recipes are the key and its focus is profit.
local function Variant(house, key)
  for _, v in ipairs(house.variants or {}) do
    if v[1] == key then return { key = v[1], label = v[2], recipes = v[3] or v[1], focus = v[4] or "profit" } end
  end
end

-- the key of the variant with these recipes and this focus, or nil
local function VariantFor(house, recipes, focus)
  for _, v in ipairs(house.variants or {}) do
    if (v[3] or v[1]) == recipes and (v[4] or "profit") == focus then return v[1] end
  end
end

-- the label of a focus, from the document's list
local function FocusLabel(house, focus)
  for _, f in ipairs(house.focus or {}) do if f[1] == focus then return f[2] end end
  return focus
end

-- the route of a profession: the variant picked, or the first it has; with its companion where
-- that changes it. Returns the plan, the companion, and whether the plan counts it
local function Effective(plan) return ns.Effective and ns.Effective(plan) or plan end     -- the route at the character's level (Tailor.lua)

local function RouteOf(house, by, profession)
  local s = ns.Settings()
  local variants = by[profession or ""] or {}
  -- "Fishing only" (Char().fishing, per character) is the route of the profession that has it,
  -- and no other's: the choice stays while another profession is looked at
  local plan = variants.fishing and Char().fishing and variants.fishing or variants[s.variant or ""]
  if not plan then
    for _, v in ipairs(house.variants or {}) do
      if variants[v[1]] then plan = variants[v[1]]; break end
    end
  end
  local also = profession and Companion(profession, by)
  local with = WithCompanion(house, plan, also)
  local route = Effective(with or plan)
  -- the recipe of each stretch that costs this character least, what it has counted (Tailor.lua):
  -- from the skill the window plans from, as Fill below has it
  if route and ns.UseWhatIHave then
    local c = Char()
    route = ns.UseWhatIHave(route, c.from[route.profession] or c.skills[route.skill_line] or route.start)
  end
  return route, also, with ~= nil
end

-- the plan to show: { plan, by, names, also = companion or nil, applied = whether the plan counts it }
local function Chosen(house)
  local by, names = Professions(house)
  local s, c = ns.Settings(), Char()
  -- the player's pick from the list; else the one last shown, while the character has it;
  -- else the first the character has trained (they come first). A character without any,
  -- and no pick, gets none: nothing is shown until one is picked
  local profession
  if c.picked ~= false then                   -- false: "none yet" picked from the list
    profession = by[c.picked or ""] and c.picked
      or (by[c.profession or ""] and Rank(by, c.profession) and c.profession)
      or (Rank(by, names[1] or "") and names[1]) or nil
  end
  local variants = by[profession or ""] or {}
  if not variants[s.variant or ""] then
    s.variant = nil
    for _, v in ipairs(house.variants or {}) do
      if variants[v[1]] then s.variant = v[1]; break end
    end
  end
  local plan, also, applied = RouteOf(house, by, profession)
  return { plan = plan, profession = profession, by = by, names = names, also = also, applied = applied }
end

-- the profession the window shows, or would
function ns.ChosenProfession()
  local house = House()
  return house and Chosen(house).profession or nil
end

-- The profession the arrow and the shopping list serve without a panel: one the character
-- has. The window's pick when the character has it, else the one last shown, else the first
-- trained; nil for a character with none. A pick of a profession the character does not have
-- is the window's to show, not the arrow's to walk or the list's to buy for (engineering
-- unlearned, and the list at the house said to make Light Shot, 12 Oct 2026)
function ns.OwnProfession()
  local house = House()
  if not house then return nil end
  local by, names = Professions(house)
  local c = Char()
  for _, p in ipairs({ c.picked, c.profession }) do
    if type(p) == "string" and by[p] and Rank(by, p) then return p end
  end
  for _, p in ipairs(names) do                -- a primary profession before a secondary one (cooking is everyone's)
    if Rank(by, p) and not IsSecondary(by, p) then return p end
  end
  for _, p in ipairs(names) do
    if Rank(by, p) then return p end
  end
  return nil
end

-- The route of a profession as the window shows it, or would: the variant picked (the first
-- the profession has when it lacks that one) with the companion counted. For the Make button
-- on the game's profession panel, which follows the panel's profession, not the window's.
function ns.RouteFor(profession)
  local house = House()
  if not (house and profession) then return nil end
  return (RouteOf(house, (Professions(house)), profession))
end

-- "Fishing only" (the site's cooking route that needs no auction house: the fish you catch, a
-- vendor's goods and recipes), picked in the window's focus control or in Interface > AddOns
-- (/fwcs fishing). The choice is the character's (Char().fishing), kept while another
-- profession is looked at; only a house with the route (Inventory.lua) can have it.
ns.FISHING_ABOUT = "cooking from the fish you catch, a vendor's goods and a vendor's recipes, nothing from the auction house."
function ns.FishingAvailable()
  local house = House()
  return house ~= nil and house.fish ~= nil
end
function ns.FishingOn() return Char().fishing == true and ns.FishingAvailable() end
function ns.FishingCommand(arg, quiet)
  local on
  if arg == "on" then on = true elseif arg == "off" then on = false else on = not ns.FishingOn() end
  local there = ns.FishingAvailable()
  if on and not there then
    on = false
    if not quiet and ns.Print then ns.Print("there is no fishing route for this character's auction house yet (it needs the helper, and a site that has it)") end
  elseif not quiet and ns.Print then
    ns.Print(on and ("Fishing only: " .. ns.FISHING_ABOUT .. " Choose it for cooking in the /fwc window (the Mode button), or /fwcs fishing off.")
      or "cooking is planned as before (/fwcs fishing on for Fishing only)")
  end
  Char().fishing = on or nil
  Repoint()
end

-- a note cut into lines of at most this many characters, at spaces (the list's rows are one line each)
local NOTE_WIDTH = 105
local wrapped = {}
local function Wrapped(text)
  local out = wrapped[text]
  if out then return out end
  out = {}
  local line = ""
  for word in text:gmatch("%S+") do
    if line ~= "" and #line + #word + 1 > NOTE_WIDTH then table.insert(out, line); line = word
    else line = line == "" and word or (line .. " " .. word) end
  end
  if line ~= "" then table.insert(out, line) end
  wrapped[text] = out
  return out
end

local function Fill(house, chosen)
  local c, plan = Char(), chosen.plan
  c.profession = chosen.profession            -- once shown, it stays the one shown
  local name = house.items or {}
  local function N(item) return (ItemName(item, name[item] or ns.ToolName(item))) end
  local rank = c.skills[plan.skill_line]
  local from = c.from[plan.profession] or rank or plan.start
  from = math.max(plan.start, math.min(from, plan.target))
  local upto = RANGE and c.upto[plan.profession] or plan.target
  upto = math.max(from, math.min(upto, plan.target))
  local have = ns.OwnTools(Have())            -- a tool counted as this character has it, bank and all
  -- the gold: how far it reaches, and the route cut there when asked
  local gold, wanted = "", upto
  if RANGE then
    local budget, bags = Budget()
    local reach = Reach(plan, from, have, upto, budget)
    if c.budget.on and reach < upto then upto = reach end
    win.gold:SetText(PlainMoney(budget))
    win.cap:SetChecked(c.budget.on or false)
    gold = string.format("\nGold %s, %s: %s", bags and "in your bags" or "as typed", Money(budget),
      reach >= wanted and "enough for all of this."
      or c.budget.on and string.format("as far as skill %d, where the list stops. Untick the box to see the rest.", reach)
      or string.format("as far as skill %d of the %d.", reach, wanted))
  end
  if RANGE then SetSliders(plan, from, upto) end
  local all, mine = ns.Tailor(plan, from, {}, upto), ns.Tailor(plan, from, have, upto)

  local variant = Variant(house, plan.variant) or { label = plan.variant, focus = "profit" }
  local also = chosen.also and chosen.applied and (" with " .. Title(chosen.also)) or ""
  win.also:SetText("Also: " .. (chosen.also and Title(chosen.also) or "none"))
  -- the mode (the route's focus) as a button that names the one in use, in the window's gold
  local fishing = plan.kind == "fishing"       -- the route is the fishing one: its costs are fish to catch (a count), not copper
  local mode = fishing and "Fishing only" or variant.focus == "skill" and "Skill-up" or variant.focus == "profit" and "Profit"
    or FocusLabel(house, variant.focus)
  win.focus:SetText("Mode: |cffffd100" .. mode .. "|r")
  if house.focus or fishing then win.focus:Show() else win.focus:Hide() end      -- a document from before: profit alone
  win.alts:SetText((ns.Settings().alts ~= false and "|cff40ff40[x]|r" or "[  ]") .. " other characters")
  win.title:SetText(string.format("|cff" .. ns.BRAND.gold .. "ForeverWowCraft|r  %s (%s), prices scanned %s",
    house.realm or "?", house.faction or "?", Age(house.scanned_at)))
  local whose = c.from[plan.profession] and "from the skill you gave (/fwc from auto undoes it)"
    or rank and "from your skill" or "a profession you do not have: the whole route"
  if fishing then              -- fish are a count: the gold is for the vendor's goods and recipes alone, and nothing is sold
    win.summary:SetText(string.format(
      "%s, Fishing only, %d to %d%s, %s. %d crafts.\nTo catch: %d fish  (%d with nothing in hand; what you have saves %d)\nTo buy from vendors (goods and recipes): %s%s",
      Title(plan.profession), from, upto, upto < plan.target and string.format(" (of %d)", plan.target) or "", whose, mine.crafts,
      mine.fish, all.fish, all.fish - mine.fish, Money(mine.spent), gold))
  else
    win.summary:SetText(string.format(
      "%s%s %d to %d%s, %s. %d crafts.\nTo buy: %s  (%s with nothing in hand; what you have saves %s)\nLeft to sell: %s     Net: %s%s",
      Title(plan.profession), also, from, upto, upto < plan.target and string.format(" (of %d)", plan.target) or "", whose, mine.crafts,
      Money(mine.spent), Money(all.spent), Money(all.spent - mine.spent), Money(mine.sold), Money(mine.sold - mine.spent), gold))
  end
  last = { house = house, plan = plan, mine = mine, all = all, from = from, upto = upto, capped = upto < wanted }

  -- what needs doing before the numbers are right
  local notices = {}
  if fishing then
    table.insert(notices, "|cff33ccffFishing only:|r " .. ns.CATCH_NOTE .. " It plans your cooking, not your Fishing skill, and no arrow leads to a fishing spot.")
  end
  if chosen.also and not chosen.applied and not fishing then
    table.insert(notices, string.format("|cff33ccffAlso %s:|r it changes nothing in this route, so the plain one is shown.", Title(chosen.also)))
  end
  if not rank and not c.from[plan.profession] then
    local any = false
    for _, r in pairs(c.skills) do if r then any = true end end
    table.insert(notices, any
      and string.format("|cffff8000You do not have %s:|r the whole route is shown, from skill %d. The buttons above pick a profession you have.",
        Title(plan.profession), from)
      or string.format("|cffff8000This character has no profession the routes cover.|r The whole of %s is shown, from skill %d, as it "
        .. "would be after the trainer. The buttons above show another profession; /fwc from <skill> plans from a skill you give.",
        Title(plan.profession), from))
  end
  if not c.bankSeen then
    table.insert(notices, "|cffff8000Your bank is not counted yet:|r open it once, and what is in it is taken off the list from then on.")
  else
    table.insert(notices, string.format("|cff33ccffBank:|r counted as it was when last open, %s. Open it again to count it afresh.", Age(c.bankSeen)))
  end
  if not c.mailSeen then
    table.insert(notices, "|cffff8000Your mail is not counted yet:|r open a mailbox once, and the items in it are counted from then on.")
  else
    table.insert(notices, string.format("|cff33ccffMail:|r counted as it was when a mailbox was last open, %s.", Age(c.mailSeen)))
  end
  if not c.ahSeen then
    table.insert(notices, "|cffff8000Your auctions are not counted yet:|r open the auction house once, and what you have up is counted from then on.")
  else
    table.insert(notices, string.format("|cff33ccffAuctions:|r counted as they were when the auction house was last open, %s.", Age(c.ahSeen)))
  end
  for _, c in ipairs(plan.camp or {}) do                   -- [item, skill first needed at, name]: made once, placed at the camp
    if c[2] <= upto then
      table.insert(notices, string.format("|cff33ccffAt your camp:|r the route makes %s once, from skill %d, and places it; the recipes that need it "
        .. "are made beside it. Its reagents are on the list.", N(c[1]), c[2]))
    end
  end
  -- a tool a step needs that the character lacks (an enchanter's rod): got first, its reagents on the list
  for _, t in ipairs(mine.tools or {}) do
    table.insert(notices, string.format("|cff33ccffA tool:|r the route needs %s from skill %d and you do not have one: %s.",
      N(t.item), t.at, t.made and "it is made on the way, and what it takes is on the list" or "it is on the list"))
  end
  if HelperNote() then table.insert(notices, HelperNote()) end
  SetNotice(table.concat(notices, "\n"))

  lines = {}
  if from >= plan.target then Line("You are at the route's end: nothing left to do.")
  elseif from >= upto then Line("Nothing between those two skills: move a slider.") end

  -- what to buy: everything the route would buy from here, and how much of it is still needed
  local price = setmetatable({}, { __index = function(_, item) return ns.BuyRow(plan, item) end })   -- a tool's reagents too
  local function cost(item, units) return price[item] and units * price[item][1] or nil end
  local keys = Sorted(all.buy, function(item) return cost(item, mine.buy[item] or 0) or 0 end)
  for item in pairs(mine.buy) do if not all.buy[item] then table.insert(keys, item) end end
  if #keys > 0 or #mine.learn > 0 then Head("Shopping list", "Need", "Have", "Buy", "Cost") end
  for _, item in ipairs(keys) do
    local buy = mine.buy[item] or 0
    local catch = price[item] and price[item][2] == "catch"           -- a fish to catch: no price, the zones in the row's tooltip
    local text = N(item) .. ((price[item] and price[item][2] == "vendor") and "  |cff808080vendor|r" or catch and "  |cff808080catch|r" or "")
    if buy == 0 then text = "|cff808080" .. N(item) .. "  (you have enough)|r" end
    Line(text, all.buy[item] or 0, have[item] or 0, buy > 0 and buy or "|cff40ff40-|r", buy > 0 and not catch and Money(cost(item, buy)) or "", item)
  end
  for _, learn in ipairs(mine.learn) do
    Line(N(learn.item) .. "  |cff808080recipe|r", 1, learn.owned and 1 or 0, learn.owned and "|cff40ff40-|r" or 1,
      learn.owned and "" or Money(learn.cost), learn.item)
  end
  if mine.unpriced > 0 then Line("|cff808080? = nothing listed when the prices were scanned; not in the totals|r") end

  -- what is taken from the bags and the bank
  keys = Sorted(mine.used, function(item) return mine.used[item] end)
  if #keys > 0 then Head("From what you have", "", "Have", "Used") end
  for _, item in ipairs(keys) do Line(N(item), "", have[item] or 0, mine.used[item], "", item) end

  if #mine.steps > 0 then Head("Route", "", "", "Crafts", "Skill") end
  for _, s in ipairs(mine.steps) do
    local why = s.step.instead and ("  |cff808080instead of " .. s.step.instead .. "|r")
      or s.step.over and ("  |cff808080" .. ns.UsingText(s.step, N, true) .. ", instead of " .. s.step.over .. "|r") or ""
    Line(RecipeName(s.step) .. why, "", "", s.crafts, s.from .. " - " .. s.to, s.step.makes and s.step.makes[1])
  end
  for _, b in ipairs(mine.blocked or {}) do                 -- nothing fits at the character's level (ns.Effective)
    Line(string.format("|cffff6060no recipe at your level for skill %d - %d: %s asks for level %s|r", b.from, b.to, RecipeName(b.step), tostring(b.step.asks or "?")))
  end
  for _, gap in ipairs(plan.gaps or {}) do
    if gap[2] > from and gap[1] < upto then Line(string.format("|cffff6060no recipe with a price for skill %d - %d|r", math.max(from, gap[1]), gap[2])) end
  end

  keys = Sorted(mine.make, function(item) return mine.make[item] end)
  if #keys > 0 then Head("Make on the way", "", "", "Units") end
  for _, item in ipairs(keys) do Line(N(item), "", "", mine.make[item], "", item) end

  local worth = plan.sell or {}
  local melt = {}
  for _, item in ipairs(plan.disenchant or {}) do melt[item] = true end
  keys = fishing and {} or Sorted(mine.sell, function(item) return (worth[item] or 0) * mine.sell[item] end)      -- the fishing route sells nothing
  if #keys > 0 then Head("Left to sell", "", "Units", "Each", "Total") end
  for _, item in ipairs(keys) do
    Line(N(item) .. (melt[item] and "  |cff808080disenchant|r" or ""), "", mine.sell[item],
      worth[item] and Money(worth[item]) or "|cff808080-|r", worth[item] and Money(worth[item] * mine.sell[item]) or "", item)
  end

  -- the fishing route's notes, once, here and not on every step: the era of the catch data and
  -- the fishing skill's note; the rank notes (the Artisan quest) are in the rank-up verdict's tooltip
  if fishing then
    local any = false
    for _, n in ipairs(plan.notes or {}) do
      if n[3] ~= "rank" and (n[1] <= 1 or n[1] >= from) then      -- a rank's note is the rank-up verdict's (its tooltip), not the window's
        if not any then Head("About this route"); any = true end
        for _, part in ipairs(Wrapped(n[2])) do Line("|cffc7c7cf" .. part .. "|r") end
      end
    end
  end
end

-- The Auctionator import string of what is to buy on the auction house (vendor items left
-- out), with quantities, as the site's "Copy import" gives it: what is left after what the
-- character has, or with `whole` everything, as if from nothing. "" when there is nothing.
-- One list a line: name^term^term; a term is "Exact Name" and 13 ';'-separated fields, the
-- last the quantity (Auctionator.Shopping.Lists.BatchImportFromString). Auctionator matches
-- the names against the client's own, so they are the client's, in its language.
-- Also returned: what the list comes to, { items, units, recipes, cost, unpriced, english },
-- the cost at the route's average prices, `unpriced` the items without one, `english` the
-- names a client in another language has not handed over yet (0 on an English client).
function ns.AuctionatorImport(whole)
  local sum = { items = 0, units = 0, recipes = 0, cost = 0, unpriced = 0, english = 0 }
  if not last then return "", sum end
  local plan, out, english = last.plan, whole and last.all or last.mine, last.house.items or {}
  local price, terms, name, foreign = setmetatable({}, { __index = function(_, item) return ns.BuyRow(plan, item) end }), {}, {}, Foreign()
  local function term(item, n)
    local shown, own = ItemName(item, english[item])
    if foreign and not own then sum.english = sum.english + 1 end
    table.insert(terms, string.format('"%s"%s%d', shown, string.rep(";", 13), n))
  end
  local keys = {}
  for item, n in pairs(out.buy) do
    if n > 0 and not (price[item] and (price[item][2] == "vendor" or price[item][2] == "catch")) then table.insert(keys, item); name[item] = (ItemName(item, english[item])) end
  end
  table.sort(keys, function(a, b) return name[a] < name[b] end)
  for _, item in ipairs(keys) do
    local n = out.buy[item]
    term(item, n)
    sum.items, sum.units = sum.items + 1, sum.units + n
    if price[item] then sum.cost = sum.cost + n * price[item][1] else sum.unpriced = sum.unpriced + 1 end
  end
  for _, learn in ipairs(out.learn) do
    if not learn.owned and plan.kind ~= "fishing" then          -- the fishing route's recipes are a vendor's: not for the auction house
      term(learn.item, 1)
      sum.items, sum.units, sum.recipes = sum.items + 1, sum.units + 1, sum.recipes + 1
      if learn.cost then sum.cost = sum.cost + learn.cost else sum.unpriced = sum.unpriced + 1 end
    end
  end
  if #terms == 0 then return "", sum end
  return string.format("FWC %s %d-%d%s", Title(plan.profession), last.from, last.upto, whole and " all" or "")
    .. "^" .. table.concat(terms, "^"), sum
end

Refresh = function()
  if not win or not win:IsShown() then return end
  CountBags()
  NoteSkills()
  win.arrowBox:SetChecked(ns.Settings().arrow ~= false)              -- as /fwcs arrow may have set it meanwhile
  local house = House()
  local chosen = house and Chosen(house)
  ShowRange(chosen and chosen.plan ~= nil)
  DrawProfessions(chosen)
  local why = not chosen and EmptyState() or nil          -- the empty window's cause (only worked out when it is empty)
  if why and why.letter == "A" then                       -- the Plans addon is there and off: "Switch it on" in the place of "Get the helper"
    win.gethelper:Hide()
  else
    if FWCS_PLANS_WRITTEN then win.gethelper:Hide() else win.gethelper:Show() end
  end
  local combat = InCombatLockdown and InCombatLockdown()          -- a secure button is left as it is in a fight
  if win.reload and not combat then
    reloadSwitchesOn = why ~= nil and why.letter == "A" and why.switch == true      -- what the button's PreClick reads
    win.reload:SetText(reloadSwitchesOn and "Switch on and reload" or "Reload now")
    win.reload:SetWidth(reloadSwitchesOn and 170 or 120)
    if why and why.reload then win.reload:Show() else win.reload:Hide() end
  end
  if not chosen then
    lines, last = {}, nil
    win.also:SetText("-"); win.focus:SetText("-"); win.alts:SetText("-")
    win.summary:SetText(why.summary)
    SetNotice(why.letter ~= "A" and HelperNote() or "")
    for _, text in ipairs(why.text) do Line(text) end
    if debugged ~= why.debug and ns.Debug and ns.Debug("empty window: " .. why.debug) then      -- `/fwcs debug`: which of the empty window's causes, once a change
      debugged = why.debug                              -- remembered only when it was said (debug switched on later says it at the next draw)
    end
  elseif not chosen.plan then                 -- no profession trained, none picked: nothing to show yet
    lines, last = {}, nil
    win.also:SetText("-"); win.focus:SetText("-"); win.alts:SetText("-")
    win.title:SetText(string.format("|cff" .. ns.BRAND.gold .. "ForeverWowCraft|r  %s (%s), prices scanned %s",
      house.realm or "?", house.faction or "?", Age(house.scanned_at)))
    win.summary:SetText("This character has no profession yet.")
    SetNotice("")
    Line("Train one, and its route shows here, from your skill, less what you have.")
    Line("To look at a route before you train it, click a profession above.")
  else
    Fill(house, chosen)
  end
  if picker and picker:IsShown() then DrawPicker() end
  for i, line in ipairs(lines) do
    local row = Row(i)
    row.name:SetText(line[1])
    for n = 1, 4 do row.cells[n]:SetText(line[6 - n]) end      -- cells run right to left: cost, buy, have, need
    row.item = line.item
    row:Show()
  end
  for i = #lines + 1, #win.rows do win.rows[i]:Hide() end
  win.body:SetHeight(math.max(10, #lines * ROW))
  local most = math.max(0, win.body:GetHeight() - win.scroll:GetHeight())
  if win.scroll:GetVerticalScroll() > most then win.scroll:SetVerticalScroll(most) end
end

local pending = false
local function RefreshSoon()
  if pending then return end
  pending = true
  C_Timer.After(REFRESH_DELAY, function()
    pending = false
    -- the bags slot by slot only for the window shown (its Refresh counts them too, and so does
    -- the logout): every bag change, loot in a fight included, read them all before (9 Nov 2026)
    if win and win:IsShown() then CountBags() end
    CountBank()
    CountMail()
    Refresh()
  end)
end

local function Cycle(list, current, step)
  for i, v in ipairs(list) do
    if v == current then return list[(i - 1 + step) % #list + 1] end
  end
  return list[1]
end

-- The row of profession buttons, in the site's order: the one shown lit blue, the character's
-- own in the usual text, the rest grey. Made the first time a house's routes are seen.
DrawProfessions = function(chosen)
  local names = {}
  for name in pairs(chosen and chosen.by or {}) do table.insert(names, name) end
  table.sort(names)
  for i, name in ipairs(names) do
    local b = win.profs[name]
    if not b then
      b = Button(win, PROF_WIDTH, "", "ForeverWowCraftProfession" .. Title(name):gsub(" ", ""))
      b:SetPoint("TOPLEFT", 12 + (i - 1) * (PROF_WIDTH + PROF_GAP), -38)
      b:SetNormalFontObject("GameFontNormalSmall")
      b:SetHighlightFontObject("GameFontHighlightSmall")
      b:SetScript("OnClick", function() Char().picked = name; win.scroll:SetVerticalScroll(0); Repoint() end)
      b:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
        GameTooltip:AddLine(Title(name))
        GameTooltip:AddLine(self.rank and string.format("Your skill: %d.", self.rank)
          or "Not yours: the whole route is shown, from the trainer on.", 1, 1, 1, true)
        GameTooltip:Show()
      end)
      b:SetScript("OnLeave", GameTooltip_Hide)
      win.profs[name] = b
    end
    local lit, rank = chosen.profession == name, Rank(chosen.by, name)
    b.rank = rank
    b:SetText(rank and Title(name) or ("|cff808080" .. Title(name) .. "|r"))
    pcall(function()
      local tint = lit and 0.55 or 1
      b:GetNormalTexture():SetVertexColor(tint, lit and 0.8 or 1, 1)
      b:GetPushedTexture():SetVertexColor(tint, lit and 0.8 or 1, 1)
    end)
    b:Show()
  end
  for name, b in pairs(win.profs) do
    if not (chosen and chosen.by[name]) then b:Hide() end
  end
end

-- The list under the Also button: the second profession to count ("also have": one or
-- none), each with the character's skill in it; a companion that changes nothing in this
-- route says so. Drawn again at every refresh.
local PICK_ROW = 20
DrawPicker = function()
  local house = House()
  local chosen = house and Chosen(house)
  if not chosen or not chosen.profession then picker:Hide() return end
  local c, by, mine, rows = Char(), chosen.by, chosen.profession, {}
  local function label(name)
    local rank = Rank(by, name)
    return Title(name) .. (rank and string.format(" |cff40ff40(%d)|r", rank) or " |cff808080(not yours)|r")
  end
  table.insert(rows, { text = "|cff33ccffAlso have|r  |cff808080(counts a second profession)|r" })
  table.insert(rows, { text = (chosen.also == nil and "|cff40ff40(x)|r " or "( ) ") .. "None",
    click = function() c.also[mine] = false; Repoint() end })
  for _, name in ipairs(chosen.names) do
    if name ~= mine and not IsSecondary(by, name) then
      local on = chosen.also == name
      local changes = WithCompanion(house, by[mine][ns.Settings().variant or ""], name) ~= nil
      table.insert(rows, { text = (on and "|cff40ff40(x)|r " or "( ) ") .. label(name) .. (changes and "" or "  |cff808080changes nothing|r"),
        click = function() c.also[mine] = name; Repoint() end })
    end
  end
  for i, row in ipairs(rows) do
    local b = picker.rows[i]
    if not b then
      b = CreateFrame("Button", nil, picker)
      b:SetSize(360, PICK_ROW)
      b:SetPoint("TOPLEFT", 10, -8 - (i - 1) * PICK_ROW)
      b.text = b:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
      b.text:SetPoint("LEFT", 4, 0)
      b.text:SetJustifyH("LEFT")
      b:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")
      b:SetScript("OnClick", function(self) if self.click then self.click() end end)
      picker.rows[i] = b
    end
    b.text:SetText(row.text)
    b.click = row.click
    b:Show()
  end
  for i = #rows + 1, #picker.rows do picker.rows[i]:Hide() end
  picker:SetHeight(#rows * PICK_ROW + 16)
end

local function TogglePicker()
  if not picker then
    picker = CreateFrame("Frame", "ForeverWowCraftPicker", win, "BackdropTemplate")
    picker:SetSize(380, 100)
    picker:SetPoint("TOPLEFT", win.also, "BOTTOMLEFT", 0, -2)
    picker:SetFrameStrata("DIALOG")
    picker:EnableMouse(true)
    picker:SetBackdrop({ bgFile = "Interface\\Tooltips\\UI-Tooltip-Background", edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
      edgeSize = 14, insets = { left = 3, right = 3, top = 3, bottom = 3 } })
    picker:SetBackdropColor(0.05, 0.05, 0.08, 0.98)
    picker.rows = {}
    win:HookScript("OnHide", function() picker:Hide() end)
    picker:Hide()
  end
  if picker:IsShown() then picker:Hide() else DrawPicker(); picker:Show() end
end

local function Wire()
  win.also:SetScript("OnClick", function()
    if last then TogglePicker() end
  end)
  win.also:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
    GameTooltip:AddLine("A second profession counted")
    GameTooltip:AddLine("The site's \"also have\": the route may make a reagent with it instead of buying. Your other "
      .. "profession by itself, or the one you pick from the list.", 1, 1, 1, true)
    GameTooltip:Show()
  end)
  win.also:SetScript("OnLeave", GameTooltip_Hide)
  if RANGE then
    win.reset:SetScript("OnClick", function()        -- from the character's own skill to the route's end
      if not last then return end
      local c = Char()
      c.from[last.plan.profession], c.upto[last.plan.profession] = nil, nil
      Refresh()
    end)
    win.reset:SetScript("OnEnter", function(self)
      GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
      GameTooltip:AddLine("Reset the skill range")
      GameTooltip:AddLine("From your own skill in the profession to the route's end.", 1, 1, 1, true)
      GameTooltip:Show()
    end)
    win.reset:SetScript("OnLeave", GameTooltip_Hide)
    win.gold:SetScript("OnEnter", function(self)
      GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
      GameTooltip:AddLine("Gold to spend")
      GameTooltip:AddLine("The gold in your bags, or an amount you type (12g 40s, or 12 for 12 gold) and Enter. The summary says "
        .. "how far up the route it goes, at the route's prices for what is still to buy. Empty the box to go by your bags again.", 1, 1, 1, true)
      GameTooltip:Show()
    end)
    win.gold:SetScript("OnLeave", GameTooltip_Hide)
    win.cap:SetScript("OnEnter", function(self)
      GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
      GameTooltip:AddLine("Only as far as this gold goes")
      GameTooltip:AddLine("Ticked, the list and the Auctionator import stop at the skill the gold reaches: what to buy now. "
        .. "Selling what you make on the way gets some of it back, so you will get a little further than that.", 1, 1, 1, true)
      GameTooltip:Show()
    end)
    win.cap:SetScript("OnLeave", GameTooltip_Hide)
  end
  -- the focus cycled, with the recipes the document lists for it (every route buys recipes
  -- since 2 Nov 2026; a document from before has the trainer routes too, and theirs are kept)
  local function Distinct(house, part, default)
    local seen, keys = {}, {}
    for _, v in ipairs(house.variants or {}) do
      local k = v[part] or default(v)
      if not seen[k] then seen[k] = true; table.insert(keys, k) end
    end
    return keys
  end
  local function Turn(part, default)
    local house = House()
    local s = ns.Settings()
    local at = house and Variant(house, s.variant)
    if not at then return end
    local keys = Distinct(house, part, default)
    -- on the profession that has the fishing route, "Fishing only" is a third choice after the two
    -- focuses; on any other the control is what it was, and the choice kept for cooking is not touched
    local fishing = house.fish and ns.ChosenProfession() == house.fish.profession
    local c = Char()
    if fishing then table.insert(keys, "fishing") end
    local to = Cycle(keys, (fishing and c.fishing) and "fishing" or at.focus, 1)
    if to == "fishing" then
      c.fishing = true
    else
      if fishing then c.fishing = nil end
      s.variant = VariantFor(house, at.recipes, to) or s.variant
    end
    Repoint()
  end
  win.focus:SetScript("OnClick", function() Turn(4, function() return "profit" end) end)
  win.focus:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
    GameTooltip:AddLine("Mode")
    GameTooltip:AddLine("Click to change.", 1, 1, 1, true)
    local house = House()
    local at = house and Variant(house, ns.Settings().variant)
    local fish = house and house.fish and ns.ChosenProfession() == house.fish.profession
    local active = fish and Char().fishing and "fishing" or at and at.focus
    local modes = {
      { "profit", "Profit", "What you make is sold at the auction house, and the route is the cheapest once it is." },
      { "skill", "Skill-up", "Nothing is listed: what you make goes to a vendor, and the route is the cheapest per skill point net of that "
        .. "(a dearer craft that a vendor pays well for can beat a cheaper one)." },
    }
    if fish then table.insert(modes, { "fishing", "Fishing only", ns.FISHING_ABOUT }) end
    for _, m in ipairs(modes) do
      local on = m[1] == active
      GameTooltip:AddLine((on and "|cff40ff40> " .. m[2] .. "|r" or "   " .. m[2]) .. ": " .. m[3], 1, 1, 1, true)
    end
    GameTooltip:Show()
  end)
  win.focus:SetScript("OnLeave", GameTooltip_Hide)
  win.alts:SetScript("OnClick", function()
    ns.Settings().alts = ns.Settings().alts == false        -- counted unless switched off (the shipped default, 7 Nov 2026)
    Refresh()
  end)
  win.alts:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
    GameTooltip:AddLine("Count your other characters")
    GameTooltip:AddLine("Also take from the bags and banks of this account's other characters of the same auction house, "
      .. "as they were when each was last played with this addon. Getting the items to this character is yours to do.", 1, 1, 1, true)
    GameTooltip:Show()
  end)
  win.alts:SetScript("OnLeave", GameTooltip_Hide)
  if RANGE then
    -- an end of the slider moved: the part of the route from here to there. The left end at
    -- the character's own skill, and the right at the route's end, are the plain route again
    -- (nothing kept).
    win.range.OnChanged = function(from, upto)
      if not last then return end
      local c, plan = Char(), last.plan
      local own = math.max(plan.start, math.min(c.skills[plan.skill_line] or plan.start, plan.target))
      c.from[plan.profession] = from ~= own and from or nil
      -- the right end where the gold cut the route is the gold's, not the player's: kept as it was
      if upto ~= last.upto or not last.capped then c.upto[plan.profession] = upto < plan.target and upto or nil end
      Refresh()
    end
    win.range:SetScript("OnEnter", function(self)
      GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
      GameTooltip:AddLine("A part of the route")
      GameTooltip:AddLine("Drag an end, click the track, or turn the wheel: the list, the costs and the Auctionator list are "
        .. "for the part between the two ends. The left end at your own skill and the right at the route's end is the "
        .. "whole route from where you are.", 1, 1, 1, true)
      GameTooltip:Show()
    end)
    win.range:SetScript("OnLeave", GameTooltip_Hide)
  end
  win.auctionator:SetScript("OnClick", function() ns.ShowAuctionator() end)
  win.auctionator:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
    GameTooltip:AddLine("Auctionator shopping list")
    GameTooltip:AddLine("The shopping list as an Auctionator import string, to copy: what is still to buy on the auction house "
      .. "after your bags and bank, with quantities, or everything from nothing. Vendor items are left out.", 1, 1, 1, true)
    GameTooltip:Show()
  end)
  win.auctionator:SetScript("OnLeave", GameTooltip_Hide)
end

function ns.ShowAuctionator(whole)
  if not win or not last then ns.Print("no route to list: /fwc first") return end
  ShowCopyBox(whole or false)
end

function ns.ToggleWindow()
  if not win then Build(); Wire() end
  if win:IsShown() then win:Hide() else win:Show() end
end

-- ================================================================ events + the /fwc command
local watcher = CreateFrame("Frame")
for _, event in ipairs({ "PLAYER_ENTERING_WORLD", "BAG_UPDATE_DELAYED", "BANKFRAME_OPENED", "BANKFRAME_CLOSED",
                         "PLAYERBANKSLOTS_CHANGED", "MAIL_SHOW", "MAIL_CLOSED", "MAIL_INBOX_UPDATE",
                         "AUCTION_HOUSE_SHOW", "AUCTION_HOUSE_CLOSED", "OWNED_AUCTIONS_UPDATED", "AUCTION_OWNED_LIST_UPDATE",
                         "SKILL_LINES_CHANGED", "CHAT_MSG_SKILL", "PLAYER_LOGOUT" }) do
  pcall(watcher.RegisterEvent, watcher, event)      -- a client without one of them refuses it: the others still count
end
watcher:SetScript("OnEvent", function(_, event)
  if event == "PLAYER_LOGOUT" then
    CountBags()
    NoteSkills()
    return
  end
  RefreshSoon()
end)

-- for the options page: the window drawn again (a switch of its changed there), and back in the middle
function ns.RefreshWindow() if win then Refresh() end end
function ns.ResetWindowPosition()
  ns.Settings().winPos = nil
  if win then win:ClearAllPoints(); win:SetPoint("CENTER") end
end

SLASH_FOREVERWOWCRAFT1 = "/fwc"
SlashCmdList.FOREVERWOWCRAFT = function(msg)
  msg = (msg or ""):lower():gsub("^%s+", ""):gsub("%s+$", "")
  local cmd, arg = msg:match("^(%S*)%s*(.-)$")
  local house, chosen, plan = House()
  if cmd == "from" or cmd == "to" or cmd == "also" then
    NoteSkills()                            -- the default profession is the character's own
    chosen = house and Chosen(house)
    plan = chosen and chosen.plan
  end
  if (cmd == "from" or cmd == "to" or cmd == "also") and not plan then
    ns.Print(chosen and "no profession shown yet: pick one with the window's first button" or EmptyState().summary)
  elseif cmd == "from" then
    local c = Char()
    c.from[plan.profession] = tonumber(arg)
    ns.Print(c.from[plan.profession] and string.format("%s is planned from skill %d. /fwc from auto goes by your own skill again.",
      Title(plan.profession), c.from[plan.profession]) or (Title(plan.profession) .. " is planned from your own skill."))
    Refresh()
  elseif cmd == "to" and RANGE then
    local c = Char()
    c.upto[plan.profession] = tonumber(arg)
    ns.Print(c.upto[plan.profession] and string.format("%s is planned up to skill %d. /fwc to auto goes to the route's end again.",
      Title(plan.profession), c.upto[plan.profession]) or (Title(plan.profession) .. " is planned to the route's end."))
    Refresh()
  elseif cmd == "also" then                 -- the second profession counted: a name, none, or auto
    local c = Char()
    local name = arg:gsub("%s+", "-")
    if arg == "auto" or arg == "" then c.also[plan.profession] = nil
    elseif arg == "none" then c.also[plan.profession] = false
    elseif chosen.by[name] and IsSecondary(chosen.by, name) then ns.Print(Title(name) .. " is a secondary profession: not counted as a second one yet") return
    elseif chosen.by[name] and name ~= plan.profession then c.also[plan.profession] = name
    else ns.Print("no such profession: " .. arg .. ". /fwc also <profession> | none | auto") return end
    Repoint()
    chosen = Chosen(house)
    ns.Print(chosen.also and string.format("%s is planned with %s%s.", Title(plan.profession), Title(chosen.also),
      chosen.applied and "" or " (which changes nothing in it)") or (Title(plan.profession) .. " is planned on its own."))
  elseif cmd == "alts" then
    ns.Settings().alts = ns.Settings().alts == false
    ns.Print(ns.Settings().alts ~= false and "your other characters' bags and banks are counted too" or "only this character's bags and bank are counted")
    Refresh()
  elseif cmd == "help" or cmd == "?" then
    ns.Print("/fwc shows what your professions still need, less what you have. /fwc from <skill> | from auto"
      .. (RANGE and " | to <skill> | to auto" or "") .. " | also <profession> | also none | also auto | alts. /fwcs is the scanner.")
  else
    ns.ToggleWindow()
  end
end

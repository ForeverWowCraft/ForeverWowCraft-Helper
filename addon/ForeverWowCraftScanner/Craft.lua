-- The route, made: the FWC button on the game's profession panel crafts the next step of the
-- /fwc route of the profession the panel shows, as Create All would. One click is one thing
-- made: the step's recipe, or first what the step makes on the way (bolts for a bag). Each
-- click starts from the character's skill as it is then, so a step cut short carries on and a
-- finished one hands over to the next; nothing is kept between clicks. The crafting stops by
-- itself when the skill reaches the step's end (the game says each point), so a lucky run
-- wastes no reagents. When a click can make nothing, the button says why instead, in its
-- tooltip and in chat, and the arrow leads to what it needs (Places.lua) with the words under
-- it. What the verdict is comes from Verdict.lua; this file is the button, the arrow it sets,
-- the pass that keeps the arrow with the window closed, and the events.

local _, ns = ...
local Char, House = ns.inv.Char, ns.inv.House
local PREFIX = "|cff" .. ns.BRAND.gold .. "ForeverWowCraft|r: "
local V = ns.verdict
local Verdict, Bags, Shopping, api, NoteStations, Selected, N = V.Verdict, V.Bags, V.Shopping, V.api, V.NoteStations, V.Selected, V.N

-- ================================================================ the button
-- An icon at the top right of the recipe page's detail, a glow pulsing round it in the colour
-- of what the click does: gold to make, green to buy, blue to learn, orange for a station it
-- needs, red when the gold in the bags is short of what the step buys; no glow, and the icon
-- grey, when it can do nothing. The tooltip has the words and the
-- whole story; a click says the words in chat and acts; the arrow, when there is one, has
-- them in brackets.
local button, running          -- running = { to, line } while a click's crafting may be going
local pointed                  -- the last { target, title, text } the arrow was set to, for the Keep arrow box

local GLOWS = { Make = { 0.3, 0.95, 1 }, Buy = { 0.3, 1, 0.4 }, Collect = { 0.3, 1, 0.4 }, Learn = { 0.75, 0.55, 1 }, Needs = { 1, 0.55, 0.2 },   -- cyan, green, green, violet, orange
                Short = { 1, 0.35, 0.35 }, ["Place"] = { 1, 0.55, 0.2 } }                                                   -- red: the gold is short; orange: a camp object to place
local function ModeOf(v)
  local word = v and v.text and v.text:match("^(%a+)")
  if word == "Make" and not v.spell then word = nil end             -- "Make N X first": nothing to make yet
  return GLOWS[word] and word or nil
end

-- what the arrow is set to, kept for the character (FWCS_DB, with its other things) so that
-- a reload or a login brings it back as it was, with no window opened; nil when it is cleared
local function Remember()
  local c = Char()
  if not pointed then c.arrow = nil; return end
  local p = pointed.target
  c.arrow = { title = pointed.title, note = pointed.note, profession = pointed.profession, learn = pointed.learn, by = pointed.by, make = pointed.make,
              place = p and { map = p.map, x = p.x, y = p.y, kind = p.kind, what = p.what, name = p.name } or nil }
end

-- the note under the arrow from a verdict's aside: the rank, and the nearest trainer teaching it
local function Aside(v)
  local a = v.aside
  if not a then return nil end
  local p, d, here = ns.NearestPlace(a.place[1], a.place[2], a.place[3], a.place[5])
  local detail
  if p then
    local who = p.name and (": " .. p.name) or ""
    if here and d then detail = string.format("%s%s, %d yd", a.place[4], who, math.floor(d + 0.5))
    elseif here then detail = a.place[4] .. who
    else detail = string.format("%s%s, in %s", a.place[4], who, ns.places.MapName(p.map)) end
  else
    detail = a.place[1] == "trainer" and ("no " .. a.place[4]:lower() .. " seen yet that teaches it") or ("no " .. a.place[4]:lower() .. " known yet")
  end
  if a.cap then detail = string.format("%s (from skill %d; the cap is %d)", detail, a.from, a.cap) end
  return { text = a.text, detail = detail }
end

-- the arrow set from a verdict: at the nearest of what it needs, with the way in its tooltip;
-- `by` says who set it ("panel" | "headless"), for Headless to know which it may clear
local function Point(v, by)
  local note = v.note or v.text                  -- a buy verdict's note lists the items and their sources
  if v.place then
    local p, d, here = ns.NearestPlace(v.place[1], v.place[2], v.place[3], v.place[5])
    if p then
      local title = v.place[4]
      if p.name and (p.kind == "vendor" or p.kind == "trainer" or p.kind == "quest") then title = title .. ": " .. p.name end
      v.target, v.title = p, title
      pointed = { target = p, title = title, note = note, by = by or "panel", profession = v.profession and ns.Title(v.profession) or nil, learn = v.learn, rank = v.rank }
      table.insert(v.tip, here and (d and string.format("The arrow points at the nearest: %s, %d yd.", title, math.floor(d + 0.5)) or "The arrow points at the nearest: " .. title .. ".")
        or string.format("The nearest seen is in %s: %s%s.", ns.places.MapName(p.map), title, d and string.format(", about %d yd as the crow flies", math.floor(d + 0.5)) or ""))
      ns.SetArrow(p, title, false, note, pointed.profession)
    else
      local what = v.place[1] == "station" and v.place[2]:lower() or v.place[1] == "auction" and "auctioneer" or v.place[1] == "quest" and "quest giver" or v.place[1]
      local how = v.place[1] == "station" and "open this panel at one" or v.place[1] == "trainer" and "open a trainer's window"
        or v.place[1] == "vendor" and "open a merchant's window" or v.place[1] == "mailbox" and "open a mailbox"
        or v.place[1] == "quest" and "the tooltip says who gives it and where" or "open the auction house"
      table.insert(v.tip, string.format("No %s seen yet: %s, and the arrow points there from then on.", what, how))
      -- nothing of the kind known: the arrow stays, a question mark for a point, and says so
      pointed = { title = "No " .. what .. " seen yet", note = note, by = by or "panel", profession = v.profession and ns.Title(v.profession) or nil, learn = v.learn }
      ns.SetArrow(nil, pointed.title, false, note, pointed.profession)
    end
  elseif v.show or v.text:match("^Needs ") then     -- a tool to buy, or needs of no place: the arrow says the words
    pointed = { title = v.text, by = by or "panel", profession = v.profession and ns.Title(v.profession) or nil }
    ns.SetArrow(nil, v.text, false, nil, pointed.profession)
  elseif v.spell then                          -- something to make, here: the words, under a hammer
    pointed = { title = v.text, by = by or "panel", profession = v.profession and ns.Title(v.profession) or nil, make = true }
    ns.SetArrow(nil, v.text, false, nil, pointed.profession, "make")
  elseif not v.idle then                       -- no profession open (the overview page), or none with a route: the arrow is left be
    pointed = nil
    ns.ClearArrow()
  end
  if pointed then pointed.aside = Aside(v); ns.SetArrowAside(pointed.aside) end
  Remember()
end

-- the arrow as it was for this character, back after a reload or a login, before any
-- window opens; the passes then move it on as they may
local function Restore()
  if ns.Settings().arrowKeep == false or ns.Settings().arrow == false then return end
  local saved = Char().arrow
  if type(saved) ~= "table" then return end
  pointed = { target = saved.place, title = saved.title, note = saved.note, profession = saved.profession, learn = saved.learn, by = saved.by or "panel", make = saved.make }
  ns.SetArrow(saved.place, saved.title, false, saved.note, saved.profession, saved.make and "make" or nil)
end

local Standing                           -- below: a profession's verdict as things stand, without its panel
local panelOpen = false                  -- by the trade skill events, for a client whose window cannot say

-- whether the profession window is on screen. The window says when it can; the trade skill
-- events are no guide: the overview tile fires "closed" with the window open, and K toggles
-- the window without them
local function PanelShown()
  local win = ProfessionsFrame or TradeSkillFrame
  if type(win) == "table" and win.IsShown then
    local ok, shown = pcall(win.IsShown, win)
    if ok and shown ~= nil then return shown and true or false end
  end
  return panelOpen
end

-- the profession the button last served, unlearned (engineering dropped to level tailoring,
-- 12 Oct 2026: the arrow kept engineering's step until a tile was clicked): the character's
-- skills say it is gone, so it is forgotten, and the arrow set for it goes. The pass without
-- the window then serves the next the character has; with the window open, the next tile clicked
local SkillsReadable = ns.inv.SkillsReadable     -- whether the client's skill list can be read now (Inventory.lua)
local function Unlearned()
  local c = Char()
  ns.inv.NoteSkills()
  local plan = c.making and ns.RouteFor(c.making)
  if not plan or not SkillsReadable() or c.skills[plan.skill_line] then return false end
  local was = ns.Title(c.making)
  c.making = nil
  if pointed and pointed.profession == was then pointed = nil; Remember(); ns.ClearArrow() end
  return true
end

-- the window open on a page without the button (the overview): the arrow of the profession
-- last shown, as things stand; the dashboard is no profession and must not touch the arrow
local function Overview()
  if Unlearned() or not Char().making then return end
  local alt = Standing(Char().making)
  if alt and not alt.idle then Point(alt, "panel") end
end

local function Refresh()
  if not button or not button:IsShown() then return end
  local visible = button.IsVisible and button:IsVisible()
  if visible == false then                        -- the button is hidden with its page
    if PanelShown() then Overview() end
    return
  end
  -- a click's crafting under way: the verdict holds until the cast ends (the bags change
  -- with every craft, and the words and the arrow flickered along, 12 Oct 2026)
  if running and UnitCastingInfo and (UnitCastingInfo("player")) then return end
  local ok, v = pcall(Verdict)
  if not ok then v = { text = "ForeverWowCraft: error", tip = { tostring(v) } } end
  button.verdict = v
  if V.Switched() then
    if ns.ReloadShopping then ns.ReloadShopping() end  -- the list open at the house: that profession's now
  end
  pcall(NoteStations, Selected())
  if v.recipe or v.spell then pcall(NoteStations, v.recipe or v.spell) end
  if v.idle then Overview() else Point(v) end        -- the overview page: the arrow of the profession last shown
  local mode = ModeOf(v)
  if mode ~= rawget(button, "mode") then
    button.mode = mode or false
    local pulse = rawget(button, "pulse")
    if mode then
      local c = GLOWS[mode]
      button.glow:SetVertexColor(c[1], c[2], c[3])                       -- the glow in the colour of what the click does
      button.glow:Show()
      button.icon:SetVertexColor(1, 1, 1)
      if button.icon.SetDesaturated then button.icon:SetDesaturated(false) end
      if pulse and not pulse:IsPlaying() then pulse:Play() end
    else
      button.glow:Hide()                                                 -- grey mark, no glow: nothing to do
      button.icon:SetVertexColor(0.6, 0.6, 0.6)
      if button.icon.SetDesaturated then button.icon:SetDesaturated(true) end
      if pulse and pulse:IsPlaying() then pulse:Stop() end
      button.face:SetAlpha(1)
    end
  end
  if GameTooltip:GetOwner() == button and GameTooltip:IsShown() then button:GetScript("OnEnter")() end
end

-- The arrow with the profession window closed, while Keep arrow is ticked: from the route
-- of the profession the button last served (else the one the /fwc window shows, which is the
-- first the character has trained when none was picked), at the character's skill, as far as
-- the route and the bags tell without the panel. What is known and what a recipe requires are
-- the panel's to say, so those two checks are left out. Run as the world is entered (a
-- reload, a login), as the bags or a skill change, and every five seconds, so the arrow is
-- there again after a reload without the window opened, and moves on as things are bought.
-- whether the character knows a recipe, by the spellbook (a recipe is a spell it knows):
-- true, or false when the client cannot say
local function Known(spell)
  if IsPlayerSpell and IsPlayerSpell(spell) then return true end
  if IsSpellKnown and IsSpellKnown(spell) then return true end
  return false
end

-- the verdict of a profession as things stand, without its panel: at the character's skill
-- and cap. Known: by the spellbook (a recipe is a spell: its no is a no, so nothing is
-- offered to make that is not known, 11 Oct 2026), or by the panel's data when that is
-- loaded; unknown only on a client whose spellbook cannot be asked. Requirements: the
-- client's, which answer once the panel has been open this session, and say nothing before
function Standing(profession)
  local plan = profession and ns.RouteFor(profession)
  if not plan then return nil end
  local c = Char()
  ns.inv.NoteSkills()
  local skill = c.skills[plan.skill_line]
  if not skill then return nil end
  local learned = api.Learned
  api.Learned = function(spell)
    if Known(spell) or learned(spell) == true then return true end
    if IsPlayerSpell or IsSpellKnown then return false end
    return nil
  end
  local ok, v = pcall(Verdict, { open = { id = plan.skill_line, rank = skill, max = (c.caps or {})[plan.skill_line] }, profession = profession })
  api.Learned = learned
  if ok and type(v) == "table" then return v end
end

-- in a fight the verdict waits (a bag change, a skill-up or the 5 s ticker would each run a
-- whole route walk there): it is owed, and run once the fight is over (PLAYER_REGEN_ENABLED)
local owed = false
local function Headless()
  if InCombatLockdown and InCombatLockdown() then owed = true; return end
  owed = false
  if not House() then return end
  Unlearned()
  if PanelShown() or ns.Settings().arrowKeep == false or ns.Settings().arrow == false then return end
  local c = Char()
  local profession = (c.making and ns.RouteFor(c.making)) and c.making or (ns.OwnProfession and ns.OwnProfession())
  local v = Standing(profession)
  if not v or v.idle then return end
  -- somewhere to go: pointed at. Else the arrow is this pass's to set only when it set the
  -- one there, or none is there, or the one there was for a recipe now known: the panel's
  -- (a trainer, an anvil: its checks) stays otherwise
  local mine = not pointed or pointed.by == "headless" or (pointed.learn and Known(pointed.learn)) or (pointed.rank ~= nil) or false
  if v.place or mine then Point(v, "headless") end
end

local function Click()
  Refresh()
  local v = button and button.verdict
  if not v then return end
  print(PREFIX .. v.text .. ". " .. (v.tip and v.tip[#v.tip] or ""))
  if not v.spell then
    if pointed then ns.SetArrow(pointed.target, pointed.title, true, pointed.note, pointed.profession) end      -- brought back after a right-click
    if v.shopping then ns.ShowShopping(v.shopping) end
    return
  end
  running = { to = v.to, line = v.line }
  if not api.Craft(v.spell, v.crafts) then
    print(PREFIX .. "the client would not craft from the button; use Create All with " .. (v.text:gsub("^Make %d+ ", "")) .. ".")
    running = nil
  end
end

local function Tip()
  local v = button and button.verdict
  if not v then return end
  GameTooltip:SetOwner(button, "ANCHOR_TOP")
  GameTooltip:AddLine("ForeverWowCraft: " .. v.text)
  for _, line in ipairs(v.tip or {}) do GameTooltip:AddLine(line, 1, 1, 1, true) end
  GameTooltip:Show()
end

-- the button on the recipe page, in the corner art at the bottom left of the recipe's detail,
-- just above the page's own Create All, once the page is there: an icon with a glow that
-- pulses, the window's frame holding the Keep arrow box
local function Place()
  if button then return end
  local win, page = ProfessionsFrame, ProfessionsFrame and ProfessionsFrame.CraftingPage
  local parent, above = page, page and (page.CreateAllButton or page.CreateButton)
  if not above then
    win, parent, above = TradeSkillFrame, TradeSkillFrame, TradeSkillCreateAllButton or TradeSkillCreateButton
  end
  if not (win and parent and above) then return end
  button = CreateFrame("Button", "ForeverWowCraftMake", parent)
  button:SetSize(110, 80)                       -- wide to the right, tall enough for the mark; its left edge off the corner art
  button:SetPoint("BOTTOMLEFT", above, "TOPLEFT", 60, 8)
  button:SetFrameLevel((above.GetFrameLevel and above:GetFrameLevel() or 1) + 3)
  -- the mark (icon.tga, 128 px, from the brand's icon; the letters FWC until 12 Oct 2026), with
  -- a glow round it pulsing in brightness in the colour of what the click does (the pulse is
  -- the alpha of the frame that holds the glow, animated there and back; the mark itself
  -- stays, grey when there is nothing to do)
  button.icon = button:CreateTexture(nil, "ARTWORK")
  button.icon:SetSize(68, 68)
  button.icon:SetPoint("CENTER", 0, 0)
  button.icon:SetTexture("Interface\\AddOns\\ForeverWowCraftScanner\\icon")
  button.icon:SetVertexColor(0.6, 0.6, 0.6)
  if button.icon.SetDesaturated then button.icon:SetDesaturated(true) end
  button.face = CreateFrame("Frame", nil, button)
  button.face:SetAllPoints()
  button.glow = button.face:CreateTexture(nil, "OVERLAY")
  button.glow:SetTexture("Interface\\Buttons\\UI-ActionButton-Border")
  button.glow:SetBlendMode("ADD")
  button.glow:SetSize(124, 124)                 -- the border art has room round its square: this much for a 68 px mark
  button.glow:SetPoint("CENTER", button.icon, "CENTER", 0, 0)
  button.glow:Hide()
  local group = button.face.CreateAnimationGroup and button.face:CreateAnimationGroup()
  if type(group) == "table" and group.CreateAnimation then
    local a = group:CreateAnimation("Alpha")
    if a.SetFromAlpha then a:SetFromAlpha(0.35); a:SetToAlpha(1) elseif a.SetChange then a:SetChange(-0.65) end
    a:SetDuration(0.8)
    group:SetLooping("BOUNCE")
    button.pulse = group
  end
  button:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Square", "ADD")
  button:SetScript("OnClick", Click)
  button:SetScript("OnEnter", Tip)
  button:SetScript("OnLeave", function() if GameTooltip:GetOwner() == button then GameTooltip:Hide() end end)
  button:SetScript("OnShow", Refresh)
  if win.HookScript then                        -- the window's own showing and hiding, the surest word
    win:HookScript("OnShow", function() panelOpen = true; ns.ArrowBack(); Refresh() end)
    win:HookScript("OnHide", function()
      panelOpen, running = false, nil
      if ns.Settings().arrowKeep == false then pointed = nil; Remember(); ns.ClearArrow() else Headless() end
    end)
  end
  -- the arrow kept when the panel closes: a box at the window's top right corner, by the X,
  -- on every page (its own strata: by the X it went unseen, 11 Oct 2026)
  local keep = CreateFrame("CheckButton", "ForeverWowCraftKeepArrow", win, "UICheckButtonTemplate")
  keep:SetSize(22, 22)
  keep:SetPoint("TOPRIGHT", win, "TOPRIGHT", -34, -6)
  keep:SetFrameStrata("HIGH")
  keep.label = keep:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  keep.label:SetPoint("RIGHT", keep, "LEFT", -2, 0)
  keep.label:SetText("Keep arrow")
  keep:SetChecked(ns.Settings().arrowKeep ~= false)
  keep:SetScript("OnClick", function(s)
    local on = s:GetChecked() and true or false
    ns.Settings().arrowKeep = on
    if on then
      if pointed then ns.SetArrow(pointed.target, pointed.title, true, pointed.note, pointed.profession) end   -- ticked: the arrow back, if put away
      Headless()
    elseif not PanelShown() then
      ns.ClearArrow()                                                                       -- unticked with the window closed: as before, no arrow
      pointed = nil
      Remember()
    end                                                                                     -- unticked with it open: nothing until it closes
  end)
  keep:SetScript("OnEnter", function()
    GameTooltip:SetOwner(keep, "ANCHOR_TOP")
    GameTooltip:AddLine("Keep the arrow")
    GameTooltip:AddLine("Ticked, the arrow stays when this window closes, until what it points at is reached or it is right-clicked. Unticked, it goes with the window.", 1, 1, 1, true)
    GameTooltip:Show()
  end)
  keep:SetScript("OnLeave", function() GameTooltip:Hide() end)
  -- the panel's "Requires" changes as the character walks (to an anvil), with no event: looked at now and then
  if C_Timer and C_Timer.NewTicker then C_Timer.NewTicker(1.5, Refresh) end
  Refresh()
end

-- a skill point gained: the step's end reached stops the crafting
local function SkillChanged()
  if not running then return end
  local open = api.Open()
  local skill = open and open.rank
  if not skill then
    ns.inv.NoteSkills()
    skill = Char().skills[running.line]
  end
  if skill and skill >= running.to then
    api.Stop()
    print(PREFIX .. string.format("skill %d reached, crafting stopped: press Escape to cancel the one under way. Click Make again for what comes next.", skill))
    running = nil
  end
end

local frame = CreateFrame("Frame")
for _, event in ipairs({ "ADDON_LOADED", "PLAYER_ENTERING_WORLD", "TRADE_SKILL_SHOW", "TRADE_SKILL_LIST_UPDATE", "TRADE_SKILL_UPDATE", "TRADE_SKILL_CLOSE",
                         "SKILL_LINES_CHANGED", "CHAT_MSG_SKILL", "BAG_UPDATE_DELAYED", "PLAYER_MONEY", "PLAYER_LEVEL_UP",
                         "NEW_RECIPE_LEARNED", "LEARNED_SPELL_IN_TAB", "LEARNED_SPELL_IN_SKILL_LINE", "ITEM_DATA_LOAD_RESULT",
                         "MAIL_SHOW", "MAIL_INBOX_UPDATE", "MAIL_CLOSED", "PLAYER_REGEN_ENABLED" }) do
  pcall(frame.RegisterEvent, frame, event)
end
local named = false             -- a redraw for names that came is on its way
frame:SetScript("OnEvent", function(_, event, name)
  if event == "ADDON_LOADED" then
    if name == "Blizzard_Professions" or name == "Blizzard_TradeSkillUI" then Place() end
    return
  end
  if event == "PLAYER_REGEN_ENABLED" then                  -- the fight is over: the verdict it held back
    if owed then Headless() end
    return
  end
  if event == "ITEM_DATA_LOAD_RESULT" then                 -- an item's name came from the client: the arrow's note names it as the game does
    -- they come in bursts (hundreds while a list is scanned): one redraw for a burst
    if pointed and not named then
      named = true
      local function redraw() named = false; if PanelShown() then Refresh() else Headless() end end
      if C_Timer and C_Timer.After then C_Timer.After(0.5, redraw) else redraw() end
    end
    return
  end
  if event == "PLAYER_ENTERING_WORLD" then                 -- a login or a reload: the arrow back as it was, then moved on
    local function back() Restore(); Headless() end
    if C_Timer and C_Timer.After then C_Timer.After(2, back) else back() end
    return
  end
  if event == "TRADE_SKILL_SHOW" then panelOpen = true; ns.ArrowBack() end     -- the profession window: the arrow put away comes back
  if event == "TRADE_SKILL_CLOSE" then                     -- fired for the overview tile too, with the window open
    running, panelOpen = nil, false
    if PanelShown() then Overview()
    elseif ns.Settings().arrowKeep == false then pointed = nil; Remember(); ns.ClearArrow()
    else Headless() end
    return
  end
  if event == "SKILL_LINES_CHANGED" or event == "CHAT_MSG_SKILL" then SkillChanged() end
  if event == "NEW_RECIPE_LEARNED" or event == "LEARNED_SPELL_IN_TAB" or event == "LEARNED_SPELL_IN_SKILL_LINE" then
    if panelOpen then Refresh() else Headless() end                    -- a recipe learned at the trainer: the arrow moves on
    return
  end
  Place()
  Refresh()
  if not PanelShown() then Headless() end
end)
Place()
if C_Timer and C_Timer.NewTicker then C_Timer.NewTicker(5, Headless) end

-- the route changed by a click in the /fwc window (skill-up, the second profession, another
-- profession picked): the Make button's words, the arrow and the shopping list at once, not at
-- the next pass (the user asked whether the arrow follows the skill-up box, 6 Nov 2026)
function ns.RoutePicked()
  if PanelShown() then Refresh() else Headless() end
  if ns.ReloadShopping then ns.ReloadShopping() end
end

-- /fwcs needs: what the client says a recipe requires, raw, for the recipe selected in the
-- panel and for the one the button's verdict is about (a spell id as the argument asks of
-- that one): to learn what the client answers, and when (11 Oct 2026: nothing for Copper
-- Tube, whose panel said Anvil and Blacksmith Hammer)
function ns.NeedsCommand(arg)
  local spells = {}
  local given = tonumber(arg)
  if given then table.insert(spells, { "asked", given }) end
  local sel = Selected()
  if sel then table.insert(spells, { "selected", sel }) end
  local v = button and button.verdict
  if v and (v.recipe or v.spell) then table.insert(spells, { "the verdict's", v.recipe or v.spell }) end
  if #spells == 0 then print(PREFIX .. "no recipe: open a profession and select one, or give a spell id (/fwcs needs 3922)"); return end
  for _, s in ipairs(spells) do
    local ok, reqs = pcall(C_TradeSkillUI and C_TradeSkillUI.GetRecipeRequirements or function() end, s[2])
    local parts = {}
    for _, r in ipairs(ok and type(reqs) == "table" and reqs or {}) do
      if type(r) == "table" then
        table.insert(parts, string.format("%s (type %s, met %s, place %s)", tostring(r.name), tostring(r.type), tostring(r.met), tostring(api.IsPlace(r))))
      else
        table.insert(parts, tostring(r))
      end
    end
    print(PREFIX .. string.format("%s recipe, spell %d (%s): %s", s[1], s[2], ns.RecipeName and (select(2, pcall(ns.RecipeName, { spell = s[2] }))) or "?",
      #parts > 0 and table.concat(parts, "; ") or (ok and "nothing" or ("error: " .. tostring(reqs)))))
  end
end


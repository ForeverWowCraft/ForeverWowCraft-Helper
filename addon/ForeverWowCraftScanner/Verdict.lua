-- What the Make button would do, worked out: the next thing to make from the route and the
-- bags (ns.NextCraft, which asks the game nothing, so the tests run it outside the game), the
-- client's crafting calls by whichever panel it has (api: Blizzard_Professions and
-- Blizzard_TradeSkillUI craft by spell, the old TradeSkillFrame by an index into its list),
-- and the verdict itself (Verdict): make this, buy that, learn, train the next rank, a tool or a
-- place the recipe needs, or the route done. Craft.lua is the button, the arrow and the
-- events; Shop.lua the list at the auction house. Exported as ns.verdict and ns.craft.
--
-- The route is the one the /fwc window shows for that profession (its variant and companion:
-- ns.RouteFor).
--
-- WHAT THIS FILE GATHERS: with the profession panel open, a crafting station (an anvil, a forge)
-- the panel says the character stands at, as a place for the arrow (ns.NotePlace, Places.lua:
-- kept here, not sent); and the item-data level of the recipe scroll the route buys
-- (ns.NoteRecipeLevel, ForeverWowCraftScanner.lua: sent with the vendors met, pooled with other
-- players' to know the level each recipe is gated at); and the tools the client says the route's
-- recipes need (an enchanter's rods) with what each tool's recipe takes (ns.LearnTools:
-- FWCS_DB.__tools, kept on this computer for the shopping list, not sent). Nothing of the
-- character. Everything the addon gathers: docs/scanner-addon.md, "What the addon gathers".

local _, ns = ...
local Char, House, Spelt = ns.inv.Char, ns.inv.House, ns.inv.Spelt

-- ================================================================ the next thing to make
-- The first step of the route with crafts left at `skill`, walked on its own with `have` =
-- { [item] = units } in hand: { step, spell, crafts, from, to, uses,
--   buy = { {item, units}, ... }                what `have` lacks for it, most first,
--   make = { {item, units, crafts, spell, uses}, ... }   what the step makes on the way (spell
--                                             nil when the document does not say how) };
-- nil when the route is done at `skill`.
function ns.NextCraft(plan, skill, have, upto)
  local step, left
  for _, s in ipairs(plan.steps or {}) do
    left = s.blocked and ((s.to > skill) and 1 or 0) or ns.CraftsLeft(s, skill)
    if left > 0 then step = s; break end
  end
  if not step then return nil end
  if step.blocked then                   -- nothing of the stretch fits at the character's level (ns.Effective)
    return { blocked = true, step = step, from = math.max(skill, step.from), to = step.to, asks = step.asks }
  end
  -- `upto` (the skill the gold reaches, ns.BudgetReach) cuts the step: a point at least
  local from = math.max(skill, step.from)
  local to = math.min(step.to, math.max(upto or step.to, from + 1))
  if to < step.to then left = ns.CraftsLeft(step, skill, to) end
  local walk = ns.Tailor(plan, skill, have, to)
  local out = { step = step, spell = step.spell, crafts = left, from = from, to = to, capped = to < step.to or nil,
                uses = step.uses, buy = {}, make = {} }
  for item, units in pairs(walk.buy) do table.insert(out.buy, { item, units }) end
  table.sort(out.buy, function(a, b) if a[2] ~= b[2] then return a[2] > b[2] end return a[1] < b[1] end)
  for item, units in pairs(walk.make) do
    local how = walk.how[item]
    table.insert(out.make, { item, units, how and math.ceil(units / how[1]) or units, how and how[3] or nil, how and how[2] or {} })
  end
  table.sort(out.make, function(a, b) return a[1] < b[1] end)
  return out
end

-- ================================================================ the client's crafting
-- the index of a spell in the old panel's list (its rows are what the character knows)
local function OldIndex(spell)
  for i = 1, (GetNumTradeSkills and GetNumTradeSkills() or 0) do
    local link = GetTradeSkillRecipeLink and GetTradeSkillRecipeLink(i)
    if link and tonumber(link:match("enchant:(%d+)")) == spell then return i end
  end
end

local api = {}

-- the profession the panel shows: { id = skill line, name, rank }, or nil with no panel
-- whether the window shows recipes that are not this character's: another player's profession
-- linked in chat, a guild's recipes, a vendor crafting
local function Linked()
  for _, f in ipairs({ C_TradeSkillUI and C_TradeSkillUI.IsTradeSkillLinked, C_TradeSkillUI and C_TradeSkillUI.IsTradeSkillGuild,
                       C_TradeSkillUI and C_TradeSkillUI.IsNPCCrafting, IsTradeSkillLinked, IsTradeSkillGuild }) do
    local ok, yes = pcall(f)
    if ok and yes == true then return true end
  end
  return nil
end

function api.Open()
  local open
  if C_TradeSkillUI and C_TradeSkillUI.GetBaseProfessionInfo then
    local ok, info = pcall(C_TradeSkillUI.GetBaseProfessionInfo)
    if ok and type(info) == "table" and (info.professionID or info.profession) then
      open = { id = info.professionID or info.profession, name = info.professionName or info.parentProfessionName, rank = info.skillLevel, max = info.maxSkillLevel }
    end
  end
  if not open and C_TradeSkillUI and C_TradeSkillUI.GetTradeSkillLine then
    local ok, id, name, rank, max = pcall(C_TradeSkillUI.GetTradeSkillLine)
    if ok and id and id ~= 0 then open = { id = id, name = name, rank = rank, max = max } end
  end
  if not open and GetTradeSkillLine then
    local name, rank, max = GetTradeSkillLine()
    if name and name ~= "" then open = { name = name, rank = rank, max = max } end
  end
  if open then open.linked = Linked() end
  return open
end

-- whether the character knows the recipe; nil when the client cannot say
function api.Learned(spell)
  if C_TradeSkillUI and C_TradeSkillUI.GetRecipeInfo then
    local ok, info = pcall(C_TradeSkillUI.GetRecipeInfo, spell)
    if ok then return type(info) == "table" and info.learned == true end
    return nil
  end
  if GetNumTradeSkills then return OldIndex(spell) ~= nil end
end

-- what the recipe needs: { { name, met, place }, ... }; place = a station to stand at (Anvil,
-- Forge) rather than a tool carried (Blacksmith Hammer), by the client's kind where it says,
-- else by name
local STATIONS = { anvil = true, forge = true, cookingfire = true, moonwell = true, campfire = true }
local function IsPlace(r)
  if STATIONS[Spelt(r.name)] then return true end            -- an anvil is a place whatever the type says
  local area = Enum and Enum.RecipeRequirementType and Enum.RecipeRequirementType.Area
  if area ~= nil and r.type ~= nil then return r.type == area end
  return false
end
function api.Requirements(spell)
  local out = {}
  if C_TradeSkillUI and C_TradeSkillUI.GetRecipeRequirements then
    local ok, reqs = pcall(C_TradeSkillUI.GetRecipeRequirements, spell)
    if ok and type(reqs) == "table" then
      for _, r in ipairs(reqs) do
        if type(r) == "table" and r.name and r.name ~= "" then table.insert(out, { name = r.name, met = r.met ~= false, place = IsPlace(r) }) end
      end
    end
  elseif GetTradeSkillTools then
    local i = OldIndex(spell)
    if i then
      local tools = { GetTradeSkillTools(i) }
      for k = 1, #tools, 2 do
        if tools[k] and tools[k] ~= "" then table.insert(out, { name = tools[k], met = tools[k + 1] and true or false, place = IsPlace({ name = tools[k] }) }) end
      end
    end
  end
  return out
end

-- a recipe of the open profession making an item of this name (a tool a step needs: an
-- Arclight Spanner), as { spell, name, learned }, a learned one first; nil when none does
function api.ToolRecipe(name)
  if not (C_TradeSkillUI and C_TradeSkillUI.GetAllRecipeIDs and C_TradeSkillUI.GetRecipeInfo) then return nil end
  local ok, ids = pcall(C_TradeSkillUI.GetAllRecipeIDs)
  if not ok or type(ids) ~= "table" then return nil end
  local want, found = Spelt(name), nil
  for _, id in ipairs(ids) do
    local ok2, info = pcall(C_TradeSkillUI.GetRecipeInfo, id)
    if ok2 and type(info) == "table" and info.name and Spelt(info.name) == want then
      if info.learned then return { spell = id, name = info.name, learned = true } end
      found = found or { spell = id, name = info.name, learned = false }
    end
  end
  return found
end

-- an item's id from its name, when the client has met the item (else nil)
function api.ItemByName(name)
  local lookups = {}
  for _, f in pairs({ C_Item and C_Item.GetItemInfoInstant, GetItemInfoInstant, C_Item and C_Item.GetItemInfo, GetItemInfo }) do
    table.insert(lookups, f)                  -- pairs, not ipairs: a nil among them would end the list
  end
  for _, f in ipairs(lookups) do
    if f then
      local ok, a, b = pcall(f, name)
      if ok then
        if type(a) == "number" and a > 0 then return a end
        local id = type(b) == "string" and tonumber(b:match("item:(%d+)"))
        if id then return id end
      end
    end
  end
end

-- the names of what the recipe needs and the character lacks right now (Anvil, Blacksmith Hammer)
function api.Needs(spell)
  local out = {}
  for _, r in ipairs(api.Requirements(spell)) do if not r.met then table.insert(out, r.name) end end
  return out
end

-- a station the character stands at, by a recipe that needs it and has it met: noted as a place
local function NoteStations(spell)
  if not spell then return end
  for _, r in ipairs(api.Requirements(spell)) do
    if r.met and r.place then ns.NotePlace("station", r.name) end
  end
end

-- the recipe the panel has selected
local function Selected()
  local form = ProfessionsFrame and ProfessionsFrame.CraftingPage and ProfessionsFrame.CraftingPage.SchematicForm
  if form and form.GetRecipeInfo then
    local ok, info = pcall(form.GetRecipeInfo, form)
    if ok and type(info) == "table" then return info.recipeID end
  end
  if GetTradeSkillSelectionIndex and GetTradeSkillRecipeLink then
    local link = GetTradeSkillRecipeLink(GetTradeSkillSelectionIndex())
    return link and tonumber(link:match("enchant:(%d+)")) or nil
  end
end

function api.Craft(spell, n)
  if C_TradeSkillUI and C_TradeSkillUI.CraftRecipe then return (pcall(C_TradeSkillUI.CraftRecipe, spell, n)) end
  local i = OldIndex(spell)
  if i and DoTradeSkill then return (pcall(DoTradeSkill, i, n)) end
  return false
end

-- the repeat stopped. The craft under way ends and makes one more than the step: the client
-- refuses SpellStopCasting from an addon (11 Oct 2026), so the player's Escape is the one
-- thing that cancels it, and the chat says so at the stop
function api.Stop()
  if C_TradeSkillUI and C_TradeSkillUI.StopRecipeRepeat then return (pcall(C_TradeSkillUI.StopRecipeRepeat)) end
  if StopTradeSkillRepeat then return (pcall(StopTradeSkillRepeat)) end
  return false
end

-- ================================================================ what the click would do
-- the route's profession the panel shows: by skill line, else by name
local function ProfessionOf(house, open)
  local byName
  for _, plan in pairs(house.plans or {}) do
    if open.id and plan.skill_line == open.id then return plan.profession end
    if open.name and Spelt(open.name) == Spelt(plan.profession) then byName = plan.profession end
  end
  return byName
end

-- what is in the bags of everything the route handles (the bank does not count: a craft takes
-- from the bags), and with "Use what I already have first" (on by default) the bank too, as
-- counted when last open: what is there is not bought again, the button sends the character
-- for it (BankVerdict). The second table: what of it is in the bank
local function HaveFirst() return ns.Settings().haveFirst ~= false end
local function Bags(plan)
  local have, seen, banked = {}, {}, {}
  local bank = HaveFirst() and Char().items or nil
  local function Add(item)
    if item and not seen[item] then
      seen[item] = true
      have[item] = ns.inv.Count(item) or 0
      local row = bank and bank[item]
      if row and (row[2] or 0) > 0 then have[item], banked[item] = have[item] + row[2], row[2] end
    end
  end
  for _, s in ipairs(plan.steps or {}) do
    for _, u in ipairs(s.uses or {}) do Add(u[1]) end
    if s.makes then Add(s.makes[1]) end
  end
  for item, how in pairs(plan.made or {}) do
    Add(item)
    for _, u in ipairs(how[2] or {}) do Add(u[1]) end
  end
  local known = ns.ToolsKnown and ns.ToolsKnown()         -- what the tools take, from the bags too
  for _, t in pairs(known and known.made or {}) do
    for _, u in ipairs(t.uses or {}) do Add(u[1]) end
  end
  return ns.OwnTools and ns.OwnTools(have) or have, banked  -- a tool is had in the bank too
end

local function N(house, item) return (ns.ItemName(item, house.items and house.items[item] or ns.ToolName(item))) end

-- Whether a vendor sells the item: the route buys it from one (row[2]), or one sells it dearer
-- than the house did (row[3], since 7 Nov 2026). In game the vendor is the place to get it
-- either way: a sure, one-stop trip (a player sent to the house and a vendor for a dye came
-- back from the vendor with no need of the house, 7 Nov 2026); the house is said to be cheaper
local function VendorSells(plan, item)
  local row = ns.BuyRow(plan, item)
  return row ~= nil and (row[2] == "vendor" or type(row[3]) == "number")
end

-- where the route buys an item: { kind, what, item, title } for ns.NearestPlace
local function Seller(plan, item)
  if VendorSells(plan, item) then return { "vendor", nil, item, "Vendor" } end
  return { "auction", nil, nil, "Auctioneer" }
end

-- what a step needs bought, as Shop.lua lists it: { item, units (in all, from the bags), have,
-- source ("ah" | "vendor"), price (about, a unit), recipe (true for the recipe item) }
local function ShoppingOf(plan, nxt, tolearn)
  local out = {}
  for _, b in ipairs(nxt.buy) do
    local row = ns.BuyRow(plan, b[1])
    local have = ns.inv.Count(b[1]) or 0
    local catch = ns.Catches(plan, b[1])                 -- a fish of the fishing route: caught, not bought
    local vendor = not catch and VendorSells(plan, b[1])
    -- price: what one costs where it is got; `cheaper`: the house's price when the route found it lower there
    local price = row and not catch and ((vendor and type(row[3]) == "number") and row[3] or row[1]) or nil
    local cheaper = (row and vendor and type(row[3]) == "number" and row[1] < row[3]) and row[1] or nil
    table.insert(out, { item = b[1], units = b[2] + have, have = have, source = catch and "catch" or vendor and "vendor" or "ah", price = price, cheaper = cheaper })
  end
  -- the recipe is not offered again while it waits in the mail (bought by hand or with the Buy button) or the bank
  local banked = tolearn and (ns.inv.Char().items[tolearn.item] or {})[2] or 0
  if tolearn and tolearn.spell == nxt.spell and (ns.inv.Count(tolearn.item) or 0) == 0 and banked == 0
     and not (ns.inv.InMail and (ns.inv.InMail(tolearn.item) or 0) > 0) then
    table.insert(out, 1, { item = tolearn.item, units = 1, have = 0, source = VendorSells(plan, tolearn.item) and "vendor" or "ah", price = tolearn.cost, recipe = true })
  end
  return out
end

-- the list for the auction house, with no profession panel open: the profession the Make
-- button last served, which is the one opened last in the professions book (the /fwc
-- window's until one has been), at the character's skill. Opening another profession in the
-- book moves the list to that one, at once while the house is open (Refresh asks for it).
local function Shopping()
  local house = House()
  if not house then return {} end
  local c = Char()
  ns.inv.NoteSkills()                          -- what the character has goes by its skills, or by the panel open on it
  local open = api.Open()
  local function has(plan) return c.skills[plan.skill_line] or (open and not open.linked and open.id == plan.skill_line and open.rank) or nil end
  local making = c.making and ns.RouteFor(c.making)
  local profession = (making and has(making)) and c.making or (ns.OwnProfession and ns.OwnProfession())
  local plan = profession and ns.RouteFor(profession)
  if not plan then return {} end
  local skill = has(plan)
  if not skill then return {} end             -- a profession the character does not have: nothing to buy for it
  local bags = Bags(plan)
  local nxt = skill < plan.target and ns.NextCraft(plan, skill, bags, ns.BudgetReach and ns.BudgetReach(plan, skill, bags))
  if not nxt or nxt.blocked then return {} end
  local out = ShoppingOf(plan, nxt, c.tolearn)
  local t = c.tool
  local listed = false                                      -- the walk has it already, as a tool known (Tailor.lua)
  for _, e in ipairs(out) do if type(t) == "table" and e.item == t.item then listed = true end end
  if type(t) == "table" and t.item and not listed and (ns.inv.Count(t.item) or 0) == 0 then        -- the tool the step lacks, first
    table.insert(out, 1, { item = t.item, units = 1, have = 0, source = t.source or "ah", price = t.price })
  end
  out.title = ns.RecipeName(nxt.step) .. ", skill " .. nxt.from .. " to " .. nxt.to .. (nxt.capped and " (as far as the gold goes)" or "") .. ", needs"
  return out
end

-- the rank a cap ends, by the cap: what the trainer teaches next
local RANKS = { [75] = "Journeyman", [150] = "Expert", [225] = "Artisan" }
-- The ranks no trainer teaches, on Forever as in vanilla (wow-professions.com/forever, 8 Nov
-- 2026; a player at 150 first aid was told no trainer was known): Expert First Aid and Expert
-- Cooking are books two vendors sell (one a faction), Artisan First Aid and Artisan Cooking a
-- quest at a doctor or a cook. The seed has the sellers and the quest givers (places.py).
local RANKUPS = {
  ["first-aid"] = {
    [150] = { book = 16112, name = "Expert First Aid - Under Wraps", needs = 125,
              where = "Deneb Walker in Stromgarde Keep, Arathi Highlands (Alliance) or Balai Lok'Wein in Brackenwall Village, Dustwallow Marsh (Horde), for 1g" },
    [225] = { quest = "Triage", needs = 225, level = 35,
              where = "Doctor Gustaf VanHowzen in Theramore Isle, Dustwallow Marsh (Alliance) or Doctor Gregory Victor in Hammerfall, Arathi Highlands (Horde)" },
  },
  cooking = {
    [150] = { book = 16072, name = "Expert Cookbook", needs = 125,
              where = "Shandrina at Mystral Lake, Ashenvale (Alliance) or Wulan in Shadowprey Village, Desolace (Horde), for 1g" },
    [225] = { quest = "Clamlette Surprise", needs = 225, level = 35,
              where = "Dirge Quikcleave in Gadgetzan, Tanaris (both factions)" },
  },
}
local RANK_EARLY = 25                      -- the next rank is taught from this far below the cap

-- What the button does now: { text, tip = { lines }, spell, crafts, to, line }; spell nil
-- when the click can make nothing, and text says why. `given` = { open, profession } stands
-- in for the panel when none is open (the arrow with the window closed, Headless below)
-- the verdict when nothing can be made from the bags: what to buy, where, the list on a click
local function BuyVerdict(house, plan, nxt, step, tip, profession)
  local shopping = ShoppingOf(plan, nxt)
  shopping.title = ns.RecipeName(step) .. ", skill " .. nxt.from .. " to " .. nxt.to .. (nxt.capped and " (as far as the gold goes)" or "") .. ", needs"
  local ah, vendor, catch = {}, {}, {}
  for _, e in ipairs(shopping) do table.insert(e.source == "catch" and catch or e.source == "vendor" and vendor or ah, e) end
  -- the vendor first: the sure trip (what it sells never runs out; the house may have sold out)
  local text
  if #vendor == 1 and #ah == 0 then text = string.format("Buy %d %s from a vendor", vendor[1].units - vendor[1].have, N(house, vendor[1].item))
  elseif #vendor > 0 and #ah == 0 then text = string.format("Buy from a vendor: %d items", #vendor)
  elseif #ah == 1 and #vendor == 0 then text = string.format("Buy %d %s at the auction house", ah[1].units - ah[1].have, N(house, ah[1].item))
  elseif #vendor == 0 and #ah > 0 then text = string.format("Buy at the auction house: %d items", #ah)
  elseif #ah > 0 then text = string.format("Buy from a vendor (%d) and the auction house (%d)", #vendor, #ah)
  elseif #catch == 0 then text = "Buy at the auction house: 0 items" end
  -- the fish of the fishing route are caught: "Catch 45 Raw Longjaw Mud Snapper", after what a vendor sells when there is some
  if #catch > 0 then
    local fish = #catch == 1 and string.format("%d %s", catch[1].units - catch[1].have, N(house, catch[1].item)) or string.format("%d kinds of fish", #catch)
    text = text and (text .. ", and catch " .. fish) or ("Catch " .. fish)
  end
  table.insert(tip, "Needs:")
  for _, e in ipairs(shopping) do
    if e.source == "catch" then
      local where = ns.CatchSpots(plan, e.item)
      table.insert(tip, string.format("  %d %s (have %d): catch%s", e.units - e.have, N(house, e.item), e.have, where and (", " .. where) or ""))
    else
      table.insert(tip, string.format("  %d %s (have %d)%s, %s", e.units - e.have, N(house, e.item), e.have,
        e.price and (", about " .. ns.Money(e.price * (e.units - e.have))) or "",
        e.source == "vendor" and ("from a vendor" .. (e.cheaper and string.format(" (the auction house had it for %s each)", ns.Money(e.cheaper)) or ""))
          or "at the auction house"))
    end
  end
  if #catch > 0 then table.insert(tip, ns.CATCH_NOTE) end
  table.insert(tip, "Click: the shopping list.")
  -- the note under the arrow: each item and where it is got, the vendor's first; a fish: its zones
  local parts, ordered = {}, {}
  for _, e in ipairs(vendor) do table.insert(ordered, e) end
  for _, e in ipairs(ah) do table.insert(ordered, e) end
  for _, e in ipairs(catch) do table.insert(ordered, e) end
  for i, e in ipairs(ordered) do
    if i > 3 then table.insert(parts, string.format("+%d more", #ordered - 3)); break end
    table.insert(parts, string.format("%d %s: %s", e.units - e.have, N(house, e.item),
      e.source == "catch" and (ns.CatchSpots(plan, e.item, true) or "catch") or e.source == "vendor" and "vendor" or "AH"))
  end
  -- the arrow: the nearest of the sources, a vendor seen or seeded selling a vendor item or the
  -- auctioneer; a vendor item nobody was seen selling leaves the house to point at
  local best, bestD, bestHere
  local function consider(place)
    local p, d, here = ns.NearestPlace(place[1], place[2], place[3])
    if not p then return end
    if not best or (here and not bestHere) or ((here or false) == (bestHere or false) and d and (not bestD or d < bestD)) then best, bestD, bestHere = place, d, here end
  end
  for _, e in ipairs(vendor) do consider(Seller(plan, e.item)) end
  if #ah > 0 then consider({ "auction", nil, nil, "Auctioneer" }) end
  local place = best or (#vendor > 0 and Seller(plan, vendor[1].item)) or (#ah > 0 and Seller(plan, ah[1].item)) or nil
  local v = { text = text, note = table.concat(parts, ", "), tip = tip, shopping = shopping, place = place, profession = profession }
  if not place then       -- only fish to catch: nothing to walk to, the arrow says the words and the zones (it knows no map for a fishing zone)
    v.show, v.catch = true, true
    table.insert(tip, #tip, "No arrow for fishing: the zones above are the Classic-era world's names, and the addon has no spot to point at. Fish where you can.")
  end
  return v
end

-- What the step needs that the bank holds (with "Use what I already have first"): taken from
-- the bank before anything is bought (what is there is off the list already). `banked` is
-- Bags' second table; the bags are walked alone to see what of it the step needs. nil when
-- nothing waits there.
local function BankVerdict(house, plan, nxt, banked, tip, profession)
  if not next(banked) then return nil end
  local bags = {}
  for item, n in pairs(Bags(plan)) do bags[item] = n - (banked[item] or 0) end
  local walk = ns.Tailor(plan, nxt.from, bags, nxt.to)
  local waiting = {}
  for item, units in pairs(walk.buy) do
    if (banked[item] or 0) > 0 then table.insert(waiting, { item = item, units = math.min(units, banked[item]) }) end
  end
  if #waiting == 0 then return nil end
  table.sort(waiting, function(a, b) if a.units ~= b.units then return a.units > b.units end return a.item < b.item end)
  local parts = {}
  for i, w in ipairs(waiting) do
    if i > 3 then table.insert(parts, string.format("+%d more", #waiting - 3)); break end
    table.insert(parts, string.format("%d %s: bank", w.units, N(house, w.item)))
  end
  table.insert(tip, "In your bank (as counted when it was last open):")
  for _, w in ipairs(waiting) do table.insert(tip, string.format("  %d %s", w.units, N(house, w.item))) end
  local text = #waiting == 1 and string.format("Take %d %s from the bank", waiting[1].units, N(house, waiting[1].item))
    or string.format("Take from the bank: %d items", #waiting)
  return { text = text, note = table.concat(parts, ", "), tip = tip, show = true, bank = true, profession = profession }
end

-- What the step needs that waits in the mail (seen in the inbox, or bought at the auction
-- house this visit, which the game delivers by mail): the mailbox first, the nearest one,
-- before anything is bought again. `scroll`: the recipe the route buys
-- for this step, named with the rest when it waits there too (a bought recipe is mailed like
-- anything else). nil when nothing waits.
local function MailVerdict(house, plan, nxt, step, tip, profession, scroll)
  if not ns.inv.InMail then return nil end
  local waiting, rest = {}, 0
  if scroll and (ns.inv.Count(scroll) or 0) == 0 and (ns.inv.InMail(scroll) or 0) > 0 then
    table.insert(waiting, { item = scroll, units = 1, recipe = true })
  end
  for _, b in ipairs(nxt.buy) do
    local n = ns.inv.InMail(b[1]) or 0
    if n > 0 then table.insert(waiting, { item = b[1], units = math.min(n, b[2]) }) else rest = rest + 1 end
  end
  if #waiting == 0 then return nil end
  local function Name(w) return w.recipe and N(house, w.item) or string.format("%d %s", w.units, N(house, w.item)) end
  local parts = {}
  for i, w in ipairs(waiting) do
    if i > 3 then table.insert(parts, string.format("+%d more", #waiting - 3)); break end
    table.insert(parts, Name(w) .. ": mailbox")
  end
  table.insert(tip, "In the mail (seen in the inbox, or bought at the auction house):")
  for _, w in ipairs(waiting) do table.insert(tip, "  " .. Name(w)) end
  if rest > 0 then table.insert(tip, string.format("%d more item%s to buy after the mailbox.", rest, rest == 1 and "" or "s")) end
  if waiting[1].recipe then table.insert(tip, "Then learn the recipe from it.") end
  local text = #waiting == 1 and ("Collect " .. Name(waiting[1]) .. " from the mailbox")
    or string.format("Collect from the mailbox: %d items", #waiting)
  return { text = text, note = table.concat(parts, ", "), tip = tip, place = { "mailbox", nil, nil, "Mailbox" }, profession = profession }
end

-- The recipe scroll the route buys, once it is had somewhere: in the bags it is used (the
-- recipe is learned from it; no place, nothing to walk to); in the mail or the bank it is
-- fetched first. nil when it is nowhere: it is to be bought.
local function ScrollVerdict(house, plan, nxt, step, tip, profession, scroll)
  local name = N(house, scroll)
  local v
  if (ns.inv.Count(scroll) or 0) > 0 then
    table.insert(tip, string.format("%s is in your bags: use it to learn the recipe.", name))
    v = { text = string.format("Learn %s: use %s in your bags", ns.RecipeName(step), name), tip = tip, profession = profession, show = true }
  elseif ns.inv.InMail and (ns.inv.InMail(scroll) or 0) > 0 then
    v = MailVerdict(house, plan, nxt, step, tip, profession, scroll)
  elseif ((ns.inv.Char().items[scroll] or {})[2] or 0) > 0 then
    table.insert(tip, "In your bank (as counted when it was last open):")
    table.insert(tip, "  " .. name)
    v = { text = string.format("Take %s from the bank", name), note = name .. ": bank", tip = tip, show = true, bank = true, profession = profession }
  end
  if v then v.learn = nxt.spell end
  return v
end

-- A recipe to learn and reagents to buy are two trips: the nearer one first. The house, when
-- it is open, or nearer than the trainer, or on this map when the trainer is not; the trainer
-- otherwise, and when there is nothing to buy or no seller known (running between the house
-- and the trainer ate the time, 12 Oct 2026)
local function NearerFirst(profession, plan, nxt, upto, need, spell)
  if #nxt.buy == 0 then return "trainer" end
  local first                                             -- a fish is caught, not bought: no seller to compare with
  for _, b in ipairs(nxt.buy) do
    if not ns.Catches(plan, b[1]) then first = b[1]; break end
  end
  if not first then return "trainer" end
  if ns.scanner and ns.scanner.Open() then return "buy" end
  local seller = Seller(plan, first)
  local s, sd, shere = ns.NearestPlace(seller[1], seller[2], seller[3])
  if not s then return "trainer" end
  local t, td, there = ns.NearestPlace("trainer", profession, nil, upto, need, spell)
  if not t then return "buy" end
  if shere and not there then return "buy" end
  if there and not shere then return "trainer" end
  if sd and td and sd < td then return "buy" end
  return "trainer"
end

-- ================================================================ the tools the route needs
-- The client says what a recipe of the open profession needs beside its reagents (a Runed
-- Copper Rod: GetRecipeRequirements, a tool rather than a place) and what a recipe takes
-- (GetRecipeSchematic); the routes' documents say neither. With the panel open on the route's
-- profession, each recipe of the route is asked once a session, and each tool named is looked
-- up once: the recipe of the profession that makes it (api.ToolRecipe), what that takes and
-- makes, and the tools it needs in turn. Kept in FWCS_DB.__tools (Tailor.lua says how), which
-- the route's walk reads: the shopping list then has what a tool takes before the step that
-- needs it, unless the character has the tool (10 Nov 2026). Places (an anvil, a camp object
-- the route makes) are not tools here. Cost: a call per recipe of the route, the first time
-- the panel shows it in a session; a look through the profession's recipes per tool named.
local asked, resolved = {}, {}           -- this session: the recipes asked, the tools looked up
local function Tools()
  FWCS_DB.__tools = FWCS_DB.__tools or {}
  local k = FWCS_DB.__tools
  k.spells, k.made, k.v = k.spells or {}, k.made or {}, k.v or 0
  return k
end

-- what a recipe takes as the client's schematic has it ({ {item, units}, ... }, its basic
-- reagents) and the item it makes; nil on a client without schematics
local function Schematic(spell)
  if not (C_TradeSkillUI and C_TradeSkillUI.GetRecipeSchematic) then return nil end
  local ok, s = pcall(C_TradeSkillUI.GetRecipeSchematic, spell, false)
  if not ok or type(s) ~= "table" then return nil end
  local basic = Enum and Enum.CraftingReagentType and Enum.CraftingReagentType.Basic
  local uses = {}
  for _, slot in ipairs(s.reagentSlotSchematics or {}) do
    local r = type(slot) == "table" and type(slot.reagents) == "table" and slot.reagents[1]
    local n = type(slot) == "table" and tonumber(slot.quantityRequired) or 0
    if type(r) == "table" and tonumber(r.itemID) and n > 0 and (basic == nil or slot.reagentType == nil or slot.reagentType == basic) then
      table.insert(uses, { tonumber(r.itemID), n })
    end
  end
  return uses, tonumber(s.outputItemID)
end

local function Same(a, b)
  if #a ~= #(b or {}) then return false end
  for i = 1, #a do if a[i] ~= b[i] then return false end end
  return true
end

-- a tool's record as words, to tell whether a look-up changed it
local function Said(t)
  local parts = { tostring(t.item), tostring(t.spell) }
  for _, u in ipairs(t.uses or {}) do table.insert(parts, u[1] .. "x" .. u[2]) end
  for _, n in ipairs(t.needs or {}) do table.insert(parts, n) end
  return table.concat(parts, ",")
end

function ns.LearnTools(plan)
  if not (plan and C_TradeSkillUI and C_TradeSkillUI.GetRecipeRequirements and C_TradeSkillUI.GetRecipeInfo) then return end
  local k, changed
  local function Resolve(name, depth)
    local key = Spelt(name)
    if (resolved[key] or 0) >= 3 or depth > 3 then return end
    k = k or Tools()
    local t = k.made[key] or { name = name }
    local was = k.made[key] and Said(t)
    local recipe = api.ToolRecipe(name)
    if recipe then
      local uses, item = Schematic(recipe.spell)
      t.spell = recipe.spell
      if uses and #uses > 0 then t.uses = uses end
      t.item = item or t.item
      local needs = {}
      for _, r in ipairs(api.Requirements(recipe.spell)) do
        if not r.place then table.insert(needs, r.name); Resolve(r.name, depth + 1) end
      end
      t.needs = #needs > 0 and needs or nil
    end
    t.item = t.item or api.ItemByName(name)
    resolved[key] = t.item and 3 or (resolved[key] or 0) + 1   -- an item the client has not met yet: asked again, twice
    k.made[key] = t
    if Said(t) ~= was then changed = true end
  end
  local spells = {}
  for _, s in ipairs(plan.steps or {}) do
    table.insert(spells, s.spell)
    for _, a in ipairs(s.alt or {}) do table.insert(spells, a.spell) end
  end
  for _, s in ipairs(plan.source and plan.source.steps or {}) do
    for _, a in ipairs(s.alt or {}) do table.insert(spells, a.spell) end
  end
  for _, spell in ipairs(spells) do
    if spell and not asked[spell] then
      local ok, info = pcall(C_TradeSkillUI.GetRecipeInfo, spell)
      if ok and type(info) == "table" then                  -- the client has the recipe's data: its answer counts
        asked[spell] = true
        local names = {}
        for _, r in ipairs(api.Requirements(spell)) do
          if not r.place then
            table.insert(names, r.name)
            Resolve(r.name, 0)
            local t = (k or Tools()).made[Spelt(r.name)]
            -- met with none counted: a better tool stands in for it (kept, so the list does not ask for it)
            local stand = (r.met and t and t.item and (ns.inv.Count(t.item) or 0) == 0) or nil
            if t and t.met ~= stand then t.met = stand; changed = true end
          end
        end
        k = k or Tools()
        if #names > 0 and not Same(names, k.spells[spell]) then k.spells[spell] = names; changed = true end   -- an empty answer never clears one
      end
    end
  end
  if changed then
    k.v = k.v + 1
    if ns.inv.Retrack then ns.inv.Retrack() end              -- the tools and what they take are counted from now on
  end
end

local switched                           -- the book opened another profession: the shopping list follows
local asideOf                            -- the note the verdict carries under the arrow (the next rank to train, the other trip)
local usingOf                            -- "Using your 40 Briarthorn": the step's recipe chosen for what the character has

-- The colour the client gives a recipe at the character's skill: "optimal" (orange), "medium"
-- (yellow), "easy" (green), "trivial" (grey), "difficult" (red: not yet); nil when it cannot say.
-- The client's word beats the route's tables (Forever moves recipe levels by hotfix)
local COLOURS = { [0] = "optimal", [1] = "medium", [2] = "easy", [3] = "trivial" }
local KINDS = { optimal = true, medium = true, easy = true, trivial = true, difficult = true }
function api.Colour(spell)
  if C_TradeSkillUI and C_TradeSkillUI.GetRecipeInfo then
    local ok, info = pcall(C_TradeSkillUI.GetRecipeInfo, spell)
    if ok and type(info) == "table" and info.relativeDifficulty ~= nil then return COLOURS[info.relativeDifficulty] end
  end
  if GetTradeSkillInfo then
    local i = OldIndex(spell)
    if i then
      local _, kind = GetTradeSkillInfo(i)
      if KINDS[kind] then return kind end
    end
  end
  return nil
end

-- A run of a vouched recipe (ns.StandIns) from `skill`, up to `to`: the crafts it takes (about,
-- where a craft may give no point) and the skill it stops at, never past one where its chance is
-- 0. Where the route says nothing of its chance (e.now nil), the client's colour does: orange or
-- yellow, one craft a point up to `to` (yellow lasts far longer than a run from the bags gains:
-- it turns green, then grey, before a craft is wasted); green, one craft a click (the next could
-- be grey, and nothing says how far off that is); grey, red or no word, none. Grey or red in the
-- client is none whatever the route's tables say
local function Run(e, colour, skill, to)
  if colour == "trivial" or colour == "difficult" then return 0, skill end
  if e.now == nil then
    if colour == "optimal" or colour == "medium" then return to - skill, to end
    if colour == "easy" then return 1, math.min(to, skill + 1) end
    return 0, skill
  end
  local crafts, at = 0, skill
  while at < to do
    local c = e.chance(at)
    if not c or c <= 0 then break end
    crafts, at = crafts + 1 / c, at + 1
  end
  return math.ceil(crafts - 0.001), at
end

-- A run from the bags of recipe `c` ({ spell, uses, name? }), `crafts` at most and stopping at
-- skill `stop` (Run): the Make verdict, with `said` (usingOf, name) the tooltip's line of why;
-- "Needs <station>" when the recipe needs one the character is not at; nil when the bags hold no
-- craft of it or a tool it needs is lacking. `low`: the run's chance is the client's green
local function Offer(house, plan, nxt, c, crafts, stop, from, banked, tip, profession, said, low)
  local can = crafts
  for _, u in ipairs(c.uses) do can = math.min(can, math.floor((ns.inv.Count(u[1]) or 0) / u[2])) end
  if can <= 0 then return nil end
  local needs, place = {}, nil
  for _, r in ipairs(api.Requirements(c.spell)) do
    if not r.met then
      if r.place and not api.ToolRecipe(r.name) then
        table.insert(needs, r.name)
        place = place or { "station", r.name, nil, r.name }
      else
        return nil                         -- a tool lacking: no craft from the bags
      end
    end
  end
  local name = c.name or ns.RecipeName(c)
  local mine = {}
  for _, u in ipairs(c.uses) do table.insert(mine, { u[1], u[2] * can }) end
  table.sort(mine, function(a, b) if a[2] ~= b[2] then return a[2] > b[2] end return a[1] < b[1] end)
  usingOf = ns.UsingText({ mine = mine }, function(item) return N(house, item) end)     -- the arrow's note: this run's, not the stretch's
  table.insert(tip, said(usingOf, name))
  if crafts > stop - from then
    table.insert(tip, string.format("Not every craft gives a point here: about %d crafts for %d points.", crafts, stop - from))
  elseif low then
    table.insert(tip, "Green in the panel: one at a time, until it stops giving points.")
  end
  local later = {}                         -- what of the stretch's own recipe waits in the bank: fetched after this run
  for _, u in ipairs(nxt.uses or {}) do
    if (banked[u[1]] or 0) > 0 then table.insert(later, string.format("%d %s", banked[u[1]], N(house, u[1]))) end
  end
  if #later > 0 then table.insert(tip, "In your bank for later: " .. table.concat(later, ", ") .. ".") end
  if #needs > 0 then
    table.insert(tip, "The recipe needs " .. table.concat(needs, ", ") .. ".")
    return { text = "Needs " .. table.concat(needs, ", "), tip = tip, place = place, recipe = c.spell, profession = profession }
  end
  table.insert(tip, string.format("Click: makes %d, stopping at skill %d.", can, stop))
  return { text = string.format("Make %d %s", can, name), tip = tip, spell = c.spell, crafts = can, to = stop, line = plan.skill_line, profession = profession }
end

-- ================================================================ known recipes, off the route
-- The recipes of a profession the character knows, as the profession panel lists them: read
-- while the panel is open, and kept in the character's saved record so that the same answer
-- holds with the panel closed and after a reload (with the panel open the button made cakes from
-- the bags; closed, the arrow went back to buying the recipe for Clam Chowder, 14 Nov 2026).
--
-- WHAT THIS GATHERS: with the panel open on a profession, every recipe of it the character has
-- learned, as the client shows it: its spell, name and colour at the character's skill, what it
-- takes, and whether it has a cooldown. Kept in FWCS_DB.__chars["<house's realm>|<name>"].learned
-- (Inventory.lua's record of the character), on this computer, NEVER sent: the helper reads of
-- __chars only names, houses, factions, items and skills (fwchelper/plans.py, characters), and
-- sends scans and vendors alone. Why: to offer, from the bags, a recipe off the route that still
-- gives points, with the panel closed too. The shape, one profession by its skill line:
--   learned[skill line] = { skill = the skill it was seen at, t = when,
--     list = { { spell, colour ("optimal", "medium", "easy", "trivial"), name,
--                uses = { { item, units }, ... }, cd = true when it has a cooldown }, ... } }
-- written again whole at each look (once per change: ns.HaveGen, Tailor.lua), a profession the
-- character no longer has dropped then. Cost: a call or two per recipe of the profession, once
-- per change while the panel is open.
--
-- Cooldowns: C_TradeSkillUI.GetRecipeCooldown says only that a recipe is cooling down (and
-- whether it is a daily one or has charges); GetSpellBaseCooldown, where the client has it, says
-- a recipe has a cooldown at all; the old panel's GetTradeSkillCooldown says the time left. A
-- recipe any of them marks is noted cd, and so is a transmute by its name, whatever they say.
local function Cooling(spell, oldIndex, name)
  if (name or ""):match("^Transmute") then return true end
  if C_TradeSkillUI and C_TradeSkillUI.GetRecipeCooldown then
    local ok, left, daily, _, most = pcall(C_TradeSkillUI.GetRecipeCooldown, spell)
    if ok and ((tonumber(left) or 0) > 0 or daily == true or (tonumber(most) or 0) > 0) then return true end
  end
  if GetSpellBaseCooldown then
    local ok, ms = pcall(GetSpellBaseCooldown, spell)
    if ok and (tonumber(ms) or 0) > 0 then return true end
  end
  if oldIndex and GetTradeSkillCooldown then
    local ok, left = pcall(GetTradeSkillCooldown, oldIndex)
    if ok and (tonumber(left) or 0) > 0 then return true end
  end
  return false
end

-- the panel's list, read now: { { spell, colour, name, uses, cd }, ... } of the learned recipes;
-- nil when the client gives none
local function PanelList()
  local out
  if C_TradeSkillUI and C_TradeSkillUI.GetAllRecipeIDs and C_TradeSkillUI.GetRecipeInfo then
    local ok, ids = pcall(C_TradeSkillUI.GetAllRecipeIDs)
    for _, id in ipairs(ok and type(ids) == "table" and ids or {}) do
      local ok2, info = pcall(C_TradeSkillUI.GetRecipeInfo, id)
      if ok2 and type(info) == "table" and info.learned and COLOURS[info.relativeDifficulty] then
        out = out or {}
        table.insert(out, { spell = id, colour = COLOURS[info.relativeDifficulty], name = info.name, uses = Schematic(id) or {},
                            cd = Cooling(id, nil, info.name) or nil })
      end
    end
  elseif GetNumTradeSkills and GetTradeSkillInfo and GetTradeSkillRecipeLink and GetTradeSkillNumReagents and GetTradeSkillReagentInfo and GetTradeSkillReagentItemLink then
    for i = 1, GetNumTradeSkills() or 0 do
      local name, kind = GetTradeSkillInfo(i)
      local link = KINDS[kind] and kind ~= "difficult" and GetTradeSkillRecipeLink(i)
      local spell = link and tonumber(link:match("enchant:(%d+)"))
      if spell then
        local uses = {}
        for r = 1, GetTradeSkillNumReagents(i) or 0 do
          local _, _, count = GetTradeSkillReagentInfo(i, r)
          local rlink = GetTradeSkillReagentItemLink(i, r)
          local item = rlink and tonumber(rlink:match("item:(%d+)"))
          if item and (tonumber(count) or 0) > 0 then table.insert(uses, { item, tonumber(count) }) end
        end
        out = out or {}
        table.insert(out, { spell = spell, colour = kind, name = name, uses = uses, cd = Cooling(spell, i, name) or nil })
      end
    end
  end
  return out
end

-- The panel open on the profession of skill line `line`, at `skill`: its list read (once per
-- change) and kept as the character's record of it
local seenGen, seenOf
local function NoteRecipes(line, skill)
  local gen = ns.HaveGen and ns.HaveGen() or 0
  if not line or (seenGen == gen and seenOf == line) then return end
  local list = PanelList()
  if not list then return end
  seenGen, seenOf = gen, line
  local c = Char()
  c.learned = c.learned or {}
  c.learned[line] = { skill = skill, t = time and time() or 0, list = list }
  if ns.inv.SkillsReadable() then                         -- a profession the character no longer has: its record goes
    for l in pairs(c.learned) do if not c.skills[l] then c.learned[l] = nil end end
  end
end

-- The recipes the fallback may offer: the character's record of the profession of skill line
-- `line` (just read, with the panel open), orange and yellow only (green, grey and red never),
-- none with a cooldown. Seen at another skill than `skill`: a recipe is offered only where the
-- route's numbers show it still at least yellow there (its `at`, from any stretch that lists it
-- as a next-best: below the green), at the colour they give; else it is unknown, and left out.
-- nil when there is no record (the panel never opened on the profession on this computer)
local function KnownRecipes(plan, line, skill)
  local rec = line and (Char().learned or {})[line]
  if type(rec) ~= "table" or type(rec.list) ~= "table" then return nil end
  local ats
  local out = {}
  for _, r in ipairs(rec.list) do
    local colour = r.colour
    if rec.skill ~= skill then
      if not ats then
        ats = {}
        for _, s in ipairs((plan.source and plan.source.steps) or plan.steps or {}) do
          for _, a in ipairs(s.alt or {}) do if a.spell and a.at then ats[a.spell] = ats[a.spell] or a.at end end
        end
      end
      local at = ats[r.spell]
      colour = at and skill >= at[1] and skill < at[3] and (skill < at[2] and "optimal" or "medium") or nil
    end
    if (colour == "optimal" or colour == "medium") and not r.cd and type(r.uses) == "table" and #r.uses > 0 then
      table.insert(out, { spell = r.spell, name = r.name, colour = colour, uses = r.uses })
    end
  end
  return out
end

-- With the panel closed, the record stands in for what the client would say of a recipe there:
-- learned (a recipe in it is), and its colour (at the skill it was seen at only). Set by the
-- verdict for the profession it serves; nil with the panel open, where the client answers
local memory
local function Remembered(spell)
  if not memory then return nil end
  if not memory.by then
    memory.by = {}
    for _, r in ipairs(memory.rec.list or {}) do memory.by[r.spell] = r end
  end
  return memory.by[spell]
end
-- learned: the client's yes, or the record's (a recipe once learned stays learned; the record
-- never turns the client's yes into a no)
local function Learned(spell)
  local live = api.Learned(spell)
  if live ~= true and Remembered(spell) then return true end
  return live
end
-- the colour: with the panel closed the record's, while it was seen at this skill; else the client's
local function Colour(spell)
  local r = memory and memory.same and Remembered(spell)
  if r then return r.colour end
  return api.Colour(spell)
end

-- What the route still needs that a known recipe off the route must not burn: every item the
-- stretches from the current one on use, and what those are made of where the route makes them
-- (plan.made). Not reserved: what the route buys from a vendor (VendorSells: a vendor's stock is
-- cheap and never runs out, so a cake's Hot Spices are bought again for a later stretch at a
-- vendor's price, where reserving them would keep the cake from the bags for a few coppers'
-- worth of spices). Simple and on the safe side: an item the route uses is skipped whatever the
-- counts, rather than weighed against what a later stretch would buy anyway
local function Reserved(plan, skill)
  local out = {}
  local function Add(item, depth)
    if out[item] or VendorSells(plan, item) then return end
    out[item] = true
    local how = plan.made and plan.made[item]
    if how and depth < 4 then
      for _, u in ipairs(how[2] or {}) do Add(u[1], depth + 1) end
    end
  end
  for _, s in ipairs(plan.steps or {}) do
    if s.to > skill then
      for _, u in ipairs(s.uses or {}) do Add(u[1], 0) end
    end
  end
  return out
end

-- The bags first. Nothing of the stretch's chosen recipe (nor of what it makes on the way) can
-- be made from the bags, or that recipe is not learned yet: before the trainer, a recipe to buy,
-- the bank, the mailbox or a seller, the first recipe the planner vouches for (ns.StandIns,
-- Tailor.lua: the stretch's own and its next-best, then those of the stretches before it) that
-- the bags alone hold a craft of is made, as many as they hold, up to the stretch's end (the
-- gold's cut, nxt.to, included) or the skill where it stops giving points, whichever is first:
-- a whole run of one recipe, never a craft of each in turn. Counted from the bags alone, as Can
-- is: what the bank holds of it does not make a craft now. One the character does not know (a
-- trainer's walk, or a scroll to buy) or that lacks a tool is no craft from the bags, and is
-- passed over; a station it needs is said as for the stretch's own. A green craft is allowed
-- (the reagents are the player's own), but no point a craft is promised: the tooltip says about
-- how many crafts.
--
-- Then, nothing the route vouches for being in the bags: any recipe of the profession the
-- character knows that the panel shows (or showed, at this skill: the character's record, so the
-- answer is the same with the panel closed and after a reload) orange or yellow and the bags hold
-- a craft of (KnownRecipes), none that uses what the route still needs (Reserved). Orange before
-- yellow, then the one the bags make the most crafts of, then by name; a run up to the stretch's
-- end, the verdict asked again after it (a player with the fins and the legs for soups and cakes
-- in the bags was sent to buy the recipe for Clam Chowder, a route without either, 14 Nov 2026).
-- Once the bags hold no craft of any, the verdict goes on as before (the last fin in the bank
-- fetched for the soup, once the cakes are made). nil when none is to be made.
local function BagsVerdict(house, plan, nxt, skill, banked, tip, profession)
  local list = ns.StandIns and ns.StandIns(plan, skill)
  if not list then return nil end        -- the box off (the route's own recipes), or a stretch whose product a later one uses
  local from = math.max(skill, nxt.from)
  local seen = { [nxt.spell or 0] = true }
  for _, e in ipairs(list) do
    local c = e.rec
    seen[c.spell] = true
    if c.spell ~= nxt.spell and c.uses and #c.uses > 0 and Learned(c.spell) ~= false then
      local colour = Colour(c.spell)
      local crafts, stop = Run(e, colour, from, nxt.to)
      local v = crafts > 0 and Offer(house, plan, nxt, c, crafts, stop, from, banked, tip, profession, function(using, name)
        return e.here and string.format("%s: %s stands in for %s from your bags, nothing to fetch or buy.", using, name, ns.RecipeName(nxt.step))
          or string.format("%s: %s, from an earlier stretch, still gives points: made from your bags, nothing to fetch or buy.", using, name)
      end, e.now == nil and colour == "easy")
      if v then return v end
    end
  end
  local known = KnownRecipes(plan, plan.skill_line, skill)
  if not known then                      -- never seen: said once here, the verdict going on as before
    table.insert(tip, string.format("Open your %s window once so the addon can see what your bags can make.", ns.Title(profession)))
    return nil
  end
  if #known == 0 then return nil end
  local reserved = Reserved(plan, skill)
  local offers = {}
  for _, c in ipairs(known) do
    local free = not seen[c.spell]
    for _, u in ipairs(c.uses) do if reserved[u[1]] then free = false end end
    if free then
      local can = math.huge
      for _, u in ipairs(c.uses) do can = math.min(can, math.floor((ns.inv.Count(u[1]) or 0) / u[2])) end
      if can > 0 then table.insert(offers, { c = c, can = can }) end
    end
  end
  table.sort(offers, function(a, b)
    if a.c.colour ~= b.c.colour then return a.c.colour == "optimal" end
    if a.can ~= b.can then return a.can > b.can end
    return (a.c.name or "") < (b.c.name or "")
  end)
  for _, o in ipairs(offers) do
    local crafts, stop = Run({}, o.c.colour, from, nxt.to)
    local v = crafts > 0 and Offer(house, plan, nxt, o.c, crafts, stop, from, banked, tip, profession, function(using, name)
      return string.format("%s: %s is not on the route but still gives points: made from your bags, nothing to fetch or buy.", using, name)
    end)
    if v then return v end
  end
  return nil
end

-- The stretch's recipe is not learned yet: a vouched recipe the bags hold a craft of is made
-- first (BagsVerdict), and the trip for the recipe becomes the arrow's note, as the other trip of
-- a two-trip verdict is (a player was sent to buy the recipe for Clam Chowder with 3 soups and 4
-- cakes' worth in the bags, 14 Nov 2026). The trip: the recipe bought where the route buys it,
-- collected from the mailbox when it waits there, taken from the bank (a tooltip line: the arrow
-- knows no bank), or learned at the trainer. A scroll already in the bags is learned first, one
-- click and no trip; a recipe the character's level cannot learn yet is said in the tooltip, no
-- trip offered. nil when the bags make nothing: the recipe's own verdicts follow, as before
local function BagsBeforeLearning(house, plan, nxt, skill, banked, tip, profession, learn, trainer)
  if learn and (ns.inv.Count(learn[1]) or 0) > 0 then return nil end
  local made = BagsVerdict(house, plan, nxt, skill, banked, tip, profession)
  if not made then return nil end
  local recipe = ns.RecipeName(nxt.step)
  local need = learn and ((ns.NoteRecipeLevel and ns.NoteRecipeLevel(learn[1])) or learn[3])
  local mine = UnitLevel and UnitLevel("player")
  local line
  if need and mine and need > mine then
    line = string.format("%s asks for character level %d: learned later.", recipe, need)
  elseif learn and ns.inv.InMail and (ns.inv.InMail(learn[1]) or 0) > 0 then
    asideOf = { text = "Then collect " .. N(house, learn[1]) .. " from the mailbox", place = { "mailbox", nil, nil, "Mailbox" } }
  elseif learn and ((Char().items[learn[1]] or {})[2] or 0) > 0 then
    line = string.format("Then take %s from the bank and learn %s.", N(house, learn[1]), recipe)
  elseif learn then
    Char().tolearn = { spell = nxt.spell, item = learn[1], cost = learn[2] }       -- the list at the house still offers it
    asideOf = { text = "Then buy the recipe for " .. recipe, place = Seller(plan, learn[1]) }
  else
    asideOf = { text = "Then learn " .. recipe .. " at the trainer", place = trainer }
  end
  if asideOf and not line then line = asideOf.text .. " (the arrow's note)." end
  table.insert(made.tip, #made.tip, line)                    -- before "Click: ..."
  return made
end

local function VerdictOf(given)
  local house = House()
  if not house then
    return { text = "No routes for this realm yet", tip = { "The helper fetches them: see /fwc." } }
  end
  local open = given and given.open or api.Open()
  if not open then
    return { text = "No profession open", tip = { "Open a profession's recipes." }, idle = true }
  end
  local profession = given and given.profession or ProfessionOf(house, open)
  local plan = profession and ns.RouteFor(profession)
  if not plan then
    return { text = "No route for this profession", tip = { "The site has no route for the profession this panel shows." }, idle = true }
  end
  -- a window on recipes that are not this character's: another player's profession linked in
  -- chat, a guild's, or a profession the character does not have. Nothing is made, bought or
  -- trained for it: the route follows the character's own professions only (a player was sent
  -- to train enchanting, which he did not have, 8 Nov 2026)
  if not given then
    ns.inv.NoteSkills()
    if open.linked or (ns.inv.SkillsReadable() and not Char().skills[plan.skill_line]) then
      return { text = "Not one of your professions", idle = true,
               tip = { string.format("This window shows %s recipes that are not this character's: another player's, or a profession it does not have. The route, the arrow and the shopping list follow your own professions.", ns.Title(profession)) } }
    end
  end
  if not given and Char().making ~= profession then      -- the profession opened in the book: the list's and the arrow's
    Char().making = profession
    switched = true
  end
  local skill = open.rank or Char().skills[plan.skill_line] or plan.start
  local tip = { string.format("%s route, skill %d.", ns.Title(profession), skill) }
  if not given then pcall(ns.LearnTools, plan) end      -- the panel open on the route's profession: the tools its recipes need
  local bags, banked = Bags(plan)
  -- the panel open on the route's profession: what it lists is kept (NoteRecipes); closed, the
  -- character's record of it answers for the client (memory: Learned, Colour, KnownRecipes)
  memory = nil
  if not given then
    pcall(NoteRecipes, plan.skill_line, skill)
  else
    local rec = (Char().learned or {})[plan.skill_line]
    if type(rec) == "table" and type(rec.list) == "table" then memory = { rec = rec, same = rec.skill == skill } end
  end
  local nxt = skill < plan.target and ns.NextCraft(plan, skill, bags, ns.BudgetReach and ns.BudgetReach(plan, skill, bags))
  if not nxt then
    return { text = string.format("Route done at skill %d", skill), tip = { tip[1], string.format("The route ends at %d.", plan.target) } }
  end
  if nxt.blocked then                    -- no recipe of the stretch can be learned at the character's level (ns.Effective)
    local mine = UnitLevel and UnitLevel("player") or 0
    table.insert(tip, string.format("No recipe of the route fits at character level %d for skill %d to %d: %s asks for level %s%s. Level up, or learn one later; the route goes on after this stretch.",
      mine, nxt.from, nxt.to, ns.RecipeName(nxt.step), tostring(nxt.asks or "?"),
      (nxt.step.others or 0) > 0 and string.format(", and so %s the %d next best", nxt.step.others > 1 and "do" or "does", nxt.step.others) or ""))
    local text = (nxt.step.others or 0) > 0 and string.format("Needs a higher level for skill %d to %d", nxt.from, nxt.to)
      or string.format("Needs level %s for %s", tostring(nxt.asks or "?"), ns.RecipeName(nxt.step))       -- no next best to fall back on: the recipe's own words
    return { text = text, tip = tip, profession = profession, show = true }
  end
  local fishing = plan.kind == "fishing"  -- the fishing route's costs are weights, not copper: no money wording for them
  if nxt.step.instead then               -- the next best stands in for a recipe the character cannot learn yet
    table.insert(tip, fishing and string.format("%s stands in for %s, which asks for character level %d.", ns.RecipeName(nxt.step), nxt.step.instead, nxt.step.asks or 0)
      or string.format("%s stands in for %s, which asks for character level %d: about %s a skill point.",
        ns.RecipeName(nxt.step), nxt.step.instead, nxt.step.asks or 0, ns.Money(nxt.step.cpp or 0)))
  end
  if nxt.step.over and nxt.step.mine and #nxt.step.mine > 0 then   -- the next best costs this character less with what it has (Tailor.lua)
    usingOf = ns.UsingText(nxt.step, function(item) return N(house, item) end)
    table.insert(tip, fishing and string.format("%s: %s stands in for %s, with fewer fish to catch for you. The box \"Use what I already have first\" in Interface > AddOns turns this off.",
        usingOf, ns.RecipeName(nxt.step), nxt.step.over)
      or string.format("%s: %s stands in for %s, about %s a skill point less for you. The box \"Use what I already have first\" in Interface > AddOns turns this off.",
        usingOf, ns.RecipeName(nxt.step), nxt.step.over, ns.Money(nxt.step.saves or 0)))
  end
  if nxt.capped then table.insert(tip, string.format("Only as far as the gold goes (the box in the /fwc window): this step is cut at skill %d.", nxt.to)) end
  -- the next rank (Journeyman at 75, Expert at 150, Artisan at 225) can be trained from 25
  -- below the cap. From there it is a note under the arrow, the craft path going on; from one
  -- below the cap it comes before anything else: the next point would reach the cap, where
  -- no craft gives a point and the craft under way is one too many
  local cap = open.max or (Char().caps or {})[plan.skill_line]
  if cap and cap > 0 and cap < plan.target and skill >= cap - RANK_EARLY then
    local what = RANKS[cap] and (RANKS[cap] .. " " .. ns.Title(profession)) or ("the next rank of " .. ns.Title(profession))
    local place = { "trainer", profession, nil, ns.Title(profession) .. " trainer", cap + 1 }
    local act, got = "Train " .. what, "trained"
    local up = RANKUPS[profession] and RANKUPS[profession][cap]
    if up and up.book then
      act, got = "Buy " .. up.name, "learned from its book"
      place = { "vendor", nil, up.book, "Seller of " .. up.name }
      table.insert(tip, string.format("No trainer teaches %s: it is the book %s, sold by %s. The book asks for skill %d.", what, up.name, up.where, up.needs))
    end
    local young                          -- below the quest's character level: the words say so, not the tooltip alone (a player was sent to a quest they could not take yet, 9 Nov 2026)
    if up and up.quest then
      local mine = UnitLevel and UnitLevel("player") or 0
      young = mine > 0 and mine < up.level
      act, got = "Learn " .. what .. " by the quest " .. up.quest, "earned by its quest"
      if young then act = string.format("At level %d, learn %s by the quest %s", up.level, what, up.quest) end
      place = { "quest", profession, nil, up.quest }
      table.insert(tip, string.format("No trainer teaches %s: the quest %s gives it, from %s. It asks for skill %d and character level %d.", what, up.quest, up.where, up.needs, up.level))
      if young then table.insert(tip, string.format("You are level %d: the quest is offered from level %d.", mine, up.level)) end
      for _, n in ipairs(plan.notes or {}) do         -- the route's own word on the quest (the fishing route: what it asks for that is not fished)
        if n[1] == up.needs then table.insert(tip, n[2]) end
      end
    end
    if skill >= cap - 1 then
      table.insert(tip, skill >= cap
        and string.format("Skill %d is the cap: no craft gives a point until %s is %s.", skill, what, got)
        or string.format("Skill %d: the next point reaches the cap. %s first.", skill, act))
      return { text = young and act or act .. " first", tip = tip, profession = profession, rank = cap, place = place }
    end
    asideOf = { text = act, place = place, from = cap - RANK_EARLY, cap = cap }
    table.insert(tip, string.format("%s can be %s from skill %d (the cap is %d): see the arrow's note.", what, got, cap - RANK_EARLY, cap))
  end
  local step = nxt.step
  table.insert(tip, string.format("Step: %s, skill %d to %d, about %d crafts.", ns.RecipeName(step), nxt.from, nxt.to, nxt.crafts))
  -- a recipe to learn: the trainer's, or one the route buys. With reagents to buy as well, the
  -- nearer of the trainer and the house comes first, the other as a note under the arrow
  if Learned(nxt.spell) == false then
    local learn = step.learn
    local trainer = { "trainer", profession, nil, ns.Title(profession) .. " trainer", step.from, step.at and step.at[1], nxt.spell }     -- [5] the rank to train, [6] the skill the recipe is learned at (a trainer seen to teach none so high comes last), [7] its spell (a trainer seen to teach it only)
    local made = BagsBeforeLearning(house, plan, nxt, skill, banked, tip, profession, learn, trainer)
    if made then return made end
    if not learn and NearerFirst(profession, plan, nxt, step.from, trainer[6], trainer[7]) == "buy" then
      table.insert(tip, "The house is nearer: buy first, then learn the recipe at the trainer.")
      local v = BuyVerdict(house, plan, nxt, step, tip, profession)
      asideOf = { text = "Then learn " .. ns.RecipeName(step) .. " at the trainer", place = trainer }
      return v
    end
    -- the scroll asks for a character level (the client's word first, the route's data else): short
    -- of it the recipe cannot be learned, and the button says so instead of sending the player to
    -- buy it (a player below 45 sent for Recipe: Elixir of Intellect, 8 Nov 2026)
    local need = learn and ((ns.NoteRecipeLevel and ns.NoteRecipeLevel(learn[1])) or learn[3])
    local mine = UnitLevel and UnitLevel("player")
    if need and mine and need > mine then
      table.insert(tip, string.format("%s asks for character level %d, and this character is %d: the recipe cannot be learned yet. The route for your level, on the site, leaves it out.", N(house, learn[1]), need, mine))
      Char().tolearn = nil
      return { text = string.format("Needs level %d for %s", need, ns.RecipeName(step)), tip = tip, profession = profession, show = true }
    end
    -- the scroll the route buys, had already: in the mail, the bank or the bags (bought by hand or
    -- with the Buy button): fetched or used, not bought again; the level gate above applies first
    local had = learn and ScrollVerdict(house, plan, nxt, step, tip, profession, learn[1])
    if had then Char().tolearn = { spell = nxt.spell, item = learn[1], cost = learn[2] }; return had end
    local sold = fishing and learn and plan.sold_by and plan.sold_by[learn[1]]       -- the fishing route's recipes are a vendor's
    table.insert(tip, learn and string.format("The route buys the recipe, %s, for %s: %s.", N(house, learn[1]), ns.Money(learn[2]),
      sold and ("sold by " .. sold) or fishing and "sold by a vendor" or "a pattern sold or dropped, not a trainer's")
      or "The trainer teaches it.")
    Char().tolearn = learn and { spell = nxt.spell, item = learn[1], cost = learn[2] } or nil
    local shopping = learn and ShoppingOf(plan, nxt, Char().tolearn) or nil
    if shopping then shopping.title = ns.RecipeName(step) .. ": the recipe, and what the step needs" end
    if not learn and #nxt.buy > 0 then
      local buy = BuyVerdict(house, plan, nxt, step, {}, profession)
      local then_ = "Then " .. buy.text:sub(1, 1):lower() .. buy.text:sub(2)
      if buy.place then
        asideOf = { text = then_, place = buy.place }
        table.insert(tip, "The trainer is nearer; the needs come after (the arrow's note).")
      else                                  -- only fish to catch: nowhere to point at, the tooltip says what comes after
        table.insert(tip, then_ .. ".")
      end
    end
    -- "Buy the recipe" for a pattern the route buys: "Learn" read as the trainer's to a player
    -- who then looked for Red Linen Vest there
    return { text = (learn and "Buy the recipe for " or "Learn ") .. ns.RecipeName(step) .. " first", tip = tip, shopping = shopping, learn = nxt.spell,
             place = learn and Seller(plan, learn[1]) or trainer, profession = profession }
  end
  Char().tolearn = nil
  -- what the bags allow a craft of, the step's own recipe first (skill now), then what it
  -- makes on the way
  local function Can(c)
    local can = c.crafts
    for _, u in ipairs(c.uses or {}) do
      can = math.min(can, math.floor((ns.inv.Count(u[1]) or 0) / u[2]))
    end
    return can
  end
  if not given then Char().tool = nil end      -- a tool to buy is remembered below, while a step lacks it
  -- the candidates: what the step makes on the way (bolts for a bag) first, while the bags
  -- hold fewer than the step needs, for as many crafts as are still short; the step's recipe
  -- after. The other way round, the step's recipe took over as soon as the bags held enough
  -- for one craft of it, mid-run of the intermediate (12 Oct 2026)
  local candidates = {}
  local unsaid                         -- an intermediate the document does not say how to make
  for _, m in ipairs(nxt.make) do
    if m[4] then                       -- its units and crafts are what the step still lacks, the bags counted
      if (m[3] or 0) > 0 then
        table.insert(candidates, { spell = m[4], crafts = m[3], what = N(house, m[1]), uses = m[5], onway = m[2] })
      end
    else
      unsaid = unsaid or { crafts = m[3], what = N(house, m[1]) }
    end
  end
  table.insert(candidates, { spell = nxt.spell, crafts = nxt.crafts, what = ns.RecipeName(step), uses = nxt.uses })
  for _, c in ipairs(candidates) do
    local can = Can(c)
    if can > 0 then
      if c.onway then table.insert(tip, string.format("First, on the way: %d %s.", c.onway, c.what)) end
      if api.Learned(c.spell) == false then
        table.insert(tip, "The trainer teaches it.")
        return { text = "Learn " .. c.what .. " first", tip = tip, place = { "trainer", profession, nil, ns.Title(profession) .. " trainer", nil, c.spell == nxt.spell and nxt.step.at and nxt.step.at[1] or nil, c.spell } }
      end
      local needs, place, tools = {}, nil, {}
      for _, r in ipairs(api.Requirements(c.spell)) do
        if not r.met then
          -- a place the client asks for that a recipe of this profession makes is a camp object
          -- (a Tanning Rack, a Spinning Wheel: Forever, 6 Nov 2026): made and placed, not found
          if r.place and not api.ToolRecipe(r.name) then
            table.insert(needs, r.name)
            if not place then place = { "station", r.name, nil, r.name } end
          else
            table.insert(tools, r.name)
          end
        end
      end
      -- a tool lacking (an Arclight Spanner) comes before any walk to a station: learned at the
      -- trainer when a recipe of the profession makes it and is not known; made here when it is
      -- (at its own station, when it needs one); else bought, where the route's prices say
      if #tools > 0 then
        local tool = tools[1]
        local recipe = api.ToolRecipe(tool)
        local owned = recipe and api.ItemByName(tool)
        if owned and (ns.inv.Count(owned) or 0) > 0 then           -- a camp object made and in the bags: put it down
          table.insert(tip, string.format("%s needs %s beside you: it is in your bags, place it at your camp.", c.what, tool))
          return { text = "Place " .. tool .. " first", tip = tip, show = true, profession = profession }
        end
        local known = ns.ToolsKnown and ns.ToolsKnown()
        local t = known and known.made[Spelt(tool)]
        local titem = (t and t.item) or api.ItemByName(tool)
        local row = titem and Char().items[titem]
        if row and (row[2] or 0) > 0 and (ns.inv.Count(titem) or 0) == 0 then   -- had, in the bank: not made or bought again
          table.insert(tip, string.format("%s needs %s: it is in your bank.", c.what, tool))
          return { text = "Take " .. tool .. " from the bank first", tip = tip, show = true, profession = profession }
        end
        if recipe and not recipe.learned then
          table.insert(tip, string.format("%s needs %s: learn it at the trainer.", c.what, tool))
          return { text = "Learn " .. recipe.name .. " first", tip = tip, learn = recipe.spell, profession = profession,
                   place = { "trainer", profession, nil, ns.Title(profession) .. " trainer", nil, nil, recipe.spell } }
        end
        if recipe then
          local tneeds, tplace = {}, nil
          for _, r in ipairs(api.Requirements(recipe.spell)) do
            if not r.met and r.place then
              table.insert(tneeds, r.name)
              if not tplace then tplace = { "station", r.name, nil, r.name } end
            end
          end
          if #tneeds > 0 then
            table.insert(tip, string.format("%s needs %s, made at %s.", c.what, tool, table.concat(tneeds, ", ")))
            return { text = "Needs " .. table.concat(tneeds, ", ") .. " to make " .. recipe.name, tip = tip, place = tplace, recipe = recipe.spell, profession = profession }
          end
          -- what the tool takes, short in the bags: bought first, on the step's list (the walk has it)
          local short = false
          for _, u in ipairs(t and t.uses or {}) do
            if (ns.inv.Count(u[1]) or 0) < u[2] then short = true end
          end
          if short and #nxt.buy > 0 then
            table.insert(tip, string.format("%s needs %s, made from what is on the list.", c.what, tool))
            return MailVerdict(house, plan, nxt, step, tip, profession) or BuyVerdict(house, plan, nxt, step, tip, profession)
          end
          table.insert(tip, string.format("%s needs %s. Click: makes one.", c.what, tool))
          return { text = "Make 1 " .. recipe.name .. " first", tip = tip, spell = recipe.spell, crafts = 1, to = nxt.to, line = plan.skill_line, profession = profession }
        end
        local item = titem
        if item then
          local row = ns.BuyRow(plan, item)
          if not given then Char().tool = { item = item, name = tool, price = row and row[1] or nil, source = row and row[2] == "vendor" and "vendor" or "ah" } end
          local source = row and row[2] == "vendor" and "vendor" or "ah"
          local shopping = { { item = item, units = 1, have = 0, source = source, price = row and row[1] or nil } }
          shopping.title = tool .. ", to make " .. c.what
          table.insert(tip, string.format("%s needs %s, bought %s. Click: the list.", c.what, tool, source == "vendor" and "from a vendor" or "at the auction house"))
          return { text = "Buy " .. tool .. " first", tip = tip, shopping = shopping, place = Seller(plan, item), profession = profession }
        end
        table.insert(tip, string.format("%s needs %s: a vendor sells it.", c.what, tool))
        return { text = "Buy " .. tool .. " first", tip = tip, show = true, profession = profession }
      end
      if #needs > 0 then
        table.insert(tip, "The recipe needs " .. table.concat(needs, ", ") .. ".")
        return { text = "Needs " .. table.concat(needs, ", "), tip = tip, place = place, recipe = c.spell, profession = profession }
      end
      table.insert(tip, string.format("Click: makes %d, stopping at skill %d.", can, nxt.to))
      return { text = string.format("Make %d %s", can, c.what), tip = tip, spell = c.spell, crafts = can, to = nxt.to, line = plan.skill_line, profession = profession }
    end
  end
  -- nothing of the stretch's recipe can be made from the bags: a recipe that may stand in for it
  -- and that the bags hold a craft of (BagsVerdict); then what is in the bank (with "Use what I
  -- already have first"), what waits in the mail, then what to buy, where
  local fromBags = BagsVerdict(house, plan, nxt, skill, banked, tip, profession)
  if fromBags then return fromBags end
  local fromBank = BankVerdict(house, plan, nxt, banked, tip, profession)
  if fromBank then return fromBank end
  if #nxt.buy > 0 then return MailVerdict(house, plan, nxt, step, tip, profession) or BuyVerdict(house, plan, nxt, step, tip, profession) end
  if unsaid then
    table.insert(tip, "Run the helper (fwch.py plans) for a newer route.")
    return { text = string.format("Make %d %s first", unsaid.crafts, unsaid.what), tip = tip, profession = profession }
  end
  table.insert(tip, "The bags do not hold a craft's worth.")
  return { text = "Reagents missing", tip = tip }
end

-- ================================================================ the gold
-- A verdict that buys (its shopping list: reagents, a recipe, a tool) is held against the gold
-- in the bags. Short of it, the words say by how much and the two ways out: gold farmed, or
-- the reagents farmed instead of bought, where they can be (the recipe and a vendor's goods
-- take gold; what the house sells drops or grows somewhere). No arrow to a seller for what
-- cannot be paid; the click still opens the list, with the prices. A player was told
-- to buy a cooking recipe without the silver for it.
local function Short(v)
  if not v.shopping or not GetMoney then return v end
  local cost, unknown, farm = 0, false, {}
  for _, e in ipairs(v.shopping) do
    local n = e.units - (e.have or 0)
    if n > 0 and e.source ~= "catch" then                   -- a fish is caught: it costs no gold
      if e.price then cost = cost + e.price * n else unknown = true end
      if e.source ~= "vendor" and not e.recipe then table.insert(farm, string.format("%d %s", n, N(House() or {}, e.item))) end
    end
  end
  local gold = GetMoney() or 0
  if cost <= gold then return v end
  v.short, v.place, v.show = cost - gold, nil, true
  v.text = string.format("Short %s: farm gold%s", ns.Money(cost - gold), #farm > 0 and (" or farm " .. table.concat(farm, ", ")) or "")
  local at = #v.tip + 1                                    -- before "Click: ..." when that is the last line
  if v.tip[#v.tip] and v.tip[#v.tip]:match("^Click") then at = #v.tip end
  table.insert(v.tip, at, string.format("Gold in the bags: %s; this needs about %s%s.", ns.Money(gold), ns.Money(cost), unknown and " at least" or ""))
  table.insert(v.tip, at + 1, #farm > 0 and ("Farm the gold, or farm " .. table.concat(farm, ", ") .. " instead of buying" .. (#farm < #v.shopping and " (the rest takes gold)" or "") .. ".")
                                        or "Farm the gold: what is short is bought, not farmed.")
  return v
end

-- the verdict, with its note (the next rank to train, from 25 below the cap) and the gold
local function Verdict(given)
  asideOf, usingOf, memory = nil, nil, nil
  local v = VerdictOf(given)
  memory = nil                             -- the record answers for one verdict only
  if type(v) == "table" and asideOf then v.aside = asideOf end
  if type(v) == "table" and usingOf and not v.rank then v.note, v.using = v.note and (usingOf .. "; " .. v.note) or usingOf, usingOf end   -- the arrow's note says it too
  if type(v) == "table" then Short(v) end
  return v
end

api.IsPlace = IsPlace
-- whether the book opened another profession since last asked (the shopping list follows it)
local function Switched() local s = switched; switched = false; return s end

ns.verdict = { Verdict = Verdict, api = api, NoteStations = NoteStations, Selected = Selected, Switched = Switched }
ns.craft = { Shopping = Shopping }

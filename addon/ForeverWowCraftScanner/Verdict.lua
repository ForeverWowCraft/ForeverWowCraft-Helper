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

local _, ns = ...
local Char, House, Spelt = ns.inv.Char, ns.inv.House, ns.inv.Spelt

local PREFIX = "|cff" .. ns.BRAND.gold .. "ForeverWowCraft|r: "

-- ================================================================ the next thing to make
-- The first step of the route with crafts left at `skill`, walked on its own with `have` =
-- { [item] = units } in hand: { step, spell, crafts, from, to, uses,
--   buy = { {item, units}, ... }                what `have` lacks for it, most first,
--   make = { {item, units, crafts, spell, uses}, ... }   what the step makes on the way (spell
--                                             nil when the document does not say how) };
-- nil when the route is done at `skill`.
function ns.NextCraft(plan, skill, have)
  local step, left
  for _, s in ipairs(plan.steps or {}) do
    left = ns.CraftsLeft(s, skill)
    if left > 0 then step = s; break end
  end
  if not step then return nil end
  local walk = ns.Tailor(plan, skill, have, step.to)
  local out = { step = step, spell = step.spell, crafts = left, from = math.max(skill, step.from), to = step.to,
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
function api.Open()
  if C_TradeSkillUI and C_TradeSkillUI.GetBaseProfessionInfo then
    local ok, info = pcall(C_TradeSkillUI.GetBaseProfessionInfo)
    if ok and type(info) == "table" and (info.professionID or info.profession) then
      return { id = info.professionID or info.profession, name = info.professionName or info.parentProfessionName, rank = info.skillLevel, max = info.maxSkillLevel }
    end
  end
  if C_TradeSkillUI and C_TradeSkillUI.GetTradeSkillLine then
    local ok, id, name, rank, max = pcall(C_TradeSkillUI.GetTradeSkillLine)
    if ok and id and id ~= 0 then return { id = id, name = name, rank = rank, max = max } end
  end
  if GetTradeSkillLine then
    local name, rank, max = GetTradeSkillLine()
    if name and name ~= "" then return { name = name, rank = rank, max = max } end
  end
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
-- from the bags)
local function Bags(plan)
  local have, seen = {}, {}
  local function Add(item)
    if item and not seen[item] then
      seen[item] = true
      have[item] = ns.inv.Count(item) or 0
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
  return have
end

local function N(house, item) return (ns.ItemName(item, house.items and house.items[item])) end

-- where the route buys an item: { kind, what, item, title } for ns.NearestPlace
local function Seller(plan, item)
  local row = plan.buy and plan.buy[item]
  if row and row[2] == "vendor" then return { "vendor", nil, item, "Vendor" } end
  return { "auction", nil, nil, "Auctioneer" }
end

-- what a step needs bought, as Shop.lua lists it: { item, units (in all, from the bags), have,
-- source ("ah" | "vendor"), price (about, a unit), recipe (true for the recipe item) }
local function ShoppingOf(plan, nxt, tolearn)
  local out = {}
  for _, b in ipairs(nxt.buy) do
    local row = plan.buy and plan.buy[b[1]]
    local have = ns.inv.Count(b[1]) or 0
    table.insert(out, { item = b[1], units = b[2] + have, have = have, source = row and row[2] == "vendor" and "vendor" or "ah", price = row and row[1] or nil })
  end
  if tolearn and tolearn.spell == nxt.spell and (ns.inv.Count(tolearn.item) or 0) == 0 then
    local row = plan.buy and plan.buy[tolearn.item]
    table.insert(out, 1, { item = tolearn.item, units = 1, have = 0, source = row and row[2] == "vendor" and "vendor" or "ah", price = tolearn.cost, recipe = true })
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
  local function has(plan) return c.skills[plan.skill_line] or (open and open.id == plan.skill_line and open.rank) or nil end
  local making = c.making and ns.RouteFor(c.making)
  local profession = (making and has(making)) and c.making or (ns.OwnProfession and ns.OwnProfession())
  local plan = profession and ns.RouteFor(profession)
  if not plan then return {} end
  local skill = has(plan)
  if not skill then return {} end             -- a profession the character does not have: nothing to buy for it
  local nxt = skill < plan.target and ns.NextCraft(plan, skill, Bags(plan))
  if not nxt then return {} end
  local out = ShoppingOf(plan, nxt, c.tolearn)
  local t = c.tool
  if type(t) == "table" and t.item and (ns.inv.Count(t.item) or 0) == 0 then        -- the tool the step lacks, first
    table.insert(out, 1, { item = t.item, units = 1, have = 0, source = t.source or "ah", price = t.price })
  end
  out.title = ns.RecipeName(nxt.step) .. ", skill " .. nxt.from .. " to " .. nxt.to .. ", needs"
  return out
end

-- the rank a cap ends, by the cap: what the trainer teaches next
local RANKS = { [75] = "Journeyman", [150] = "Expert", [225] = "Artisan" }
local RANK_EARLY = 25                      -- the next rank is taught from this far below the cap

-- What the button does now: { text, tip = { lines }, spell, crafts, to, line }; spell nil
-- when the click can make nothing, and text says why. `given` = { open, profession } stands
-- in for the panel when none is open (the arrow with the window closed, Headless below)
-- the verdict when nothing can be made from the bags: what to buy, where, the list on a click
local function BuyVerdict(house, plan, nxt, step, tip, profession)
  local shopping = ShoppingOf(plan, nxt)
  shopping.title = ns.RecipeName(step) .. ", skill " .. nxt.from .. " to " .. nxt.to .. ", needs"
  local ah, vendor = {}, {}
  for _, e in ipairs(shopping) do table.insert(e.source == "vendor" and vendor or ah, e) end
  local text
  if #ah == 1 and #vendor == 0 then text = string.format("Buy %d %s at the auction house", ah[1].units - ah[1].have, N(house, ah[1].item))
  elseif #ah > 0 and #vendor == 0 then text = string.format("Buy at the auction house: %d items", #ah)
  elseif #ah == 0 and #vendor == 1 then text = string.format("Buy %d %s from a vendor", vendor[1].units - vendor[1].have, N(house, vendor[1].item))
  elseif #ah == 0 then text = string.format("Buy from a vendor: %d items", #vendor)
  else text = string.format("Buy at the auction house (%d) and a vendor (%d)", #ah, #vendor) end
  table.insert(tip, "Needs:")
  for _, e in ipairs(shopping) do
    table.insert(tip, string.format("  %d %s (have %d)%s, %s", e.units - e.have, N(house, e.item), e.have,
      e.price and (", about " .. ns.Money(e.price * (e.units - e.have))) or "", e.source == "vendor" and "from a vendor" or "at the auction house"))
  end
  table.insert(tip, "Click: the shopping list.")
  return { text = text, tip = tip, shopping = shopping, place = #ah > 0 and Seller(plan, ah[1].item) or Seller(plan, vendor[1].item), profession = profession }
end

-- A recipe to learn and reagents to buy are two trips: the nearer one first. The house, when
-- it is open, or nearer than the trainer, or on this map when the trainer is not; the trainer
-- otherwise, and when there is nothing to buy or no seller known (running between the house
-- and the trainer ate the time, 12 Oct 2026)
local function NearerFirst(profession, plan, nxt, upto)
  if #nxt.buy == 0 then return "trainer" end
  if ns.scanner and ns.scanner.Open() then return "buy" end
  local seller = Seller(plan, nxt.buy[1][1])
  local s, sd, shere = ns.NearestPlace(seller[1], seller[2], seller[3])
  if not s then return "trainer" end
  local t, td, there = ns.NearestPlace("trainer", profession, nil, upto)
  if not t then return "buy" end
  if shere and not there then return "buy" end
  if there and not shere then return "trainer" end
  if sd and td and sd < td then return "buy" end
  return "trainer"
end

local switched                           -- the book opened another profession: the shopping list follows
local asideOf                            -- the note the verdict carries under the arrow (the next rank to train, the other trip)
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
  if not given and Char().making ~= profession then      -- the profession opened in the book: the list's and the arrow's
    Char().making = profession
    switched = true
  end
  local skill = open.rank or Char().skills[plan.skill_line] or plan.start
  local tip = { string.format("%s route, skill %d.", ns.Title(profession), skill) }
  local nxt = skill < plan.target and ns.NextCraft(plan, skill, Bags(plan))
  if not nxt then
    return { text = string.format("Route done at skill %d", skill), tip = { tip[1], string.format("The route ends at %d.", plan.target) } }
  end
  -- the next rank (Journeyman at 75, Expert at 150, Artisan at 225) can be trained from 25
  -- below the cap. From there it is a note under the arrow, the craft path going on; from one
  -- below the cap it comes before anything else: the next point would reach the cap, where
  -- no craft gives a point and the craft under way is one too many
  local cap = open.max or (Char().caps or {})[plan.skill_line]
  if cap and cap > 0 and cap < plan.target and skill >= cap - RANK_EARLY then
    local what = RANKS[cap] and (RANKS[cap] .. " " .. ns.Title(profession)) or ("the next rank of " .. ns.Title(profession))
    local place = { "trainer", profession, nil, ns.Title(profession) .. " trainer", cap + 1 }
    if skill >= cap - 1 then
      table.insert(tip, skill >= cap
        and string.format("Skill %d is the cap: no craft gives a point until %s is trained.", skill, what)
        or string.format("Skill %d: the next point reaches the cap. Train %s first.", skill, what))
      return { text = "Train " .. what .. " first", tip = tip, profession = profession, rank = cap, place = place }
    end
    asideOf = { text = "Train " .. what, place = place, from = cap - RANK_EARLY, cap = cap }
    table.insert(tip, string.format("%s can be trained from skill %d (the cap is %d): see the arrow's note.", what, cap - RANK_EARLY, cap))
  end
  local step = nxt.step
  table.insert(tip, string.format("Step: %s, skill %d to %d, about %d crafts.", ns.RecipeName(step), nxt.from, nxt.to, nxt.crafts))
  -- a recipe to learn: the trainer's, or one the route buys. With reagents to buy as well, the
  -- nearer of the trainer and the house comes first, the other as a note under the arrow
  if api.Learned(nxt.spell) == false then
    local learn = step.learn
    local trainer = { "trainer", profession, nil, ns.Title(profession) .. " trainer", step.from }
    if not learn and NearerFirst(profession, plan, nxt, step.from) == "buy" then
      table.insert(tip, "The house is nearer: buy first, then learn the recipe at the trainer.")
      local v = BuyVerdict(house, plan, nxt, step, tip, profession)
      asideOf = { text = "Then learn " .. ns.RecipeName(step) .. " at the trainer", place = trainer }
      return v
    end
    table.insert(tip, learn and string.format("The route buys the recipe, %s, for %s: a pattern sold or dropped, not a trainer's.", N(house, learn[1]), ns.Money(learn[2]))
      or "The trainer teaches it.")
    Char().tolearn = learn and { spell = nxt.spell, item = learn[1], cost = learn[2] } or nil
    local shopping = learn and ShoppingOf(plan, nxt, Char().tolearn) or nil
    if shopping then shopping.title = ns.RecipeName(step) .. ": the recipe, and what the step needs" end
    if not learn and #nxt.buy > 0 then
      local buy = BuyVerdict(house, plan, nxt, step, {}, profession)
      asideOf = { text = "Then " .. buy.text:sub(1, 1):lower() .. buy.text:sub(2), place = buy.place }
      table.insert(tip, "The trainer is nearer; the needs come after (the arrow's note).")
    end
    -- "Buy the recipe" for a pattern the route buys: "Learn" read as the trainer's to a player
    -- who then looked for Red Linen Vest there (the user, 7 Nov 2026)
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
        return { text = "Learn " .. c.what .. " first", tip = tip, place = { "trainer", profession, nil, ns.Title(profession) .. " trainer" } }
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
        if recipe and not recipe.learned then
          table.insert(tip, string.format("%s needs %s: learn it at the trainer.", c.what, tool))
          return { text = "Learn " .. recipe.name .. " first", tip = tip, learn = recipe.spell, profession = profession,
                   place = { "trainer", profession, nil, ns.Title(profession) .. " trainer" } }
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
          table.insert(tip, string.format("%s needs %s. Click: makes one.", c.what, tool))
          return { text = "Make 1 " .. recipe.name .. " first", tip = tip, spell = recipe.spell, crafts = 1, to = nxt.to, line = plan.skill_line, profession = profession }
        end
        local item = api.ItemByName(tool)
        if item then
          local row = plan.buy and plan.buy[item]
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
  -- nothing can be made from the bags: what to buy, where
  if #nxt.buy > 0 then return BuyVerdict(house, plan, nxt, step, tip, profession) end
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
-- cannot be paid; the click still opens the list, with the prices. The user, 6 Nov 2026: told
-- to buy a cooking recipe without the silver for it.
local function Short(v)
  if not v.shopping or not GetMoney then return v end
  local cost, unknown, farm = 0, false, {}
  for _, e in ipairs(v.shopping) do
    local n = e.units - (e.have or 0)
    if n > 0 then
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
  asideOf = nil
  local v = VerdictOf(given)
  if type(v) == "table" and asideOf then v.aside = asideOf end
  if type(v) == "table" then Short(v) end
  return v
end

api.IsPlace = IsPlace
-- whether the book opened another profession since last asked (the shopping list follows it)
local function Switched() local s = switched; switched = false; return s end

ns.verdict = { Verdict = Verdict, Bags = Bags, Shopping = Shopping, api = api, NoteStations = NoteStations, Selected = Selected, N = N, Switched = Switched }
ns.craft = { Verdict = Verdict, Bags = Bags, Shopping = Shopping }

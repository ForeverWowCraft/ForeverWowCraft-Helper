-- A route, less what the character has.
--
-- ns.Tailor(plan, skill, have) walks a route of FWCS_PLANS (fwchelper/plans.py says what a plan
-- holds) from `skill` on, with `have` = { [itemID] = units } in hand, and says what is left to
-- do: what to buy, what to make on the way (and how, for the Make button), what of `have` gets
-- used, and what is left to sell. Nothing here asks the game anything, so it runs outside it
-- too (tests/test_ingame.py).
--
-- Each step's reagents come, in this order, from what the character has, from what earlier
-- steps made, from crafting them (where the route does: step.craft and plan.made), and from
-- buying. A reagent the route took from an earlier step that the character is already past is
-- made the way that step made it. Prices are the route's average for one unit, so a shorter
-- list is an estimate: the cheapest auctions go first, and fewer units cost less each.
--
-- A tool a step's recipe needs beside its reagents (an enchanter's Runed Copper Rod) is got
-- once, before the first step that needs it, unless `have` holds it: made, its reagents taken
-- like a step's (a Copper Rod from a vendor and a Strange Dust), or bought when no recipe of
-- the profession makes it. The routes' documents do not say which recipe needs which tool; the
-- client does, with the profession's recipes open, and ns.LearnTools (Verdict.lua) keeps what
-- it says in FWCS_DB.__tools, read here (a player's shopping list left out the rod the Make
-- button then had them make, 10 Nov 2026).

local _, ns = ...

local function Spelt(name) return ((name or ""):lower():gsub("[^a-z0-9]", "")) end

-- ================================================================ the tools the recipes need
-- FWCS_DB.__tools = { v = changes made, spells = { [recipe spell] = { tool name, ... } },
--                     made = { [spelt tool name] = { item, name, spell (its recipe; nil: bought),
--                              uses = { { item, units }, ... }, needs = { tool name, ... },
--                              met = true when the client said a recipe had it and none was counted } } }
-- What a lookup needs, made again only when ns.LearnTools changed something (v)
local index, indexOf, indexV
function ns.ToolsKnown()
  local k = FWCS_DB and FWCS_DB.__tools
  if not k then return nil end
  if index and indexOf == k and indexV == k.v then return index end
  local byItem = {}
  for _, t in pairs(k.made or {}) do if t.item then byItem[t.item] = t end end
  index, indexOf, indexV = { spells = k.spells or {}, made = k.made or {}, byItem = byItem }, k, k.v
  return index
end

-- a tool's name as the client gave it when it was learned, for a route whose items do not name it
function ns.ToolName(item)
  local known = ns.ToolsKnown()
  local t = known and known.byItem[item]
  return t and t.name or nil
end

-- How many of a tool this character has: the bags, and the bank as counted when last open (a
-- tool is had wherever it is kept; the step's own check at the panel wants it in the bags).
-- One when the client said a recipe had the tool while none was counted (a better one standing
-- in for it). 0 outside the game
function ns.ToolOwned(item)
  local inv = ns.inv
  if not (inv and inv.Count) then return 0 end
  local n = inv.Count(item) or 0
  local c = inv.Char and inv.Char()
  local row = c and c.items and c.items[item]
  n = n + (row and row[2] or 0)
  local known = ns.ToolsKnown()
  local t = known and known.byItem[item]
  if n == 0 and t and t.met then n = 1 end
  return n
end

-- `have` with every tool the addon knows of counted as this character has it (ns.ToolOwned):
-- another character's does not help, a rod being soulbound; the bank's does
function ns.OwnTools(have)
  local known = ns.ToolsKnown()
  if not known then return have end
  for item in pairs(known.byItem) do have[item] = ns.ToolOwned(item) end
  return have
end

-- The price of one where the route gets it, as plan.buy has it ({ copper, "ah" | "vendor" }):
-- the route's own, else another route of the house that buys it, else a merchant met that
-- sells it for gold alone (FWCS_DB.__vendors: the price of one purchase over its bundle); nil
-- when nothing says. For what a tool takes, which the route itself may not buy (Copper Rod)
local houseRows = setmetatable({}, { __mode = "k" })
local vendorRows, vendorsAt, vendorsOf          -- the merchants met, by item: made again when one is noted
local function Vendors()
  local all = FWCS_DB and FWCS_DB.__vendors
  if vendorRows and vendorsAt == ns.notedAt and vendorsOf == all then return vendorRows end
  vendorRows, vendorsAt, vendorsOf = {}, ns.notedAt, all
  for _, v in pairs(all or {}) do
    for item, w in pairs(type(v) == "table" and type(v.items) == "table" and v.items or {}) do
      if not vendorRows[item] and type(w) == "table" and (w.price or 0) > 0 and w.usable ~= false and not w.cost then
        vendorRows[item] = { w.price / math.max(1, w.stack or 1), "vendor" }
      end
    end
  end
  return vendorRows
end
function ns.BuyRow(plan, item)
  local row = plan and plan.buy and plan.buy[item]
  if row then return row end
  local house = ns.inv and ns.inv.House and ns.inv.House()
  if house then
    local rows = houseRows[house]
    if not rows then
      rows = {}
      for _, p in pairs(house.plans or {}) do
        for i, r in pairs(p.buy or {}) do
          i = tonumber(i) or i
          if not rows[i] or (r[2] == "vendor" and rows[i][2] ~= "vendor") then rows[i] = r end
        end
      end
      houseRows[house] = rows
    end
    if rows[item] then return rows[item] end
  end
  return Vendors()[item]
end

-- ================================================================ the fishing route
-- The fishing route (Plans.lua FWCS_ROUTES, joined to the house by Inventory.lua) is a plan of
-- kind "fishing": its fish are buy rows with the source "catch" (a weight, never copper), and
-- plan.catch = { [fish] = { { zone, chance }, ... } } says where each is caught, from the
-- Classic-era world's tables, which may differ from Forever's. Nothing here asks the game.
ns.CATCH_NOTE = "Catch spots are from the Classic-era world and may differ."

-- whether the route buys the item by catching it
function ns.Catches(plan, item)
  local row = plan and plan.buy and plan.buy[item]
  return row ~= nil and row[2] == "catch"
end

-- where a fish is caught, from the plan: "Wetlands 100%, Teldrassil 100%, Loch Modan 88%", or with
-- `names` only the zones' names; nil when the plan names none. Made once a plan, a fish and a kind
local spots = setmetatable({}, { __mode = "k" })
function ns.CatchSpots(plan, item, names)
  local all = plan and plan.catch
  local rows = all and all[item]
  if type(rows) ~= "table" or #rows == 0 then return nil end
  local held = spots[all]
  if not held then held = {}; spots[all] = held end
  local key = names and -item or item
  if held[key] == nil then
    local parts = {}
    for _, z in ipairs(rows) do
      local chance = tonumber(z[2]) or 0
      table.insert(parts, names and z[1] or string.format(chance >= 10 and "%s %d%%" or "%s %.1f%%", z[1], chance >= 10 and math.floor(chance + 0.5) or chance))
    end
    held[key] = table.concat(parts, ", ")
  end
  return held[key]
end

local function In(list, item)
  for _, v in ipairs(list or {}) do
    if v == item then return true end
  end
  return false
end

-- crafts of a step still to do at `skill`, up to `upto` (the route's end when not given): all
-- of them when the step lies within, none when it lies outside, else the points in between
function ns.CraftsLeft(step, skill, upto)
  upto = math.min(upto or step.to, step.to)
  if skill <= step.from and upto >= step.to then return step.crafts end
  if skill >= upto or upto <= step.from then return 0 end
  local n = 0
  for point = math.max(skill, step.from), upto - 1 do n = n + (step.per[point - step.from + 1] or 0) end
  return math.min(step.crafts, math.max(1, math.ceil(n - 0.001)))
end

-- `upto` stops the route at that skill (the route's target when not given): a part of it
function ns.Tailor(plan, skill, have, upto)
  upto = math.min(upto or plan.target, plan.target)
  local own, stock, known = {}, {}, {}     -- what is left of `have`; made and not used yet; item -> how an earlier step makes it
  for item, units in pairs(have or {}) do own[item] = units end
  local out = { from = skill, to = upto, steps = {}, buy = {}, make = {}, how = {}, used = {}, sell = {}, learn = {}, blocked = {}, tools = {},
                spent = 0, sold = 0, crafts = 0, unpriced = 0, fish = 0 }

  local function Get(item, need, step, depth)
    local take = math.min(own[item] or 0, need)
    if take > 0 then
      own[item] = own[item] - take
      out.used[item] = (out.used[item] or 0) + take
      need = need - take
    end
    take = math.min(stock[item] or 0, need)
    if take > 0 then
      stock[item] = stock[item] - take
      need = need - take
    end
    if need <= 0 then return end
    local how
    if In(step.craft, item) then
      how = plan.made and plan.made[item]
    elseif not In(step.buy, item) then
      how = (plan.made and plan.made[item]) or known[item]
    end
    if how and depth < 4 then
      local crafts = math.ceil(need / how[1])
      for _, use in ipairs(how[2]) do Get(use[1], use[2] * crafts, step, depth + 1) end
      out.make[item] = (out.make[item] or 0) + crafts * how[1]
      out.how[item] = how                      -- { units a craft, what a craft uses, the spell (where the route says) }
      stock[item] = (stock[item] or 0) + crafts * how[1] - need
      return
    end
    out.buy[item] = (out.buy[item] or 0) + need
  end

  -- the tools: got once (done) and held from then on (held: not left to sell, a rod being
  -- soulbound). One a later tool's recipe takes as a reagent is gone, and got again if a step
  -- after needs it
  local tools = ns.ToolsKnown and ns.ToolsKnown()
  local camp, held, gone, done = {}, {}, {}, {}
  for _, c in ipairs(plan.camp or {}) do camp[c[1]] = true end          -- the route makes those itself
  local TOOL = { buy = {}, craft = {} }
  local function Has(item) return held[item] or (not gone[item] and (own[item] or 0) > 0) end
  local function Tool(name, at, depth)
    local t = tools.made[Spelt(name)]
    if not t or not t.item or camp[t.item] or done[t.item] or depth > 3 then return end
    done[t.item] = true
    if Has(t.item) then return end
    for _, n in ipairs(t.needs or {}) do Tool(n, at, depth + 1) end      -- a tool its own recipe needs, first
    if t.spell and t.uses and #t.uses > 0 then
      for _, u in ipairs(t.uses) do
        local need = u[2]
        if tools.byItem[u[1]] and Has(u[1]) then                          -- an earlier tool, taken by this one's recipe
          if not held[u[1]] then own[u[1]] = own[u[1]] - 1; out.used[u[1]] = (out.used[u[1]] or 0) + 1 end
          held[u[1]], gone[u[1]], done[u[1]] = nil, true, nil
          need = need - 1
        end
        if need > 0 then Get(u[1], need, TOOL, 0) end
      end
      out.make[t.item] = (out.make[t.item] or 0) + 1
      out.how[t.item] = { 1, t.uses, t.spell }
    else
      out.buy[t.item] = (out.buy[t.item] or 0) + 1
    end
    held[t.item] = true
    table.insert(out.tools, { item = t.item, name = t.name, at = at, made = t.spell ~= nil })
  end

  local recipes = {}                      -- the recipes to buy, once each: a bought recipe's every stretch carries it
  for _, step in ipairs(plan.steps) do
    local crafts = step.blocked and 0 or ns.CraftsLeft(step, skill, upto)
    if step.blocked and skill < step.to and step.from < upto then              -- nothing fits at the character's level (ns.Effective)
      table.insert(out.blocked, { from = math.max(skill, step.from), to = math.min(upto, step.to), step = step })
    end
    if crafts > 0 then
      if step.learn and skill <= step.from and not recipes[step.learn[1]] then
        recipes[step.learn[1]] = true
        local owned = (own[step.learn[1]] or 0) > 0
        table.insert(out.learn, { item = step.learn[1], cost = step.learn[2], owned = owned })
        if not owned then out.spent = out.spent + step.learn[2] end
      end
      if tools and step.spell then             -- again while one got took another the step needs (a rod into a rod)
        local names = tools.spells[step.spell] or {}
        for _ = 1, #names > 1 and 3 or 1 do
          for _, name in ipairs(names) do Tool(name, math.max(skill, step.from), 0) end
        end
      end
      for _, use in ipairs(step.uses) do Get(use[1], use[2] * crafts, step, 0) end
      if step.makes then stock[step.makes[1]] = (stock[step.makes[1]] or 0) + crafts * step.makes[2] end
      out.crafts = out.crafts + crafts
      table.insert(out.steps, { step = step, crafts = crafts, from = math.max(skill, step.from), to = math.min(upto, step.to) })
    end
    if step.makes then known[step.makes[1]] = { step.makes[2], step.uses, step.spell } end
  end

  for item, units in pairs(out.buy) do
    local price = ns.BuyRow(plan, item)
    if price and price[2] == "catch" then out.fish = out.fish + units         -- a fish the player catches: a count, never copper (the fishing route)
    elseif price then out.spent = out.spent + units * price[1] else out.unpriced = out.unpriced + 1 end
  end
  for item, units in pairs(stock) do
    if units > 0 then
      out.sell[item] = units
      out.sold = out.sold + units * ((plan.sell and plan.sell[item]) or 0)
    end
  end
  return out
end

-- ================================================================ the route at the character's level
-- A step whose recipe the character cannot learn yet (its scroll asks for a character level: the
-- client's word, else the route's) is swapped for the first of the step's next-best recipes
-- (step.alt, the site's planner: the two cheapest other recipes for that stretch) that fits and
-- is not grey before the stretch starts; none fitting, the step is blocked and says so. The plan
-- comes back with its steps resolved and the rest shared, the same table while nothing changed
-- (a player below 45 was sent for Recipe: Elixir of Intellect, 8 Nov 2026). The box "Routes for
-- my level" in Interface > AddOns turns it off.
local cache = setmetatable({}, { __mode = "k" })
local function Asks(rec)
  local learn = rec.learn
  local live = learn and ns.NoteRecipeLevel and ns.NoteRecipeLevel(learn[1])
  return live or (learn and learn[3]) or rec.level
end
local function Fits(rec, from, mine)
  local need = Asks(rec)
  if need and need > mine then return false, need end
  if rec.at and rec.at[4] and rec.at[4] <= from then return false end        -- grey before the stretch: no point from it
  return true, need
end
function ns.Effective(plan)
  if not plan or not plan.steps then return plan end
  if ns.Settings and ns.Settings().levelRoutes == false then return plan end
  local mine = UnitLevel and UnitLevel("player")
  if not mine then return plan end
  local steps, sig, changed = {}, tostring(mine), false
  for _, step in ipairs(plan.steps) do
    local ok, need = Fits(step, step.from, mine)
    if ok then
      table.insert(steps, step)
    else
      local picked
      for _, alt in ipairs(step.alt or {}) do
        if Fits(alt, step.from, mine) then picked = alt; break end
      end
      local out = {}
      for k, v in pairs(step) do out[k] = v end
      if picked then
        for k, v in pairs(picked) do out[k] = v end
        out.instead, out.asks = step.recipe, need
      else
        out.blocked, out.asks = true, need
      end
      out.alt, out.others = nil, #(step.alt or {})
      table.insert(steps, out)
      sig = sig .. "|" .. step.from .. ":" .. tostring(picked and picked.spell or "x")
      changed = true
    end
  end
  local hit = cache[plan]
  if hit and hit.sig == sig then return hit.plan end
  local out = plan
  if changed then
    out = {}
    for k, v in pairs(plan) do out[k] = v end
    out.steps, out.source = steps, plan
  end
  cache[plan] = { sig = sig, plan = out }
  return out
end

-- ================================================================ the route with what the character has
-- "Use what I already have first" (Interface > AddOns, /fwcs have; on by default). For each
-- stretch of the route still ahead, the route's recipe and its next-best (step.alt, up to two)
-- are priced for THIS character: what each still has to buy at the route's prices, less what
-- the route counts its products as worth, a skill point, with what the character owns counted
-- as free. The cheapest stands in for the route's recipe, which keeps its place on a tie or a
-- near-tie (the larger of HAVE_TIE_POINT copper a point and HAVE_TIE_SHARE of its own cost with
-- nothing in hand), so that the route does not flip on a copper. With nothing owned the route
-- is never moved: a next-best is counted at no less than the route's own cost with nothing in
-- hand (the planner's word), less what the character's things save it. The route is walked in
-- order and each stretch takes from what is owned what it uses, so one stack is not counted
-- twice. Never picked: a recipe the character's level cannot learn, one learned above the
-- stretch's start or grey before it, one that gives no point somewhere in the stretch, a scroll
-- neither owned nor affordable, a reagent nothing prices; nor is a stretch moved whose product
-- a later one uses (bolts for the bags). A player farmed herbs that the route skipped for the
-- auction house's, 10 Nov 2026.
--
-- WHAT THIS READS: how many of each reagent of the route's recipes this character has, in the
-- bags (the client's count, now), the bank and the mail (as counted when each was last open,
-- Inventory.lua), its level, its gold (for a recipe scroll) and the recipes it knows; when the
-- bags, the bank, the mail, the skill, the level, the gold or the routes change, and never in
-- a fight (the last answer stands until it is over). Why: to choose the recipe of each stretch
-- that costs this character least. Kept in memory only; NEVER sent anywhere. Other characters'
-- things and the character's own auctions do not count here: the Make button cannot take from
-- them (the /fwc window still takes them off its list, as before).
-- Cost: at most three recipes a stretch, a few reagents each, priced twice (with and without
-- what is owned): some hundreds of table look-ups for a route, once per change, not per frame.
local HAVE_TIE_POINT, HAVE_TIE_SHARE = 10, 0.05
local haveGen = 0                                   -- moved on by every change that could change the answer
local haveCache = setmetatable({}, { __mode = "k" })
ns.haveWalks = 0                                    -- how many times the choice was worked out (for the tests)
function ns.HaveChanged() haveGen = haveGen + 1 end

local function Knows(spell)
  if not spell then return false end
  if IsPlayerSpell and IsPlayerSpell(spell) then return true end
  if IsSpellKnown and IsSpellKnown(spell) then return true end
  return false
end

-- this character's units of an item: the bags now, the bank and the mail as last counted
local function Owned(item)
  local inv = ns.inv
  if not inv then return 0 end
  local n = inv.Count and inv.Count(item) or 0
  local c = inv.Char and inv.Char()
  local row = c and c.items and c.items[item]
  n = n + (row and row[2] or 0)
  return n + (inv.InMail and inv.InMail(item) or (row and row[3]) or 0)
end

-- what one craft of a recipe makes is worth as the route counts it: the document's recipes (the
-- profession panel's figures), else the route's own sale price, else nothing
local function Worth(plan, cand, house)
  if plan.kind == "fishing" then return 0 end          -- what a craft makes is worth nothing to the fishing route: the fish are what count
  local row = house and house.recipes and cand.spell and house.recipes[cand.spell]
  if type(row) == "table" and type(row[2]) == "number" then return row[2] end
  local m = cand.makes
  return m and plan.sell and plan.sell[m[1]] and plan.sell[m[1]] * (m[2] or 1) or 0
end

-- copper to buy for `crafts` of a candidate, taking first from `own` then from `stock` (what the
-- steps before made), the rest made the way the route makes it or bought at its price; and what
-- it took of each. nil when a reagent has no price
local function Buys(plan, cand, crafts, own, stock)
  local tookOwn, tookStock, copper = {}, {}, 0
  local function Need(item, n, depth)
    local t = math.min(n, (own[item] or 0) - (tookOwn[item] or 0))
    if t > 0 then tookOwn[item] = (tookOwn[item] or 0) + t; n = n - t end
    t = math.min(n, (stock[item] or 0) - (tookStock[item] or 0))
    if t > 0 then tookStock[item] = (tookStock[item] or 0) + t; n = n - t end
    if n <= 0 then return true end
    local how = plan.made and plan.made[item]
    if how and depth < 3 and (In(cand.craft, item) or not In(cand.buy, item)) then
      local k = math.ceil(n / (how[1] or 1))
      for _, u in ipairs(how[2] or {}) do
        if not Need(u[1], u[2] * k, depth + 1) then return false end
      end
      return true
    end
    local row = ns.BuyRow(plan, item)
    if not row then return false end
    copper = copper + n * row[1]
    return true
  end
  for _, u in ipairs(cand.uses or {}) do
    if not Need(u[1], u[2] * crafts, 0) then return nil end
  end
  return copper, tookOwn, tookStock
end

-- one candidate of a stretch from `from`, priced: { cand, crafts, with, none, took, stockTook },
-- or nil when it cannot be had. `with`: copper out of pocket less its products' worth, what is
-- owned free; `none`: the same with nothing owned
local function Price(plan, step, cand, isRoute, ctx)
  local from = ctx.from
  if not isRoute then
    if not Fits(cand, from, ctx.level or math.huge) then return nil end
    if cand.at and cand.at[1] and cand.at[1] > from then return nil end            -- learned above the stretch's start
    for p = from, step.to - 1 do
      if ((cand.per or {})[p - step.from + 1] or 0) <= 0 then return nil end       -- no point from it there
    end
  end
  local crafts = ns.CraftsLeft({ from = step.from, to = step.to, per = cand.per or step.per, crafts = cand.crafts or step.crafts }, ctx.skill)
  local learn = 0
  -- a scroll the route buys for another stretch still ahead is bought anyway: not this one's to pay
  local elsewhere = (ctx.spells[cand.spell] or 0) - (isRoute and 1 or 0) > 0
  if cand.learn and not elsewhere and not Knows(cand.spell) and ctx.own[cand.learn[1]] == 0 then
    learn = cand.learn[2] or 0
    if not isRoute and learn > ctx.gold then return nil end                       -- a scroll not owned and not affordable
  end
  local worth = crafts * Worth(plan, cand, ctx.house)
  local with, took, stockTook = Buys(plan, cand, crafts, ctx.own, ctx.stock)
  local bare = Buys(plan, cand, crafts, {}, ctx.stock)
  if not with or not bare then return nil end
  return { cand = cand, crafts = crafts, with = with + learn - worth, none = bare + learn - worth, took = took, stockTook = stockTook }
end

-- whether a later stretch of the route uses what this one makes
local function FeedsLater(plan, i)
  local m = plan.steps[i].makes
  if not m then return false end
  for j = i + 1, #plan.steps do
    for _, u in ipairs(plan.steps[j].uses or {}) do if u[1] == m[1] then return true end end
  end
  return false
end

-- the step with a next-best in its place: the route's recipe named (over), what of the
-- character's it uses (mine, most first), what it saves a point (saves)
local SWAPPED = { "recipe", "spell", "uses", "per", "crafts", "at", "buy", "craft", "makes", "learn", "level", "cpp" }
local function Swapped(step, best, saves)
  local out = {}
  for k, v in pairs(step) do out[k] = v end
  for _, k in ipairs(SWAPPED) do out[k] = best.cand[k] end
  local mine = {}
  for item, n in pairs(best.took) do if n > 0 then table.insert(mine, { item, n }) end end
  table.sort(mine, function(a, b) if a[2] ~= b[2] then return a[2] > b[2] end return a[1] < b[1] end)
  out.alt, out.others, out.over, out.mine, out.saves = nil, #step.alt, step.recipe, mine, saves
  return out
end

function ns.UseWhatIHave(plan, skill)
  if not plan or not plan.steps then return plan end
  if ns.Settings and ns.Settings().haveFirst == false then return plan end
  skill = skill or plan.start or 1
  local level = UnitLevel and UnitLevel("player") or nil
  local hit = haveCache[plan]
  if hit and ((InCombatLockdown and InCombatLockdown()) or (hit.gen == haveGen and hit.skill == skill and hit.level == level)) then
    return hit.plan
  end
  local function Keep(out) haveCache[plan] = { gen = haveGen, skill = skill, level = level, plan = out }; return out end
  local any = false                                 -- a stretch ahead with a next-best at all
  for _, step in ipairs(plan.steps) do
    if step.alt and #step.alt > 0 and step.to > skill then any = true; break end
  end
  if not any then return Keep(plan) end
  ns.haveWalks = ns.haveWalks + 1
  local ctx = { skill = skill, level = level, gold = GetMoney and GetMoney() or 0, house = ns.inv and ns.inv.House and ns.inv.House(), stock = {}, spells = {},
                own = setmetatable({}, { __index = function(t, item) local n = Owned(item); rawset(t, item, n); return n end }) }
  for _, step in ipairs(plan.steps) do          -- the route's recipes still ahead, by stretch
    if step.spell and step.to > skill then ctx.spells[step.spell] = (ctx.spells[step.spell] or 0) + 1 end
  end
  local steps, changed = {}, false
  for i, step in ipairs(plan.steps) do
    local out = step
    if not step.blocked and ns.CraftsLeft(step, skill) > 0 then
      ctx.from = math.max(skill, step.from)
      local points = step.to - ctx.from
      local route = Price(plan, step, step, true, ctx)
      local best, bestCost
      if route and step.alt and points > 0 and not FeedsLater(plan, i) then
        local base = route.none
        for _, alt in ipairs(step.alt) do
          local p = Price(plan, step, alt, false, ctx)
          if p then
            local cost = base + math.max(0, p.none - base) - (p.none - p.with)     -- never below the route's with nothing owned
            if not bestCost or cost < bestCost then best, bestCost = p, cost end
          end
        end
        local tie = math.max(HAVE_TIE_POINT * points, HAVE_TIE_SHARE * math.abs(base))
        if best and not (bestCost < route.with - tie) then best = nil end
      end
      local chosen = best or route
      if chosen then                                -- what it takes is not there for the stretches after
        for item, n in pairs(chosen.took) do ctx.own[item] = ctx.own[item] - n end
        for item, n in pairs(chosen.stockTook) do ctx.stock[item] = ctx.stock[item] - n end
        local m = chosen.cand.makes
        if m then ctx.stock[m[1]] = (ctx.stock[m[1]] or 0) + chosen.crafts * (m[2] or 1) end
      end
      if best then out, changed = Swapped(step, best, (route.with - bestCost) / points), true end
    end
    table.insert(steps, out)
  end
  if not changed then return Keep(plan) end
  local out = {}
  for k, v in pairs(plan) do out[k] = v end
  out.steps, out.source = steps, plan.source or plan
  return Keep(out)
end

-- what moves the answer on: the bags, the bank, the mail, the skill, the level, the gold, a
-- recipe learned (the routes themselves are new tables, and so new keys, at a reload)
local haveEvents = CreateFrame and CreateFrame("Frame")
if haveEvents then
  for _, event in ipairs({ "BAG_UPDATE_DELAYED", "BANKFRAME_OPENED", "BANKFRAME_CLOSED", "PLAYERBANKSLOTS_CHANGED", "MAIL_INBOX_UPDATE",
                           "MAIL_CLOSED", "SKILL_LINES_CHANGED", "CHAT_MSG_SKILL", "PLAYER_LEVEL_UP", "PLAYER_MONEY", "NEW_RECIPE_LEARNED",
                           "LEARNED_SPELL_IN_TAB", "LEARNED_SPELL_IN_SKILL_LINE", "PLAYER_ENTERING_WORLD" }) do
    pcall(haveEvents.RegisterEvent, haveEvents, event)   -- a client without one of them refuses it: the others still count
  end
  haveEvents:SetScript("OnEvent", function() haveGen = haveGen + 1 end)
end

-- /fwcs have on | off (no word: the other way round), and the box on the options page (quiet)
function ns.HaveCommand(arg, quiet)
  local s = ns.Settings()
  local on
  if arg == "on" then on = true elseif arg == "off" then on = false else on = s.haveFirst == false end
  if on then s.haveFirst = nil else s.haveFirst = false end
  haveGen = haveGen + 1
  if not quiet and ns.Print then
    ns.Print(on and "what you already have comes first: a next-best recipe that costs you less with it stands in for the route's (/fwcs have off)"
      or "the route's own recipes, whatever you have (/fwcs have on)")
  end
  if ns.RefreshWindow then ns.RefreshWindow() end
  if ns.RoutePicked then ns.RoutePicked() end
end

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

local _, ns = ...

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
  local out = { from = skill, to = upto, steps = {}, buy = {}, make = {}, how = {}, used = {}, sell = {}, learn = {}, blocked = {},
                spent = 0, sold = 0, crafts = 0, unpriced = 0 }

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
      for _, use in ipairs(step.uses) do Get(use[1], use[2] * crafts, step, 0) end
      if step.makes then stock[step.makes[1]] = (stock[step.makes[1]] or 0) + crafts * step.makes[2] end
      out.crafts = out.crafts + crafts
      table.insert(out.steps, { step = step, crafts = crafts, from = math.max(skill, step.from), to = math.min(upto, step.to) })
    end
    if step.makes then known[step.makes[1]] = { step.makes[2], step.uses, step.spell } end
  end

  for item, units in pairs(out.buy) do
    local price = plan.buy and plan.buy[item]
    if price then out.spent = out.spent + units * price[1] else out.unpriced = out.unpriced + 1 end
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

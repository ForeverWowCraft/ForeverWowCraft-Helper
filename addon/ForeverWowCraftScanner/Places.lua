-- Where things are, and an arrow there. The client has no list of anvils, trainers or vendors.
-- The addon comes with a seed of them (Seed.lua, FWCS_SEED: the vanilla world's, from the
-- VMaNGOS database, with each map's size in yards) and notes them as the character meets them:
-- a trainer when its window opens (its profession told from what it teaches), a vendor when a
-- merchant opens (with which of the routes' items it sells), the auctioneer when the auction
-- house opens, and a crafting station (Anvil, Forge) when the profession panel says that
-- requirement is met where the character stands. Each is a map, a position and a kind, the
-- noted ones kept for the whole account (FWCS_DB.__places), nothing personal in them. The Make
-- button asks for the nearest one of what it needs and the arrow points there: TomTom's when
-- that addon is there, else this one, a texture turned by the bearing less the character's
-- facing, dragged where wanted, right-clicked away.
--
-- WHAT THIS FILE GATHERS, AND WHY (everything the addon gathers: docs/scanner-addon.md, "What the
-- addon gathers")
--   WHAT: a merchant's wares (FWCS_DB.__vendors, by the creature's id): the merchant's name, the
--     map and the spot where the character stood as the window opened, each ware's item, price as
--     asked of this character (after its reputation discount), stack, stock, whether the game lets
--     this character buy it, what it costs beside gold; the character's faction, the client's
--     build, when. A trainer's services (FWCS_DB.__trainers): its name, map and spot, each service
--     and the skill it asks for, the character's faction, the build, when. Places for the arrow
--     (FWCS_DB.__places): trainers, merchants that sell the routes' items, auctioneers, mailboxes,
--     anvils and forges, each a map, a spot and a kind.
--   WHEN: only when the player opens a merchant's, a trainer's, the auction house's or a mailbox's
--     window, or the profession panel says a station's requirement is met where the character
--     stands. Never in the background: the position is read at that moment, and only then.
--   WHY: who sells which recipe and reagent on Forever, and at what price; the skill Forever's
--     trainers teach each recipe at; where to send the arrow.
--   NEVER: no character name, level, gold, bags, chat or guild. No movement is kept: the one
--     position kept is that of the window just opened (the arrow reads where the character
--     stands to turn itself, and keeps none of it).
--   WHERE: the helper sends the merchants and the trainers (not the places, which stay here) to
--     the project's pipe, pooled with other players' sightings to know Forever's vendors and
--     trainers.
--
-- ns.Bearing asks the game nothing, for the tests.

local _, ns = ...
local House, Tracked = ns.inv.House, ns.inv.Tracked

local PREFIX = "|cff" .. ns.BRAND.gold .. "ForeverWowCraft|r: "

-- ================================================================ the map
-- where the character stands: map, x, y (fractions of the map), or nil (an instance, no map)
local function Here()
  if not (C_Map and C_Map.GetBestMapForUnit and C_Map.GetPlayerMapPosition) then return end
  local ok, map = pcall(C_Map.GetBestMapForUnit, "player")
  if not ok or not map then return end
  local ok2, pos = pcall(C_Map.GetPlayerMapPosition, map, "player")
  if not ok2 or type(pos) ~= "table" then return end
  local x, y = pos.x, pos.y
  if pos.GetXY then x, y = pos:GetXY() end
  if not (x and y) or (x == 0 and y == 0) then return end
  return map, x, y
end

-- a map's size in yards { width, height }, for distances: the seed's, else the client's; nil
-- when neither can say
local sizes = {}
local function Size(map)
  if sizes[map] == nil then
    sizes[map] = false
    local seed = FWCS_SEED and FWCS_SEED.sizes and FWCS_SEED.sizes[map]
    if seed and seed[1] and seed[2] then sizes[map] = { seed[1], seed[2] } end
    if C_Map and C_Map.GetMapWorldSize then
      local ok, w, h = pcall(C_Map.GetMapWorldSize, map)
      if ok and w and h and w > 0 and h > 0 then sizes[map] = { w, h } end
    end
    if not sizes[map] and C_Map and C_Map.GetWorldPosFromMapPos and CreateVector2D then
      local ok, _, a = pcall(C_Map.GetWorldPosFromMapPos, map, CreateVector2D(0, 0))
      local ok2, _, b = pcall(C_Map.GetWorldPosFromMapPos, map, CreateVector2D(1, 1))
      if ok and ok2 and a and b and a.x and b.x then sizes[map] = { math.abs(b.y - a.y), math.abs(b.x - a.x) } end
    end
  end
  return sizes[map] or nil
end

-- yards between two points of a map, or nil without the map's size
local function Distance(map, x1, y1, x2, y2)
  local size = Size(map)
  if not size then return nil end
  local dx, dy = (x2 - x1) * size[1], (y2 - y1) * size[2]
  return math.sqrt(dx * dx + dy * dy)
end

-- a map position in the world: continent, x (north), y (west), from the seed's rectangle of
-- the map (world = { continent, x0, y0, x1, y1 }: the seed's maker puts things on maps the
-- other way round); nil for a map the seed does not know
local function World(map, fx, fy)
  local w = FWCS_SEED and FWCS_SEED.world and FWCS_SEED.world[map]
  if not w then return end
  return w[1], w[4] - fy * (w[4] - w[2]), w[5] - fx * (w[5] - w[3])
end

-- yards between two places on any maps of one continent, through the world; nil across
-- continents (a boat or a zeppelin, not a thing to measure) or without the seed's rectangles.
-- Without it, the nearest on another map was the first fitting row of the seed: Westfall was
-- sent to Brill for Journeyman First Aid (6 Nov 2026)
local function Far(map1, x1, y1, map2, x2, y2)
  local c1, a1, b1 = World(map1, x1, y1)
  local c2, a2, b2 = World(map2, x2, y2)
  if not c1 or c1 ~= c2 then return nil end
  return math.sqrt((a1 - a2) ^ 2 + (b1 - b2) ^ 2)
end
ns.Far = Far

-- whether a place `d` yards off (nil: not measurable) beats the best so far: the nearer
-- measured one; a measured one over one that is not; else the one seen last
local function Nearer(d, p, bestD, best)
  if not best then return true end
  if d and bestD then return d < bestD end
  if d or bestD then return d ~= nil end
  return (p.t or 0) > (best.t or 0)
end

-- The way to turn an arrow that points up so that it points from (x1, y1) to (x2, y2), for a
-- character facing `facing` (radians, 0 north, turning left positive, as GetPlayerFacing):
-- radians, turning left positive, as SetRotation takes. Map x grows east, y grows south;
-- `size` scales the two when the map is not square.
function ns.Bearing(x1, y1, x2, y2, facing, size)
  local dx, dy = (x2 - x1) * (size and size[1] or 1), (y2 - y1) * (size and size[2] or 1)
  local a = math.atan2(dx, -dy)                -- right of north, turning right positive
  if math.abs(a) > 7 then a = math.rad(a) end  -- a client whose atan2 gives degrees
  return -a - (facing or 0)
end

local function MapName(map)
  if C_Map and C_Map.GetMapInfo then
    local ok, info = pcall(C_Map.GetMapInfo, map)
    if ok and type(info) == "table" and info.name then return info.name end
  end
  return "map " .. tostring(map)
end

-- ================================================================ the places
-- FWCS_DB.__places: { { map, x, y, kind, what, name, t, sells = { item, ... } }, ... }
-- kind "station": what = the requirement's name (Anvil, Forge); "trainer": what = the
-- profession; "vendor": what = the merchant's name, sells = the routes' items it sells;
-- "auction": the auctioneer. One place of a kind and what within 40 yards: seen again.
local function Places()
  FWCS_DB.__places = FWCS_DB.__places or {}
  return FWCS_DB.__places
end

-- the seed's places, as tables like the noted ones, made once: a row of FWCS_SEED.places is
-- { map, x, y, kind, what, name, extra, reach }, extra how far a trainer's rank training reaches
-- (upto: 75 to 300; 0 for a specialist who teaches recipes only) or the items a vendor sells;
-- reach (trainers, when the seed has it): the highest skill a recipe seen taught there asks for
local seeded, seededFrom                  -- made from the rows once; again when the rows are another table
local function Seeded()
  local rows = FWCS_SEED and FWCS_SEED.places or {}
  if seeded and seededFrom == rows then return seeded end
  seeded, seededFrom = {}, rows
  for _, r in ipairs(rows) do
    local p = { map = r[1], x = r[2], y = r[3], kind = r[4], what = r[5], name = r[6], seed = true }
    if type(r[7]) == "number" then p.upto = r[7] elseif type(r[7]) == "table" then p.sells = r[7]
    elseif type(r[7]) == "string" then p.faction = r[7] end          -- a quest giver's faction
    if type(r[8]) == "number" and p.kind == "trainer" then p.reach = r[8] end    -- how far its recipes go, as senders saw it; none: unknown
    if type(r[9]) == "table" and p.kind == "trainer" then                        -- the spells of the routes' recipes it was seen teaching, as a set
      p.spells = {}
      for _, id in ipairs(r[9]) do p.spells[id] = true end
    end
    table.insert(seeded, p)
  end
  return seeded
end

-- The special teachers (FWCS_SEED.special, by creature id: a quest or a character level first,
-- teachers.py; Odd Child, 10 Nov 2026) are no trainer places: never noted as one, and a note
-- made before is passed over. A note holds the name the client gave, not the id: it is matched
-- by the seed's name, or by the client's own name for that id in the trainers kept for the
-- helper. nil with a seed that has no list (one older than 1.7.7)
local function SpecialNames()
  local special = FWCS_SEED and FWCS_SEED.special
  if type(special) ~= "table" or next(special) == nil then return nil end
  local names, kept = {}, FWCS_DB.__trainers
  for id, name in pairs(special) do
    if type(name) == "string" and name ~= "" then names[name] = true end
    local t = type(kept) == "table" and kept[id]
    if type(t) == "table" and type(t.name) == "string" then names[t.name] = true end
  end
  return names
end

-- every place: the seed's and the noted ones. Made again only when a place was noted (the list
-- was copied, some 1,700 rows, on every look for the nearest, several times a verdict)
local all, allSeed, allMine, allN
local function All()
  local seed, mine = Seeded(), Places()
  if all and allSeed == seed and allMine == mine and allN == #mine then return all end
  local out = {}
  local hidden = SpecialNames()
  for _, p in ipairs(seed) do table.insert(out, p) end
  for _, p in ipairs(mine) do
    if not (hidden and p.kind == "trainer" and p.name and hidden[p.name]) then table.insert(out, p) end
  end
  all, allSeed, allMine, allN = out, seed, mine, #mine
  return out
end

local function In(list, item)
  for _, v in ipairs(list or {}) do if v == item then return true end end
  return false
end

local function Note(kind, what, extra)
  local map, x, y = Here()
  if not map then return end
  all = nil                                -- the list of every place made again at the next look (the count is a second guard)
  ns.notedAt = time()                      -- something to save (Remind.lua)
  for _, p in ipairs(Places()) do
    if p.map == map and p.kind == kind and p.what == what then
      local d = Distance(map, p.x, p.y, x, y)
      if (d and d < 40) or (not d and math.abs(p.x - x) < 0.01 and math.abs(p.y - y) < 0.01) then
        p.t = time()
        for k, v in pairs(extra or {}) do
          if k == "sells" then
            p.sells = p.sells or {}
            for _, item in ipairs(v) do if not In(p.sells, item) then table.insert(p.sells, item) end end
          elseif k == "reach" then
            if not p.reach or v > p.reach then p.reach = v end          -- the union over visits: a filter may hide recipes this time
          else
            p[k] = v
          end
        end
        return p
      end
    end
  end
  local p = { map = map, x = x, y = y, kind = kind, what = what, t = time() }
  for k, v in pairs(extra or {}) do p[k] = v end
  table.insert(Places(), p)
  return p
end
ns.NotePlace = Note

local function Npc() return UnitName and UnitName("npc") or nil end

-- What a merchant's or a trainer's window is kept under: the creature's id out of the unit's
-- GUID. Not one vendor window was kept in a day of 1.6.5+ on Forever while the same vendors
-- were noted as places (7 Nov 2026): the strict GUID pattern of before did not fit this
-- client's. Now the id is the number before the last (hex) part, whatever comes before it;
-- and with no GUID at all, the creature's name, so that nothing seen is lost
local function NpcKey()
  local guid = UnitGUID and UnitGUID("npc")
  local id = guid and (tonumber(guid:match("^Creature%-%d+%-%d+%-%d+%-%d+%-(%d+)%-")) or tonumber(guid:match("%-(%d+)%-%x+$")))
  if id then return id end
  local name = Npc()
  return name and name ~= "" and name or nil
end

-- the names a profession goes by, spelt plainly: the routes' and the client's
local function Spellings(plan)
  local out = { [ns.inv.Spelt(plan.profession)] = true, [ns.inv.Spelt(ns.Title(plan.profession))] = true }
  if C_TradeSkillUI and C_TradeSkillUI.GetTradeSkillDisplayName and plan.skill_line then
    local ok, shown = pcall(C_TradeSkillUI.GetTradeSkillDisplayName, plan.skill_line)
    if ok and shown and shown ~= "" then out[ns.inv.Spelt(shown)] = true end
  end
  return out
end

-- a trainer's window: its profession from the skill its services ask for, or from the routes'
-- recipes among them; what of the routes it teaches is kept, by name. How far it teaches
-- (upto) is its rank training, told by the service's name (the seed's, in every language:
-- "Expert Engineer" reaches 225); with no rank among the services, the highest skill asked for
-- (the old way, which counted a specialist's recipes: Oglethorpe teaches no rank, and his
-- gnomish recipes at 240 made him the trainer for Expert, 12 Oct 2026)
local function NoteTrainer()
  local house = House()
  if not (house and GetNumTrainerServices and GetTrainerServiceInfo) then return end
  local recipes, spellings = {}, {}
  for _, plan in pairs(house.plans or {}) do
    spellings[plan.profession] = Spellings(plan)
    for _, step in ipairs(plan.steps or {}) do recipes[ns.RecipeName(step)] = plan.profession end
  end
  local ranks = FWCS_SEED and FWCS_SEED.ranks or {}
  local votes, teaches, upto, ranked, top = {}, {}, 0, 0, 0       -- top: the highest skill a recipe (no rank) asks for
  for i = 1, GetNumTrainerServices() do
    local name, sub = GetTrainerServiceInfo(i)
    local reach = name and (ranks[name] or (sub and (ranks[sub .. " " .. name] or ranks[name .. " " .. sub])))
    if reach and reach > ranked then ranked = reach end
    if name and not reach and GetTrainerServiceSkillReq then
      local _, level = GetTrainerServiceSkillReq(i)
      if type(level) == "number" and level > top and level <= 300 then top = math.floor(level) end
    end
    if name and recipes[name] then
      votes[recipes[name]] = (votes[recipes[name]] or 0) + 1
      table.insert(teaches, name)
    end
    if GetTrainerServiceSkillReq then
      local skill, level = GetTrainerServiceSkillReq(i)
      if skill and skill ~= "" then
        local spelt = ns.inv.Spelt(skill)
        for profession, names in pairs(spellings) do
          if names[spelt] then votes[profession] = (votes[profession] or 0) + 1 end
        end
        if type(level) == "number" and level > upto then upto = level end     -- the highest skill its teaching asks for
      end
    end
  end
  local best, n = nil, 0
  for profession, v in pairs(votes) do if v > n then best, n = profession, v end end
  -- a special teacher is no trainer place (SpecialNames); what it teaches is still kept below
  local id = NpcKey()
  local special = FWCS_SEED and FWCS_SEED.special
  local names = type(id) == "string" and SpecialNames()
  if (type(special) == "table" and id ~= nil and special[id] ~= nil) or (names and names[id]) then
    best, all = nil, nil                   -- the list of every place made again: a note made before is passed over by this name
  end
  if best then Note("trainer", best, { name = Npc(), teaches = teaches, upto = ranked > 0 and ranked or (upto > 0 and upto or nil), reach = top > 0 and top or nil }) end
  -- the trainer's whole list, by the creature's id, for the helper to send (nothing of the
  -- character): each service and the skill it asks for. Forever keeps the skill a recipe is
  -- taught at on the server, which the client's tables do not say, and the routes planned on
  -- vanilla's levels were wrong by it (Embossed Leather Gloves). The
  -- union over visits: a service a filter hid this time stays from the last
  local map, x, y = Here()
  if id and map and GetTrainerServiceSkillReq then
    local asks, counts, skillName = {}, {}, nil
    for i = 1, GetNumTrainerServices() do
      local name, _, category = GetTrainerServiceInfo(i)
      local skill, level = GetTrainerServiceSkillReq(i)
      if name and category ~= "header" and type(skill) == "string" and skill ~= "" and type(level) == "number" then
        asks[name] = math.floor(level)
        counts[skill] = (counts[skill] or 0) + 1
      end
    end
    for s, c in pairs(counts) do if not skillName or c > counts[skillName] then skillName = s end end
    if skillName then
      ns.notedAt = time()
      FWCS_DB.__trainers = FWCS_DB.__trainers or {}
      local t = FWCS_DB.__trainers[id] or { teaches = {} }
      local mine = UnitFactionGroup and UnitFactionGroup("player")
      t.name, t.map, t.x, t.y, t.t, t.skill, t.faction = Npc() or "?", map, x, y, time(), skillName, (mine == "Alliance" or mine == "Horde") and mine or ""
      if GetBuildInfo then local _, build = GetBuildInfo(); t.build = build end
      for name, level in pairs(asks) do t.teaches[name] = level end
      FWCS_DB.__trainers[id] = t
    end
  end
end

-- A merchant slot as the old GetMerchantItemInfo gave it (name, texture, price, stack, how many
-- in stock, purchasable, usable, extended cost), from that global where the client has it, else
-- from C_MerchantFrame.GetItemInfo's table: Forever's client (Interface 16001) has only the
-- latter, and until 1.7.4 no ware or price was read there (9 Nov 2026). Nothing for an empty slot
-- or a client with neither. Shop.lua's list reads prices by it too.
function ns.MerchantItemInfo(i)
  if GetMerchantItemInfo then return GetMerchantItemInfo(i) end
  local info = C_MerchantFrame and C_MerchantFrame.GetItemInfo and C_MerchantFrame.GetItemInfo(i)
  if type(info) ~= "table" then return end
  return info.name, info.texture, info.price, info.stackCount, info.numAvailable, info.isPurchasable, info.isUsable, info.hasExtendedCost
end

-- a merchant: which of the routes' items it sells
-- A merchant's window: the vendor is noted as a place (the route's items it sells, for the
-- arrow), and its whole stock is kept by the creature's id (FWCS_DB.__vendors, since 1.6.5):
-- each slot's item, price, stack, how many are in stock (-1: as many as asked for), whether
-- the character may buy it, and what it costs beside gold (a trade faction's Favor); where the
-- vendor stood, the character's faction, when, and the client's build. The helper sends that
-- to the pipe, where the core learns who sells which recipe on Forever, which the client's
-- tables do not say (6 Nov 2026). Nothing of the character goes in; an item it may not buy
-- for its reputation is recorded as not usable, not left out.
local function NoteVendor()
  if not (GetMerchantNumItems and GetMerchantItemLink) then return end
  local tracked, sells, wares, n = Tracked(), {}, {}, GetMerchantNumItems()
  for i = 1, n do
    local link = GetMerchantItemLink(i)
    local item = link and tonumber(link:match("item:(%d+)"))
    if item then
      if tracked[item] and not In(sells, item) then table.insert(sells, item) end
      local _, _, price, stack, available, _, usable, extended = ns.MerchantItemInfo(i)
      if price ~= nil then
        local row = { price = tonumber(price) or 0, stack = tonumber(stack) or 1, n = tonumber(available) or -1, usable = usable and true or false }
        if extended and GetMerchantItemCostInfo and GetMerchantItemCostItem then
          local count = GetMerchantItemCostInfo(i)
          for j = 1, tonumber(count) or 0 do
            local _, value, costLink = GetMerchantItemCostItem(i, j)
            local costItem = costLink and (tonumber(costLink:match("item:(%d+)")) or tonumber(costLink:match("currency:(%d+)")))
            if costItem and value then row.cost = row.cost or {}; row.cost[costItem] = value end
          end
        end
        wares[item] = row
      end
    end
  end
  local npc = Npc() or "?"
  if #sells > 0 then Note("vendor", npc, { name = npc, sells = sells }) end
  local id = NpcKey()
  local map, x, y = Here()
  if id and map and next(wares) then
    ns.notedAt = time()
    FWCS_DB.__vendors = FWCS_DB.__vendors or {}
    local v = FWCS_DB.__vendors[id] or { items = {} }
    local mine = UnitFactionGroup and UnitFactionGroup("player")
    v.name, v.map, v.x, v.y, v.t, v.faction = npc, map, x, y, time(), (mine == "Alliance" or mine == "Horde") and mine or ""
    if GetBuildInfo then local _, build = GetBuildInfo(); v.build = build end
    for item, row in pairs(wares) do row.t = v.t; v.items[item] = row end      -- the union: an item sold out this time stays, with its last sighting
    FWCS_DB.__vendors[id] = v
  end
end

-- The nearest place of a kind: of `what` when given, selling `item` when given, teaching as
-- far as `upto` when given (a trainer that says how far). Returns the place, the yards to it
-- (nil when the map's size is unknown), and whether it is on this map (else the one seen last,
-- anywhere; the seed's count as seen first).
-- the character's faction, when the client says; a seed place in the other faction's own zone
-- (FWCS_SEED.sides) is not for it. What was noted in person was reached, and counts
local function Mine()
  local f = UnitFactionGroup and UnitFactionGroup("player")
  if f == "Alliance" or f == "Horde" then return f end
end
local function Reachable(p, mine)
  if p.faction and mine and p.faction ~= mine then return false end     -- a quest giver of the other faction
  if not p.seed or not mine then return true end
  local side = FWCS_SEED and FWCS_SEED.sides and FWCS_SEED.sides[p.map]
  return side == nil or side == mine
end

-- `need` (a recipe to learn: the skill it is learned at) puts a trainer seen to teach no recipe
-- that high (its reach, the seed's or the player's own note) after the ones that may; with both
-- trainers' reach known, the nearer comes first, not the lower rank band (Randal Worth, to 75
-- for ranks and 50 for recipes, was sent for a recipe at 70 before Simon Tanner a few yards
-- off). No reach known: as before. `spell` (that recipe's spell id):
-- where a reachable trainer is seen to teach it (the seed's list), only those are asked, the
-- nearest, whatever their rank band or reach; where none is known to, as above.
function ns.NearestPlace(kind, what, item, upto, need, spell)
  local map, x, y = Here()
  local mine = Mine()
  local only = false
  if spell ~= nil and what ~= nil then
    for _, p in ipairs(All()) do
      if p.kind == kind and p.what == what and p.spells and p.spells[spell] and Reachable(p, mine) then only = true; break end
    end
  end
  -- Asked how far: the trainer of that rank before one that teaches further, then the nearer.
  -- Forever's trainers teach their own rank's band (Stormwind: Lawrence Schneider to 75,
  -- Sellandus to 150, Georgio Bolero to 225): a tailor of 120 sent to the artisan's found
  -- nothing to learn there (8 Nov 2026)
  local function Better(p, d, bp, bd)
    if not bp then return true end
    if upto ~= nil and not only and (p.upto or 0) ~= (bp.upto or 0) and not (need and p.reach and bp.reach) then return (p.upto or 0) < (bp.upto or 0) end
    return Nearer(d, p, bd, bp)
  end
  -- asked how far (a rank to train): a trainer that says it teaches that far comes first, on
  -- this map or another (the nearest through the world: Far); one that does not say (noted
  -- before the addon kept that, 11 Oct 2026: it led to the apprentice trainer) is a last
  -- resort; one that says 0 (a specialist, recipes only) never
  local best, bestD, other, otherD, maybe, maybeD, maybeOther, maybeOtherD
  for _, p in ipairs(All()) do
    if p.kind == kind and (what == nil or p.what == what) and (item == nil or In(p.sells, item)) and Reachable(p, mine)
       and (not only or (p.spells and p.spells[spell])) then
      local fits = only or upto == nil or (p.upto ~= nil and p.upto >= upto)
      local unsure = not only and upto ~= nil and p.upto == nil
      if not only and need ~= nil and p.reach ~= nil and p.reach < need and (fits or unsure) then fits, unsure = false, true end    -- seen teaching nothing so high: a last resort
      if fits or unsure then
        if map and p.map == map then
          local d = Distance(map, p.x, p.y, x, y) or (math.abs(p.x - x) + math.abs(p.y - y)) * 100000
          if fits then
            if Better(p, d, best, bestD) then best, bestD = p, d end
          elseif not maybe or d < maybeD then
            maybe, maybeD = p, d
          end
        else
          local d = map and Far(map, x, y, p.map, p.x, p.y) or nil
          if fits then
            if Better(p, d, other, otherD) then other, otherD = p, d end
          elseif Nearer(d, p, maybeOtherD, maybeOther) then
            maybeOther, maybeOtherD = p, d
          end
        end
      end
    end
  end
  if best then return best, Distance(map, best.x, best.y, x, y), true end
  if other then return other, otherD, false end
  if maybe then return maybe, Distance(map, maybe.x, maybe.y, x, y), true end
  if maybeOther then return maybeOther, maybeOtherD, false end
end

-- ================================================================ the arrow
local arrow, target, dismissed        -- target = { map, x, y, title, note, profession } or { none = true, ... }; dismissed: by a right-click, until ns.ArrowBack
local ARROW, QUESTION, HAMMER = "Interface\\Minimap\\MinimapArrow", "Interface\\Icons\\INV_Misc_QuestionMark", "Interface\\Icons\\INV_Hammer_20"

-- the profession served, the title (less the profession's name when it starts with it: "Tailoring
-- trainer: X" under "Tailoring" reads "Trainer: X"), the way (no line when it is here), and the
-- note (what the Make button says) in brackets
local function Describe(d, here)
  if not target then return "" end
  local lines = {}
  local title = target.title
  if target.profession then
    table.insert(lines, target.profession)
    local rest = title:match("^" .. target.profession:gsub("%p", "%%%0") .. " (.+)$")
    if rest then title = rest:sub(1, 1):upper() .. rest:sub(2) end
  end
  table.insert(lines, title)
  if target.none then                                                     -- nothing to point at: no way to say
  elseif not here then table.insert(lines, "in " .. MapName(target.map) .. (d and string.format(", about %d yd", math.floor(d + 0.5)) or ""))
  elseif d and d >= 10 then table.insert(lines, string.format("%d yd", math.floor(d + 0.5))) end
  if target.note then table.insert(lines, "(" .. target.note .. ")") end
  if target.aside then                                                    -- the note: folded to its title; a click opens it
    if ns.Settings().asideOpen then table.insert(lines, "|cffb0b0b0v " .. target.aside.text .. ": " .. (target.aside.detail or "") .. "|r")
    else table.insert(lines, "|cffb0b0b0> " .. target.aside.text .. "|r") end
  end
  return table.concat(lines, "\n")
end

-- the arrow's picture: the arrow; a question mark when there is nothing to point at; a
-- hammer when the words are something to make here
local function Symbol(which)
  if arrow.symbol == which then return end
  arrow.symbol = which
  arrow.tex:SetTexture(which == "none" and QUESTION or which == "make" and HAMMER or ARROW)
  if which == "arrow" then arrow.tex:SetTexCoord(0, 1, 0, 1) else arrow.tex:SetTexCoord(0.08, 0.92, 0.08, 0.92); arrow.tex:SetRotation(0) end
end

local function Update()
  if not (arrow and target) then return end
  if target.none then
    Symbol(target.symbol or "none")
    arrow.tex:Show()
    arrow.text:SetText(Describe(nil, true))
    return
  end
  Symbol("arrow")
  local map, x, y = Here()
  if not map then
    arrow.tex:Hide()
    arrow.text:SetText(Describe(nil, true))           -- no way to say here (no map): the words, and the note
    return
  end
  if map ~= target.map then
    -- another map: the arrow points the way through the world, as the crow flies, when both
    -- are on one continent (the seed's rectangles: World), with the map's name and about how
    -- far; across continents, or off the seed's maps, the words alone. Until 1.6.0 the arrow
    -- went with the map's name only, and the player in Westfall sent to Goldshire had the
    -- words and no arrow (6 Nov 2026: "the arrow is surprisingly important")
    local c1, n1, w1 = World(map, x, y)
    local c2, n2, w2 = World(target.map, target.x, target.y)
    if c1 and c1 == c2 then
      arrow.tex:Show()
      local facing = GetPlayerFacing and GetPlayerFacing() or 0
      arrow.tex:SetRotation(ns.Bearing(0, 0, w1 - w2, n1 - n2, facing))     -- east is less west, south is less north
      arrow.text:SetText(Describe(math.sqrt((n1 - n2) ^ 2 + (w1 - w2) ^ 2), false))
    else
      arrow.tex:Hide()
      arrow.text:SetText(Describe(nil, false))
    end
    return
  end
  arrow.tex:Show()
  local facing = GetPlayerFacing and GetPlayerFacing() or 0
  arrow.tex:SetRotation(ns.Bearing(x, y, target.x, target.y, facing, Size(map)))
  arrow.text:SetText(Describe(Distance(map, x, y, target.x, target.y), true))
end

-- where the arrow sits: where it was dragged to, kept across reloads and logins (testers lost
-- it at every reload, 12 Oct 2026), else the top of the screen, clear of the auction house and
-- the profession window
local function Place()
  local pos = ns.Settings().arrowPos
  arrow:ClearAllPoints()
  if pos then arrow:SetPoint(pos[1], UIParent, pos[2], pos[3], pos[4]) else arrow:SetPoint("TOP", UIParent, "TOP", 0, -120) end
end

local function Build()
  arrow = CreateFrame("Frame", "ForeverWowCraftArrow", UIParent)
  arrow:SetSize(56, 56)
  Place()
  arrow:SetFrameStrata("HIGH")                       -- above the house and the profession window, when they do reach it
  arrow:SetMovable(true)
  arrow:EnableMouse(true)
  if arrow.SetHitRectInsets then arrow:SetHitRectInsets(-40, -40, 0, -110) end   -- the words under it take clicks too (12 Oct 2026: a click on the note did nothing)
  arrow:RegisterForDrag("LeftButton")
  arrow:SetScript("OnDragStart", function(a) a:StartMoving(); a.moved = true end)
  arrow:SetScript("OnDragStop", function(a)
    a:StopMovingOrSizing()
    local point, _, relPoint, x, y = a:GetPoint()
    ns.Settings().arrowPos = { point, relPoint, x, y }
  end)
  arrow:SetScript("OnMouseUp", function(a, b)
    if b == "RightButton" then dismissed = true; arrow:Hide()
    elseif b == "LeftButton" and not rawget(a, "moved") and target and target.aside then   -- a click (no drag): the note opened or folded
      local s = ns.Settings()
      s.asideOpen = not s.asideOpen
      Update()
    end
    a.moved = nil
  end)
  arrow:SetScript("OnEnter", function()
    GameTooltip:SetOwner(arrow, "ANCHOR_RIGHT")
    GameTooltip:AddLine("ForeverWowCraft: the way there")
    GameTooltip:AddLine("Drag to move (it stays there). Click to open or fold the note under it. Right-click to put away: it is back when you open a vendor, a trainer, an auctioneer, a mailbox or the profession window, or click Make. /fwcs arrow off turns it off, /fwcs arrow reset puts it back at the top.", 1, 1, 1, true)
    GameTooltip:Show()
  end)
  arrow:SetScript("OnLeave", function() GameTooltip:Hide() end)
  arrow.tex = arrow:CreateTexture(nil, "ARTWORK")
  arrow.tex:SetAllPoints()
  arrow.tex:SetTexture("Interface\\Minimap\\MinimapArrow")
  arrow.text = arrow:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  arrow.text:SetPoint("TOP", arrow, "BOTTOM", 0, -2)
  arrow.text:SetJustifyH("CENTER")
  local since = 0
  arrow:SetScript("OnUpdate", function(_, dt)
    since = since + (dt or 0)
    if since < 0.1 then return end
    since = 0
    Update()
  end)
  arrow:Hide()
end

local tomtom                          -- TomTom's waypoint, to take back
local function ViaTomTom(place, title)
  if not (TomTom and TomTom.AddWaypoint) then return false end
  if tomtom and TomTom.RemoveWaypoint then pcall(TomTom.RemoveWaypoint, TomTom, tomtom) end
  local ok, uid = pcall(TomTom.AddWaypoint, TomTom, place.map, place.x, place.y, { title = "ForeverWowCraft: " .. title, persistent = false, crazy = true })
  tomtom = ok and uid or nil
  return ok
end

-- the arrow to a place, with a title and a note under it (what the Make button says);
-- `again` brings back one put away
function ns.SetArrow(place, title, again, note, profession, symbol)
  if ns.Settings().arrow == false then return end
  if target and target.place == place and target.title == title and not again then
    if target.note ~= note or target.profession ~= profession or target.symbol ~= symbol then target.note, target.profession, target.symbol = note, profession, symbol; Update() end
    if not dismissed and arrow and not arrow:IsShown() then arrow:Show() end
    return
  end
  if place then
    target = { place = place, map = place.map, x = place.x, y = place.y, title = title, note = note, profession = profession }
  else
    target = { none = true, title = title, note = note, profession = profession, symbol = symbol }   -- nothing to point at: the words, under a question mark or a hammer
  end
  if again then dismissed = false end
  if dismissed then                            -- put away by a right-click: the target is kept, nothing is shown until ns.ArrowBack
    if arrow then arrow:Hide() end             -- (a loot that moved the step brought it back before: a player who put it away did
    return                                     -- not want it on every drop, 7 Nov 2026)
  end
  if tomtom and TomTom and TomTom.RemoveWaypoint then pcall(TomTom.RemoveWaypoint, TomTom, tomtom); tomtom = nil end
  if place and ViaTomTom(place, title) then return end
  if not arrow then Build() end
  arrow:Show()
  Update()
end

-- The arrow put away by a right-click, back where it would point: when a merchant's, a
-- trainer's, an auctioneer's or a mailbox's window opens, or the profession window (the
-- player is at the business the arrow serves); the Make button and Keep arrow bring it back
-- too (SetArrow with `again`). A loot or a bag change does not.
function ns.ArrowBack()
  if not dismissed or not target then return end
  dismissed = false
  if not target.none and target.place and ViaTomTom(target.place, target.title) then return end
  if not arrow then Build() end
  arrow:Show()
  Update()
end

-- the note under the arrow, { text, detail }, or nil for none
function ns.SetArrowAside(aside)
  if not target then return end
  if (target.aside and target.aside.text or nil) ~= (aside and aside.text or nil) or (target.aside and target.aside.detail or nil) ~= (aside and aside.detail or nil) then
    target.aside = aside
    Update()
  end
end

function ns.ClearArrow()
  target = nil
  if tomtom and TomTom and TomTom.RemoveWaypoint then pcall(TomTom.RemoveWaypoint, TomTom, tomtom); tomtom = nil end
  if arrow then arrow:Hide() end
end

-- /fwcs arrow: where the arrow points; `on` and `off` set it. /fwcs places: what has been seen
function ns.ArrowCommand(arg)
  local s = ns.Settings()
  if arg == "off" then
    s.arrow = false
    ns.ClearArrow()
    print(PREFIX .. "the arrow is off (/fwcs arrow on brings it back)")
  elseif arg == "on" then
    s.arrow = nil
    print(PREFIX .. "the arrow is on: the Make button points it at what it needs")
  elseif arg == "reset" then
    s.arrowPos = nil
    if arrow then Place() end
    print(PREFIX .. "the arrow is back at the top of the screen")
  elseif s.arrow == false then
    print(PREFIX .. "the arrow is off: /fwcs arrow on brings it back")
  elseif not target then
    print(PREFIX .. "the arrow points at nothing yet: the Make button sets it when the step needs a trainer, a vendor, an auctioneer or a crafting station")
  else
    local map, x, y = Here()
    local d = not target.none and map and map == target.map and Distance(map, x, y, target.x, target.y)
    local where = target.none and nil or (map and map ~= target.map) and ("in " .. MapName(target.map)) or d and string.format("%d yd", math.floor(d + 0.5)) or nil
    print(PREFIX .. (target.none and "the arrow shows: " or "the arrow points at ") .. target.title .. (where and (", " .. where) or "")
      .. (tomtom and " (as a TomTom waypoint)" or "")
      .. (dismissed and " (put away by a right-click: a vendor, a trainer, an auctioneer, a mailbox or the profession window opened brings it back)" or "")
      .. ". /fwcs arrow off turns it off.")
  end
end
function ns.PlacesCommand()
  local counts, seed = {}, 0
  for _, p in ipairs(Places()) do counts[p.kind] = (counts[p.kind] or 0) + 1 end
  for _ in ipairs(Seeded()) do seed = seed + 1 end
  print(PREFIX .. string.format("places known: %d trainers, %d vendors, %d auctioneers, %d crafting stations, %d mailboxes seen, and %d that the addon came with.",
    counts.trainer or 0, counts.vendor or 0, counts.auction or 0, counts.station or 0, counts.mailbox or 0, seed))
  local windows, wares, taught, services = 0, 0, 0, 0
  for _, v in pairs(FWCS_DB.__vendors or {}) do windows = windows + 1; for _ in pairs(v.items or {}) do wares = wares + 1 end end
  for _, t in pairs(FWCS_DB.__trainers or {}) do taught = taught + 1; for _ in pairs(t.teaches or {}) do services = services + 1 end end
  local scrolls = 0
  for _ in pairs(FWCS_DB.__recipes or {}) do scrolls = scrolls + 1 end
  print(PREFIX .. string.format("kept for the helper: %d merchant window(s), %d wares; %d trainer window(s), %d services; %d recipe scroll(s) with the level each asks for.", windows, wares, taught, services, scrolls))
end

local frame = CreateFrame("Frame")
for _, event in ipairs({ "TRAINER_SHOW", "TRAINER_UPDATE", "MERCHANT_SHOW", "MERCHANT_UPDATE", "AUCTION_HOUSE_SHOW", "MAIL_SHOW" }) do
  pcall(frame.RegisterEvent, frame, event)
end
frame:SetScript("OnEvent", function(_, event)
  if event ~= "TRAINER_UPDATE" and event ~= "MERCHANT_UPDATE" then ns.ArrowBack() end     -- a window of the arrow's business opened
  if event == "TRAINER_SHOW" or event == "TRAINER_UPDATE" then pcall(NoteTrainer)
  elseif event == "MERCHANT_SHOW" or event == "MERCHANT_UPDATE" then pcall(NoteVendor)
  elseif event == "AUCTION_HOUSE_SHOW" then Note("auction", "", { name = Npc() })
  elseif event == "MAIL_SHOW" then Note("mailbox", "Mailbox") end           -- for the way back to the mail (since 1.6.17)
end)

ns.places = { MapName = MapName }

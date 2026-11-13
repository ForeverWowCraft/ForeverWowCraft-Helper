-- What the character has: bags, bank, mail and the character's own auctions, and the
-- character's skills. Counted here and kept, for the account, in the saved variable:
--   FWCS_DB.__chars["<house's realm>|<name>"] = { name, realm, house, faction, t,
--       bankSeen, mailSeen, ahSeen,
--       items = { [itemID] = { in bags, in the bank, in the mail, in auctions } },
--       skills = { [skill line] = rank },
--       profession = the one last shown, picked = the one the player picked from the list,
--       from = { [profession] = skill to plan from, when the player said one },
--       upto = { [profession] = skill to plan up to }, also = { [profession] = second one, false for none },
--       budget = { copper = gold to spend when typed (nil: the bags), on = true when the route is cut there } }
-- Bags are read slot by slot whenever they change. The bank, the mailbox and the character's
-- own auctions can only be read while each is open (the game has no other way to them), so
-- those counts are from the last visit (bankSeen, mailSeen, ahSeen). Only items a profession
-- uses or makes are kept (the lists of Queue.lua and the routes' own).
-- WHAT THIS FILE GATHERS: what the character has (the items above, its skills, the gold typed as
-- a budget), when the bags change and while the bank, the mailbox or the auction house is open,
-- for the /fwc window and the Make button: a route less what is in hand. It is kept in the saved
-- file on this computer and NEVER sent: the helper reads FWCS_DB.__chars to know which auction
-- houses' routes to fetch from the site, and its `status` command lists the characters on the
-- screen; none of it leaves the computer. Everything the addon
-- gathers: docs/scanner-addon.md, "What the addon gathers".
--
-- Window.lua draws from it, through ns.inv.

local _, ns = ...

local PLACES = { "bags", "the bank", "the mail", "auctions" }     -- items[id][1..4]
local bankOpen, mailOpen, ahOpen = false, false, false
local Place

-- ================================================================ what the character has
local function Spelt(name) return ((name or ""):lower():gsub("[^a-z0-9]", "")) end

local function CharKey() return ns.RealmKey() .. "|" .. (UnitName("player") or "?") end

local function Char()
  FWCS_DB.__chars = FWCS_DB.__chars or {}
  local key = CharKey()
  local c = FWCS_DB.__chars[key] or {}
  FWCS_DB.__chars[key] = c
  c.name, c.realm, c.house = UnitName("player") or "?", GetRealmName() or "?", ns.RealmKey()
  c.faction = (UnitFactionGroup and UnitFactionGroup("player")) or ""
  c.items, c.skills, c.from, c.upto, c.also = c.items or {}, c.skills or {}, c.from or {}, c.upto or {}, c.also or {}
  c.budget = c.budget or {}                  -- the gold ceiling: copper (nil: the bags), on (the route cut there)
  return c
end

-- the auction house of this character among those the helper wrote routes for
-- The auction house a realm is of by its name, as the site's rules have it (the core's
-- config.HOUSE_PATTERNS): "CAMWOW US2 Realm 1 PvE" is US PvE (US and AU are one region),
-- "CAMWOW EU4 Realm 3 RP PvP" is EU RP PvP. Spelt as the houses' names are compared.
local function Ruled(realm)
  local region, rules = (realm or ""):match("^CAMWOW (%a+)%d+ Realm %d+ (.+)$")
  if not region then return nil end
  if region == "AU" then region = "US" end
  return Spelt(region .. " " .. rules)
end

-- The fishing route (Plans.lua's FWCS_ROUTES = { [faction] = plan }, written by helper 1.8.0 and
-- later; nothing earlier writes or reads it) joined to a house, once: house.fish is the plan, and
-- the names of its items go into house.items (the fish are not in the house's own). A house of
-- no faction, a faction with no route, or a route that is not a fishing plan, has none.
local function Attach(house)
  if house.fishLooked then return house end
  house.fishLooked = true
  local route = type(FWCS_ROUTES) == "table" and FWCS_ROUTES[house.faction or ""] or nil
  if type(route) == "table" and route.kind == "fishing" and type(route.steps) == "table" and type(route.profession) == "string" then
    house.fish = route
    house.items = house.items or {}
    for item, name in pairs(type(route.names) == "table" and route.names or {}) do
      if house.items[item] == nil then house.items[item] = name end
    end
  end
  return house
end

local function House()
  local faction = (UnitFactionGroup and UnitFactionGroup("player")) or ""
  local mine, group = Spelt(GetRealmName()), Spelt(ns.RealmKey())
  for key, house in pairs(FWCS_PLANS or {}) do
    if house.faction == faction then
      for _, realm in ipairs(house.realms or {}) do
        if realm == mine or realm == group then return Attach(house), key end
      end
    end
  end
  -- a realm no list has (nobody scanned from it, or the helper fetched the region's houses before it
  -- had seen this character): the house its name says (the blank window players reported, 9 Nov 2026)
  local ruled = Ruled(GetRealmName())
  if ruled then
    for key, house in pairs(FWCS_PLANS or {}) do
      if house.faction == faction and Spelt(house.realm or "") == ruled then return Attach(house), key end
    end
  end
end

-- the items worth counting: everything on the scan lists, everything a route names, and the
-- tools the route's recipes need with what they take (FWCS_DB.__tools: a rod in the bank is had)
local tracked
local function Tracked()
  if tracked then return tracked end
  tracked = {}
  for item in pairs(ns.QueuedItems()) do tracked[item] = true end
  local house = House()
  for item in pairs(house and house.items or {}) do tracked[item] = true end
  local known = ns.ToolsKnown and ns.ToolsKnown()
  for item, t in pairs(known and known.byItem or {}) do
    tracked[item] = true
    for _, u in ipairs(t.uses or {}) do tracked[u[1]] = true end
  end
  return tracked
end
local function Retrack() tracked = nil end             -- a tool learned: counted from the next count on

local function SlotItem(bag, slot)
  if C_Container and C_Container.GetContainerItemInfo then
    local info = C_Container.GetContainerItemInfo(bag, slot)
    if info then return info.itemID, info.stackCount end
  elseif GetContainerItemInfo then
    local _, count, _, _, _, _, _, _, _, item = GetContainerItemInfo(bag, slot)
    return item, count
  end
end

local function CountBags()
  local c, counts = Char(), {}
  local slotsOf = (C_Container and C_Container.GetContainerNumSlots) or GetContainerNumSlots
  if not slotsOf then return end
  for bag = 0, NUM_TOTAL_EQUIPPED_BAG_SLOTS or NUM_BAG_SLOTS or 4 do      -- with the reagent bag, where the client has one
    for slot = 1, slotsOf(bag) or 0 do
      local item, count = SlotItem(bag, slot)
      if item then counts[item] = (counts[item] or 0) + (count or 1) end
    end
  end
  Place(1, counts)
  Char().t = time()
end

-- The count of each tracked item in one place (1 bags .. 4 auctions) replaces the last one;
-- `seen` is the character's field that says when that place was last counted.
Place = function(place, counts, seen)
  local c, wanted = Char(), Tracked()
  for _, n in pairs(c.items) do n[place] = 0 end
  for item, n in pairs(counts) do
    if wanted[item] then
      c.items[item] = c.items[item] or { 0, 0, 0, 0 }
      c.items[item][place] = n
    end
  end
  for item, n in pairs(c.items) do
    if ((n[1] or 0) + (n[2] or 0) + (n[3] or 0) + (n[4] or 0)) == 0 then c.items[item] = nil end
  end
  if seen then c[seen] = time() end
  if ns.HaveChanged then ns.HaveChanged() end    -- the route with what the character has is worked out again (Tailor.lua)
end

-- How many of an item the bags hold (the bank not counted), by the client's call, new
-- (C_Item.GetItemCount, Forever's) or old (the GetItemCount global, gone from newer clients:
-- read through it alone, every count was 0, seen on the beta 11 Oct 2026). Nil without either.
local function Count(item)
  local f = (C_Item and C_Item.GetItemCount) or GetItemCount
  if not f then return nil end
  local ok, n = pcall(f, item)
  return ok and tonumber(n) or 0
end

-- With the bank open the game counts what is in it: an item's count with the bank, less its
-- count without. Asked of every tracked item, whichever way this client numbers its bank bags.
local function CountBank()
  if not bankOpen then return end
  local count = (C_Item and C_Item.GetItemCount) or GetItemCount
  if not count then return end
  local counts = {}
  for item in pairs(Tracked()) do
    local banked = (count(item, true, false, true) or 0) - (count(item) or 0)
    if banked > 0 then counts[item] = banked end
  end
  Place(2, counts, "bankSeen")
end

-- The items attached to the mail in the inbox, while a mailbox is open: the game only has
-- the inbox then. A client of before GetInboxItem gave the item's id gives name, texture,
-- count: the id is taken from the link.
local function CountMail()
  if not mailOpen or not GetInboxNumItems or not GetInboxItem then return end
  local counts = {}
  for i = 1, GetInboxNumItems() or 0 do
    for a = 1, ATTACHMENTS_MAX_RECEIVE or 16 do
      local name, id, texture, count = GetInboxItem(i, a)
      if name and type(id) ~= "number" then
        local link = GetInboxItemLink and GetInboxItemLink(i, a)
        id, count = link and tonumber(link:match("item:(%d+)")), texture
      end
      if id then counts[id] = (counts[id] or 0) + (count or 1) end
    end
  end
  Place(3, counts, "mailSeen")
  Char().mailed = nil                        -- the inbox seen: what was bought at the house is counted as it is, not as expected
end

-- How many of an item wait in the mail: counted in the inbox when a mailbox was last open, or
-- bought at the auction house since (NoteMailed: the game delivers a purchase by mail), the
-- larger. The Make button sends the character to the mailbox for them before buying more
-- (the user, 7 Nov 2026).
local function InMail(item)
  local c = Char()
  local seen = c.items[item] and c.items[item][3] or 0
  local coming = c.mailed and c.mailed[item] or 0
  return math.max(seen, coming)
end

-- A purchase is counted once, whichever way it is noticed (the Buy button, a hook, the
-- game's system line): one noted within the last moments is not noted again when either is
-- the system line (which comes before or after the event, as the client likes).
-- `how`: "chat" for the system line; nil for the others
local recent = {}
local DOUBLE = 10
local function NoteMailed(item, units, how)
  local now = GetTime and GetTime() or 0
  local r = recent[item]
  if r and now - r.at < DOUBLE and (how == "chat" or r.how == "chat") then return false end
  recent[item] = { at = now, how = how }
  local c = Char()
  c.mailed = c.mailed or {}
  c.mailed[item] = (c.mailed[item] or 0) + (units or 1)
  c.mailedAt = time()
  if ns.HaveChanged then ns.HaveChanged() end
  return true
end

-- A purchase made by hand in the game's own auction-house window is noticed too, so that its
-- delivery by mail is known at once (the user, 11 Nov 2026: a recipe bought by hand, and the
-- arrow did not go to a mailbox). Post-hooks on the client's purchase calls remember what was
-- asked, O(1) each; the success event counts it (NoteMailed), a failure or the house closing
-- drops it. The calls the addon's own Buy button makes (Shop.lua) go through the same
-- functions: it sets `buyingOwn` around them and counts its own success, so nothing is counted twice.
--   item auction: C_AuctionHouse.PlaceBid(auctionID, amount); a buyout only (amount at or over
--     the buyout). The item behind the auction id is read, in this order, from
--       "info":    C_AuctionHouse.GetAuctionInfoByID, when this client has it;
--       "results": the item last searched (a post-hook on SendSearchQuery, and the item search
--                  events), whose results (GetNumItemSearchResults / GetItemSearchResultInfo,
--                  as the scanner reads them) hold the auction id, with its buyout;
--     and when neither knows it, the game's own system line for a won auction (ERR_AUCTION_WON_S):
--       "chat":    while the house is open and shortly after, the line naming an item the route
--                  tracks is counted, unless the other ways counted it already.
--   commodity: C_AuctionHouse.ConfirmCommoditiesPurchase(itemID, quantity)  ("commodity")
-- `/fwcs debug` says in chat which way noticed a purchase (ns.Debug).
local handAuctions, handCommodity = {}, nil
local buyingOwn = false
local lastKey                                  -- the item key last searched: the item page the player buys from

local function Said(how, item, units)
  if ns.Debug then ns.Debug(string.format("a purchase by hand noticed (%s): %d x item %d", how, units or 1, item)) end
end

-- the item, buyout and quantity of an auction id, and the way it was known
local function AuctionOf(auctionID)
  if C_AuctionHouse.GetAuctionInfoByID then
    local ok, info = pcall(C_AuctionHouse.GetAuctionInfoByID, auctionID)
    if ok and type(info) == "table" and info.itemKey and info.itemKey.itemID then
      return info.itemKey.itemID, tonumber(info.buyoutAmount) or 0, tonumber(info.quantity) or 1, "info"
    end
  end
  if lastKey and C_AuctionHouse.GetNumItemSearchResults and C_AuctionHouse.GetItemSearchResultInfo then
    local ok, n = pcall(C_AuctionHouse.GetNumItemSearchResults, lastKey)
    for i = 1, ok and tonumber(n) or 0 do
      local ok2, info = pcall(C_AuctionHouse.GetItemSearchResultInfo, lastKey, i)
      if ok2 and type(info) == "table" and info.auctionID == auctionID then
        return (info.itemKey and info.itemKey.itemID) or lastKey.itemID, tonumber(info.buyoutAmount) or 0, tonumber(info.quantity) or 1, "results"
      end
    end
  end
end

local function OwnCall(fn, ...)
  buyingOwn = true
  local ok, err = pcall(fn, ...)
  buyingOwn = false
  if not ok then error(err, 0) end
end

if hooksecurefunc and C_AuctionHouse then
  if C_AuctionHouse.PlaceBid then
    pcall(hooksecurefunc, C_AuctionHouse, "PlaceBid", function(auctionID, amount)
      if buyingOwn or not auctionID then return end
      local item, buyout, units, how = AuctionOf(auctionID)
      if item and buyout > 0 and (tonumber(amount) or 0) >= buyout then    -- a bid under the buyout is not a purchase
        handAuctions[auctionID] = { item = item, units = units, how = how }
      end
    end)
  end
  if C_AuctionHouse.SendSearchQuery then
    pcall(hooksecurefunc, C_AuctionHouse, "SendSearchQuery", function(key)
      if type(key) == "table" and key.itemID then lastKey = key end
    end)
  end
  if C_AuctionHouse.ConfirmCommoditiesPurchase then
    pcall(hooksecurefunc, C_AuctionHouse, "ConfirmCommoditiesPurchase", function(item, units)
      if buyingOwn or not item then return end
      handCommodity = { item = item, units = tonumber(units) or 1 }
    end)
  end
end

local purchases = CreateFrame("Frame")
for _, event in ipairs({ "AUCTION_HOUSE_PURCHASE_COMPLETED", "COMMODITY_PURCHASE_SUCCEEDED", "COMMODITY_PURCHASE_FAILED", "AUCTION_HOUSE_CLOSED",
                         "AUCTION_HOUSE_SHOW", "ITEM_SEARCH_RESULTS_UPDATED", "ITEM_SEARCH_RESULTS_ADDED" }) do
  pcall(purchases.RegisterEvent, purchases, event)
end

-- The game's line for a won auction, as a pattern, from its own global string (any language):
-- "You won an auction for %s". Built again only when the string differs from the last one.
local wonFormat, wonPattern
local function WonPattern()
  local fmt = ERR_AUCTION_WON_S
  if type(fmt) ~= "string" then return nil end
  if fmt ~= wonFormat then
    wonFormat = fmt
    local marked = fmt:gsub("%%%d?%$?s", "\1")                      -- %s, %1$s: where the item stands
    marked = marked:gsub("[%^%$%(%)%.%%%[%]%*%+%-%?]", "%%%0")
    wonPattern = "^" .. marked:gsub("\1", "(.+)") .. "$"
  end
  return wonPattern
end

-- the item a won-auction line names, when it is one the route tracks: from its link, else its name
local function WonItem(msg)
  local pattern = WonPattern()
  local what = pattern and msg:match(pattern)
  if not what then return nil end
  local id = tonumber(what:match("item:(%d+)"))
  local tracked = Tracked()
  if id then return tracked[id] and id or nil end
  local name = what:match("%[(.-)%]") or what
  for item in pairs(tracked) do
    if ns.ItemName and ns.ItemName(item) == name then return item end
  end
end

local chatOn = false
local function Chat(on)
  if on == chatOn then return end
  chatOn = on
  pcall(on and purchases.RegisterEvent or purchases.UnregisterEvent, purchases, "CHAT_MSG_SYSTEM")
end

purchases:SetScript("OnEvent", function(_, event, a1)
  if event == "AUCTION_HOUSE_PURCHASE_COMPLETED" then
    local h = handAuctions[a1]
    handAuctions[a1] = nil
    if h and NoteMailed(h.item, h.units) then Said(h.how, h.item, h.units) end
  elseif event == "COMMODITY_PURCHASE_SUCCEEDED" then
    local h = handCommodity
    handCommodity = nil
    if h and NoteMailed(h.item, h.units) then Said("commodity", h.item, h.units) end
  elseif event == "ITEM_SEARCH_RESULTS_UPDATED" or event == "ITEM_SEARCH_RESULTS_ADDED" then
    if type(a1) == "table" and a1.itemID then lastKey = a1 end
  elseif event == "CHAT_MSG_SYSTEM" then
    local item = type(a1) == "string" and WonItem(a1)
    if item and NoteMailed(item, 1, "chat") then Said("system line", item, 1) end
  elseif event == "AUCTION_HOUSE_SHOW" then
    Chat(true)
  else                                                    -- failed, or the house closed: nothing was bought
    handCommodity = nil
    if event == "AUCTION_HOUSE_CLOSED" then
      handAuctions, lastKey = {}, nil
      if C_Timer and C_Timer.After then C_Timer.After(20, function() if not ahOpen then Chat(false) end end) else Chat(false) end
    end
  end
end)

-- The character's own auctions still up (not the sold ones: those are money in the mail), once
-- the auction house has sent the list (asked for when it opens; the game's own Auctions tab
-- asks too). Either way this client has them.
local function CountAuctions()
  if not ahOpen then return end
  local counts = {}
  if C_AuctionHouse and C_AuctionHouse.GetNumOwnedAuctions and C_AuctionHouse.GetOwnedAuctionInfo then
    for i = 1, C_AuctionHouse.GetNumOwnedAuctions() or 0 do
      local a = C_AuctionHouse.GetOwnedAuctionInfo(i)
      local id = a and a.itemKey and a.itemKey.itemID
      if id and (a.status or 0) == 0 then counts[id] = (counts[id] or 0) + (a.quantity or 1) end
    end
  elseif GetNumAuctionItems and GetAuctionItemInfo then
    for i = 1, GetNumAuctionItems("owner") or 0 do
      local _, _, count, _, _, _, _, _, _, _, _, _, _, _, _, status, id = GetAuctionItemInfo("owner", i)
      if id and (status or 0) == 0 then counts[id] = (counts[id] or 0) + (count or 1) end
    end
  else
    return
  end
  Place(4, counts, "ahSeen")
end

local function AskForAuctions()
  if C_AuctionHouse and C_AuctionHouse.QueryOwnedAuctions then
    pcall(C_AuctionHouse.QueryOwnedAuctions, { { sortOrder = Enum.AuctionHouseSortOrder.Price, reverseSort = false } })
  elseif GetOwnerAuctionItems then
    pcall(GetOwnerAuctionItems)
  end
end

-- The first rank's spell of each profession, by skill line (SkillLineAbility, rank 1): its
-- name is the profession's, in the client's language, for a client that only lists skills
-- by name.
local APPRENTICE = { [171] = 2259, [164] = 2018, [333] = 7411, [202] = 4036, [165] = 2108, [197] = 3908, [185] = 2550, [129] = 3273 }

local function SpellName(spell)
  local name = C_Spell and C_Spell.GetSpellName and C_Spell.GetSpellName(spell) or GetSpellInfo and GetSpellInfo(spell)
  if name and name ~= "" then return name end
end

-- The character's rank in a profession, or nil without it. Three ways, for whichever this
-- client has: by skill line, by its professions, by its skill list (there by name: the
-- client's own name for it, and the English one).
local function SkillOf(plan)
  local line = plan.skill_line
  if C_TradeSkillUI and C_TradeSkillUI.GetProfessionInfoBySkillLineID then
    local ok, info = pcall(C_TradeSkillUI.GetProfessionInfoBySkillLineID, line)
    if ok and type(info) == "table" and (info.skillLevel or 0) > 0 then return info.skillLevel, info.maxSkillLevel end
  end
  if GetProfessions and GetProfessionInfo then
    local found = { GetProfessions() }
    for i = 1, 6 do
      if found[i] then
        local _, _, rank, max, _, _, id = GetProfessionInfo(found[i])
        if id == line and rank then return rank, max end
      end
    end
  end
  if GetNumSkillLines and GetSkillLineInfo then
    local names = { [Spelt(plan.profession)] = true }
    local shown = C_TradeSkillUI and C_TradeSkillUI.GetTradeSkillDisplayName and C_TradeSkillUI.GetTradeSkillDisplayName(line)
    if shown and shown ~= "" then names[shown:lower()] = true end
    shown = APPRENTICE[line] and SpellName(APPRENTICE[line])
    if shown then names[shown:lower()] = true end
    for i = 1, GetNumSkillLines() do
      local name, header, _, rank, _, _, max = GetSkillLineInfo(i)
      if not header and name and (names[Spelt(name)] or names[name:lower()]) then return rank, max end
    end
  end
end

-- whether the client's skill list can be read now: for the first moments of a login it is
-- empty, and an empty list says nothing (tailoring was taken for unlearned at a relog, and
-- the arrow went to cooking, 12 Oct 2026)
local function SkillsReadable()
  if GetProfessions then
    local found = { GetProfessions() }
    for i = 1, 6 do if found[i] then return true end end
  end
  return (GetNumSkillLines and GetNumSkillLines() or 0) > 1
end

-- each profession's skill, and its cap (75 for an apprentice: the next rank is the trainer's)
local function NoteSkills()
  local house, c = House(), Char()
  c.caps = c.caps or {}
  for _, plan in pairs(house and house.plans or {}) do
    local rank, max = SkillOf(plan)
    c.skills[plan.skill_line] = rank
    c.caps[plan.skill_line] = (max and max > 0) and max or nil
  end
end

-- what there is to take from: this character's bags and bank, and with `alts` those of the
-- account's other characters of the same auction house
local function Have()
  local me, have = Char(), {}
  for _, c in pairs(FWCS_DB.__chars or {}) do
    if c == me or (ns.Settings().alts ~= false and c.house == me.house and c.faction == me.faction) then
      for item, n in pairs(c.items or {}) do
        have[item] = (have[item] or 0) + (n[1] or 0) + (n[2] or 0) + (n[3] or 0) + (n[4] or 0)
      end
    end
  end
  return have
end

-- ================================================================ what is open
local opener = CreateFrame("Frame")
for _, event in ipairs({ "BANKFRAME_OPENED", "BANKFRAME_CLOSED", "MAIL_SHOW", "MAIL_CLOSED",
                         "AUCTION_HOUSE_SHOW", "AUCTION_HOUSE_CLOSED", "OWNED_AUCTIONS_UPDATED", "AUCTION_OWNED_LIST_UPDATE" }) do
  pcall(opener.RegisterEvent, opener, event)       -- a client without one of them refuses it: the others still count
end
opener:SetScript("OnEvent", function(_, event)
  if event == "BANKFRAME_OPENED" then bankOpen = true
  elseif event == "BANKFRAME_CLOSED" then bankOpen = false
  elseif event == "MAIL_SHOW" then mailOpen = true
  elseif event == "MAIL_CLOSED" then mailOpen = false
  elseif event == "AUCTION_HOUSE_SHOW" then ahOpen = true; AskForAuctions()
  elseif event == "AUCTION_HOUSE_CLOSED" then ahOpen = false
  else CountAuctions() end
end)

ns.inv = { Spelt = Spelt, Char = Char, House = House, Tracked = Tracked, Count = Count, CountBags = CountBags, CountBank = CountBank,
           CountMail = CountMail, NoteSkills = NoteSkills, SkillsReadable = SkillsReadable, Have = Have, PLACES = PLACES,
           InMail = InMail, NoteMailed = NoteMailed, OwnCall = OwnCall, Retrack = Retrack, Ruled = Ruled }

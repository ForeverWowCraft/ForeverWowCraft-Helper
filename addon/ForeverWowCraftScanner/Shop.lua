-- What the next step needs bought, and buying it: a small list, one row an item with what is
-- needed, what the bags hold and about what it costs. At the auction house the list docks to
-- the house's frame and each row has a button. The house's purchase calls take a click (a
-- hardware event: from an event handler the game says "Interface action failed because of an
-- AddOn", seen on the beta 11 Oct 2026), so the list searches each item ahead, one at a time,
-- as it opens at the house; the button then says "Buy 10", that click asks the house for the
-- price of the cheapest up to that many, the house answers, and the next click confirms. A
-- single item (a recipe) goes in one click, the cheapest auction's buyout. A vendor's item
-- says "vendor": the arrow leads there, and at the vendor the list docks to the merchant's
-- window with a Buy button on each row the merchant sells: a click buys up to a stack (the
-- game's own limit a purchase), the bags say when it is there, and the row offers the rest
-- (two things from one vendor left the second unseen, 12 Oct 2026). A ware sold in bundles
-- (Empty Vial, 5 a purchase) is bought in whole bundles, enough to cover what is missing, and
-- the row says so ("Buy 15", "3 x 5"): BuyMerchantItem counts ITEMS, as the game's own
-- stack-split box asks it (players got odd amounts when it was given bundles, 10 Nov 2026).
--
-- The list is the Make button's (Craft.lua, ns.craft.Shopping): the route's next step at the
-- character's skill, less the bags. It opens by itself when the auction house opens with
-- something to buy, and from a click on the Make button when it says "Buy".

local _, ns = ...

local PREFIX = "|cff" .. ns.BRAND.gold .. "ForeverWowCraft|r: "
local ROWS = 12
local SORTS = { { sortOrder = Enum and Enum.AuctionHouseSortOrder and Enum.AuctionHouseSortOrder.Price or 1, reverseSort = false } }

local panel
local list = {}                    -- { { item, units, have, source, price, recipe }, ... }
local known = {}                   -- item -> { n } listed (a commodity) | { auctionID, price } (an item) | { none = true }
local bought = {}                  -- item -> true once bought this visit: no second buy until the house is opened again
local searching                    -- the search out: { item, row, key, commodity }
local pending                      -- the purchase under way: { item, units, row, state = "pricing" | "priced" | "buying", commodity, price, auctionID }
local waiting                      -- a ticker, while a scan has the house
local merchant                     -- the merchant open: item -> { index, price, stack, per, available }; nil when none is
local offered                      -- the list was offered at this merchant (not again on each update)
local vending                      -- a vendor purchase made: { item, have, units }, until the bags move or a while passes

local function AhOpen() return ns.scanner and ns.scanner.Open() end
local function Scanning() return ns.scanner and ns.scanner.Running() end
-- A FULL snapshot asks the house once and waits for the answer; the list may ask meanwhile,
-- and the client holds its asking until the house is free (HouseReady: the throttled message
-- system). A per-list SCAN asks item by item on the channel the list uses, and so has the
-- house to itself (12 Oct 2026: before, the list refused during either, and a snapshot that
-- never came held a player at the list for two minutes)
local function Snapshot() return Scanning() and ns.scanner.Snapshot and ns.scanner.Snapshot() or false end
local function Exclusive() return Scanning() and not Snapshot() end
local function HouseReady() return not C_AuctionHouse.IsThrottledMessageSystemReady or C_AuctionHouse.IsThrottledMessageSystemReady() end
local held                         -- when the list began waiting for the house during a snapshot; nil when not waiting
local function CanSearch() return C_AuctionHouse and C_AuctionHouse.MakeItemKey and C_AuctionHouse.SendSearchQuery and C_AuctionHouse.GetItemKeyInfo end

-- ================================================================ buying
local function Say(row, text) row.status:SetText(text) end
local function Missing(e) return math.max(1, e.units - (e.have or 0)) end

-- the merchant open: what it sells by item, with the index to buy by, the price of one
-- purchase, how many items a purchase gives (its bundle: 5 Empty Vials), how many items one
-- call may buy (the game's limit, GetMerchantItemMaxStack, in items, cut to whole bundles and
-- one bundle at least) and how many it has (-1: no end).
-- BuyMerchantItem(index, quantity) takes ITEMS: Blizzard's own merchant window opens its
-- stack-split box at up to GetMerchantItemMaxStack items in steps of the bundle and hands the
-- number picked to BuyMerchantItem as it is; what it can afford it counts as money over the
-- price of ONE item (price / bundle). Given bundles, a ware sold five at a time came in odd
-- amounts (a player, 10 Nov 2026); for a ware sold singly the two are the same.
local function ScanMerchant()
  if not (GetMerchantNumItems and GetMerchantItemLink) then return end
  merchant = {}
  for i = 1, GetMerchantNumItems() do
    local link = GetMerchantItemLink(i)
    local item = link and tonumber(link:match("item:(%d+)"))
    if item then
      local _, _, price, stack, available = ns.MerchantItemInfo(i)
      stack = math.max(1, math.floor(tonumber(stack) or 1))
      local max = GetMerchantItemMaxStack and tonumber(GetMerchantItemMaxStack(i)) or 0
      merchant[item] = { index = i, price = tonumber(price) or 0, stack = stack,
                         per = math.max(stack, max - max % stack), available = tonumber(available) or -1 }
    end
  end
end

-- what a click buys of a row's item at the merchant open: the purchases (bundles) and the
-- items they give. Whole bundles enough for what is missing (12 missing of a ware sold five
-- at a time: 3 bundles, 15), no more than one call may buy (the rest on the next click, once
-- the bags have the first), nor more than the merchant has: a limited stock is counted in
-- items, as the call is; a stock short of one bundle is taken to be one bundle (a client
-- counting it in purchases), which the merchant refuses if it is not, and the row takes a
-- click again
local function Stacks(e)
  local m = merchant and merchant[e.item]
  if not m then return 0, 0 end
  local n = math.min(math.ceil(Missing(e) / m.stack), math.floor(m.per / m.stack))
  if m.available >= 0 then
    local can = math.floor(m.available / m.stack)
    if can < 1 and m.available > 0 then can = 1 end
    n = math.min(n, can)
  end
  return n, n * m.stack
end

-- a vendor's item, bought: one call for the items of whole bundles, as the game's own
-- stack-split box buys (the bags say when it is there, and the list then offers the rest);
-- the button is dead meanwhile
local function BuyAtVendor(row, e)
  local m, n, units = merchant[e.item], Stacks(e)
  if n < 1 or not BuyMerchantItem or (vending and vending.item == e.item) then return end
  BuyMerchantItem(m.index, units)
  local v = { item = e.item, have = e.have or 0, units = units }
  vending = v
  Say(row, string.format("buying %d...", units))
  row.buy:Disable()
  if C_Timer and C_Timer.After then                           -- a refused purchase: the row takes a click again after a while
    C_Timer.After(2, function() if vending == v then vending = nil; ns.RefreshShopping() end end)
  end
end

-- a row's button and status from what is known of its item
local function Label(row)
  local e = rawget(row, "entry")
  if not e or (pending and pending.row == row) then return end
  if bought[e.item] then                         -- bought this visit: the button stays dead until the house is opened again
    Say(row, "bought"); row.buy:SetText("Bought"); row.buy:Show(); row.buy:Disable()
    return
  end
  row.buy:Enable()                               -- a row not waiting on the house takes a click
  local k = known[e.item]
  local about = e.price and ("about " .. ns.Money(e.price * Missing(e))) or ""
  if k and k.none then
    Say(row, "none listed"); row.buy:Hide()
  elseif k and k.auctionID then
    Say(row, "one for " .. ns.Money(k.price)); row.buy:SetText("Buy"); row.buy:Show()
  elseif k then
    -- the units missing, or all that is listed when that is fewer (the house refuses a
    -- quantity it cannot fill: "price unavailable", over and over, 11 Oct 2026)
    local want = Missing(e)
    local can = (k.units and k.units > 0 and k.units < want) and k.units or want
    if can < want then Say(row, string.format("only %d listed", can)) else Say(row, about) end
    row.buy:SetText("Buy " .. can); row.buy:Show()
  elseif searching and searching.row == row then
    Say(row, searching.held and "waiting for the house..." or "searching..."); row.buy:SetText("..."); row.buy:Show()
  else
    Say(row, about); row.buy:SetText("Buy"); row.buy:Show()
  end
end

-- the cheapest single auction of an item among the results
local function CheapestItem(key)
  local best
  for i = 1, C_AuctionHouse.GetNumItemSearchResults(key) do
    local info = C_AuctionHouse.GetItemSearchResultInfo(key, i)
    if info and info.buyoutAmount and info.buyoutAmount > 0 and (not best or info.buyoutAmount < best.buyoutAmount) then best = info end
  end
  return best
end

local Prime

-- the search of an item, once the house takes one; its results come as an event
local function Search(item, row)
  searching = { item = item, row = row, key = C_AuctionHouse.MakeItemKey(item) }
  Label(row)
  local function go(n)
    local s = searching
    if not s or s.item ~= item then return end
    local keyInfo = C_AuctionHouse.GetItemKeyInfo(s.key)
    local ready = HouseReady()
    if not ready and Snapshot() then
      -- the house is answering the snapshot: the list waits for it as long as that takes (the
      -- snapshot's own timeout ends it), and says so once; how long it waited is said after,
      -- to learn what the house does with a snapshot that is refused (12 Oct 2026)
      if not held then
        held = GetTime()
        print(PREFIX .. "the house is answering the snapshot: the list goes on when it is free")
      end
      if not s.held then s.held = true; Label(row) end
      C_Timer.After(0.5, function() go(n) end)
      return
    end
    if not keyInfo or not ready then
      if n > 20 then searching = nil; Say(row, "the house did not answer"); return end
      C_Timer.After(0.25, function() go(n + 1) end)
      return
    end
    if held then
      print(PREFIX .. string.format("the house is free again after %d s: the list goes on", math.floor(GetTime() - held)))
      held = nil
    end
    if s.held then s.held = nil; Label(row) end
    s.commodity = keyInfo.isCommodity
    C_AuctionHouse.SendSearchQuery(s.key, SORTS, false)
  end
  go(1)
end

-- the next unknown item of the list searched ahead, one at a time, while nothing else has the house
function Prime()
  if not panel or not panel:IsShown() or not AhOpen() or searching or pending or not CanSearch() then return end
  if Exclusive() then
    if not waiting and C_Timer and C_Timer.NewTicker then
      waiting = C_Timer.NewTicker(1, function()
        if not Exclusive() then
          if waiting and waiting.Cancel then waiting:Cancel() end
          waiting = nil
          Prime()
        end
      end)
    end
    return
  end
  for _, row in ipairs(panel.rows) do
    local e = rawget(row, "entry")
    if e and e.source ~= "vendor" and e.source ~= "catch" and (e.have or 0) < e.units and not known[e.item] and not bought[e.item] then
      Search(e.item, row)
      return
    end
  end
end

local Reload, stale
local function Reset()
  local row = pending and pending.row
  pending = nil
  if row then row.buy:Enable(); Label(row) end
  if stale and Reload then Reload() end
end

-- a purchase the house has not answered in a while (a call the client refused answers with
-- nothing) is given up, and the row takes a click again
local function GiveUpLater(p)
  if not (C_Timer and C_Timer.After) then return end
  C_Timer.After(10, function()
    if pending == p and (p.state == "pricing" or p.state == "buying") then
      Reset()
      Say(p.row, "the house did not answer")        -- after the label, which would overwrite it
    end
  end)
end

-- the row's button: the price asked (a commodity) or the auction bought (an item), confirmed
-- on the next click; an item not yet searched is searched first, and the button then says how many
local function Click(row)
  local e = rawget(row, "entry")
  if not e then return end
  if merchant and merchant[e.item] then BuyAtVendor(row, e); return end
  if not AhOpen() then return end
  -- the house's calls come first in a click, before anything is done to the button or the
  -- row: done after, they went through; done before, the client refused the call (11 Oct 2026)
  if pending and pending.row == row and pending.state == "priced" then
    pending.state = "buying"
    ns.inv.OwnCall(C_AuctionHouse.ConfirmCommoditiesPurchase, e.item, pending.units)
    Say(row, "buying...")
    row.buy:Disable()                                      -- one confirm only: dead until the house answers, whatever is clicked
    GiveUpLater(pending)
    return
  end
  if pending then
    if pending.row ~= row then print(PREFIX .. "a purchase is under way: confirm it, or close the list to drop it") end
    return                                                 -- the same row again while the house prices: nothing
  end
  local k = known[e.item]
  if not k then
    if Exclusive() then print(PREFIX .. "a per-list scan is running: buy after it, or /fwcs stop"); return end
    if searching then
      print(PREFIX .. (searching.held and "the house is answering the snapshot: the row says Buy when it is free"
                                       or "the house is being asked about another item: a moment"))
      return
    end
    if not CanSearch() then print(PREFIX .. "this client's auction house has no item search for the list: use the house's own search"); return end
    Search(e.item, row)
    return
  end
  if k.none then return end
  if not HouseReady() then print(PREFIX .. "the house is busy answering the snapshot: a moment, then click again"); return end
  if k.auctionID then
    pending = { item = e.item, units = 1, row = row, state = "buying", price = k.price, auctionID = k.auctionID }
    ns.inv.OwnCall(C_AuctionHouse.PlaceBid, k.auctionID, k.price)
    Say(row, "buying...")
    row.buy:SetText("...")
    row.buy:Disable()
    GiveUpLater(pending)
    return
  end
  local want = Missing(e)
  local can = (k.units and k.units > 0 and k.units < want) and k.units or want
  pending = { item = e.item, units = can, row = row, state = "pricing", commodity = true }
  C_AuctionHouse.StartCommoditiesPurchase(e.item, pending.units)
  Say(row, "pricing...")
  row.buy:SetText("...")                                   -- a click meanwhile does nothing (a purchase is under way)
  GiveUpLater(pending)
end

-- the list taken again from the route and the bags (a sale to a vendor, a craft, a mail
-- opened: the step's needs change with them), unless a purchase is under way, which keeps
-- its row until it is done; what the house said of each item is kept
function Reload()
  if not (panel and panel:IsShown()) then return end
  if pending then stale = true; return end
  stale = false
  local entries = ns.craft and ns.craft.Shopping and ns.craft.Shopping()
  if entries then list = entries end
  ns.RefreshShopping()
end
ns.ReloadShopping = Reload

local function Results(event, a1)
  local s = searching
  if not s then return end
  if event == "COMMODITY_SEARCH_RESULTS_UPDATED" then
    if a1 ~= s.item then return end
    local n = C_AuctionHouse.GetNumCommoditySearchResults(s.item)
    local units = 0
    if C_AuctionHouse.GetCommoditySearchResultInfo then
      for i = 1, n do                                                        -- the units listed, all auctions together
        local ok, info = pcall(C_AuctionHouse.GetCommoditySearchResultInfo, s.item, i)
        if ok and type(info) == "table" then units = units + (tonumber(info.quantity) or 0) end
      end
    end
    known[s.item] = n > 0 and { n = n, units = units } or { none = true }
  else
    if type(a1) ~= "table" or a1.itemID ~= s.item then return end
    local best = CheapestItem(s.key)
    known[s.item] = best and { auctionID = best.auctionID, price = best.buyoutAmount } or { none = true }
  end
  searching = nil
  Label(s.row)
  Prime()
end

local events = CreateFrame("Frame")
for _, e in ipairs({ "COMMODITY_SEARCH_RESULTS_UPDATED", "ITEM_SEARCH_RESULTS_UPDATED", "COMMODITY_PRICE_UPDATED", "COMMODITY_PRICE_UNAVAILABLE",
                     "COMMODITY_PURCHASE_SUCCEEDED", "COMMODITY_PURCHASE_FAILED", "AUCTION_HOUSE_PURCHASE_COMPLETED",
                     "AUCTION_HOUSE_SHOW", "AUCTION_HOUSE_CLOSED", "BAG_UPDATE_DELAYED", "SKILL_LINES_CHANGED", "CHAT_MSG_SKILL",
                     "MERCHANT_SHOW", "MERCHANT_UPDATE", "MERCHANT_CLOSED",
                     "ADDON_ACTION_BLOCKED", "ADDON_ACTION_FORBIDDEN" }) do
  pcall(events.RegisterEvent, events, e)
end
local ADDON = ...
events:SetScript("OnEvent", function(_, event, a1, a2)
  if event == "ADDON_ACTION_BLOCKED" or event == "ADDON_ACTION_FORBIDDEN" then
    -- the client refused a call of this addon's ("Interface action failed because of an
    -- AddOn"): which one, said in chat, so that what the house allows is known (11 Oct 2026:
    -- a buy of 93 was refused; from which of the calls is what this tells)
    if a1 == ADDON then
      print(PREFIX .. string.format("the client refused %s from the addon (%s)%s", tostring(a2), event,
        pending and (": the purchase of " .. tostring(pending.units) .. " is dropped; the house's own Buy takes it") or ""))
      if pending then local row = pending.row; Reset(); Say(row, "refused by the client") end
    end
    return
  end
  if event == "AUCTION_HOUSE_SHOW" then ns.OpenShopping(); return end
  -- a merchant: the list when it sells something the step needs (its wares may come after
  -- the window, on an update: offered once either way), and the rows again as they change
  if event == "MERCHANT_SHOW" or event == "MERCHANT_UPDATE" then
    if event == "MERCHANT_SHOW" then offered = false end
    ScanMerchant()
    if panel and panel:IsShown() then ns.RefreshShopping()
    elseif not offered then ns.OpenShopping() end
    return
  end
  if event == "MERCHANT_CLOSED" then
    merchant, offered = nil, false
    if panel and panel.docked then panel:Hide() end
    return
  end
  if event == "AUCTION_HOUSE_CLOSED" then
    if pending then Reset() end
    searching, known, bought, held = nil, {}, {}, nil
    if panel and panel.docked then panel:Hide() end
    return
  end
  if event == "BAG_UPDATE_DELAYED" or event == "SKILL_LINES_CHANGED" or event == "CHAT_MSG_SKILL" then
    Reload()                                                               -- the bags or the skill moved: the step's needs again
    return
  end
  if event == "COMMODITY_SEARCH_RESULTS_UPDATED" or event == "ITEM_SEARCH_RESULTS_UPDATED" then Results(event, a1); return end
  local p = pending
  if not p then return end
  if event == "COMMODITY_PRICE_UPDATED" and p.state == "pricing" then
    local unit, total = a1, a2
    p.state, p.price = "priced", total
    Say(p.row, string.format("%d for %s (%s each)", p.units, ns.Money(total or 0), ns.Money(unit or 0)))
    p.row.buy:SetText("Confirm")
    p.row.buy:Enable()
  elseif event == "COMMODITY_PRICE_UNAVAILABLE" then
    known[p.item] = nil                                    -- what is listed has changed: searched again, by itself
    Reset()
    Say(p.row, "the price moved: a moment")
    Prime()
  elseif event == "COMMODITY_PURCHASE_SUCCEEDED" or event == "AUCTION_HOUSE_PURCHASE_COMPLETED" then
    known[p.item] = nil                                  -- what is listed has changed
    bought[p.item] = true                                -- and this item is not bought again this visit
    if ns.inv.NoteMailed then ns.inv.NoteMailed(p.item, p.units) end     -- it comes by mail: the arrow goes to the mailbox for it
    Reset()
  elseif event == "COMMODITY_PURCHASE_FAILED" then
    known[p.item] = nil
    Reset()
    Say(p.row, "the purchase failed")
  end
end)

-- ================================================================ the list
local function Build()
  panel = CreateFrame("Frame", "ForeverWowCraftShop", UIParent, "BackdropTemplate")
  panel:SetSize(420, 60)
  panel:SetFrameStrata("HIGH")
  panel:SetMovable(true)
  panel:EnableMouse(true)
  panel:RegisterForDrag("LeftButton")
  panel:SetScript("OnDragStart", function(f) if not f.docked then f:StartMoving() end end)
  panel:SetScript("OnDragStop", function(f) f:StopMovingOrSizing() end)
  if C_Timer and C_Timer.NewTicker then C_Timer.NewTicker(5, function() Reload() end) end     -- and now and then regardless
  panel:SetScript("OnHide", function()                  -- a price asked and not confirmed is let go
    if pending and pending.commodity and pending.state ~= "buying" then pcall(C_AuctionHouse.CancelCommoditiesPurchase) end
    pending = nil
  end)
  if panel.SetBackdrop then
    panel:SetBackdrop({ bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background", edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
                        tile = true, tileSize = 32, edgeSize = 24, insets = { left = 6, right = 6, top = 6, bottom = 6 } })
  end
  panel.title = panel:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  panel.title:SetPoint("TOPLEFT", 14, -12)
  panel.close = CreateFrame("Button", nil, panel, "UIPanelCloseButton")
  panel.close:SetPoint("TOPRIGHT", -4, -4)
  panel.note = panel:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  panel.note:SetPoint("BOTTOMLEFT", 14, 10)
  panel.note:SetWidth(390)
  panel.note:SetJustifyH("LEFT")
  panel.rows = {}
  for i = 1, ROWS do
    local row = CreateFrame("Frame", nil, panel)
    row:SetSize(392, 20)
    row:SetPoint("TOPLEFT", 14, -34 - (i - 1) * 22)
    row.name = row:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    row.name:SetPoint("LEFT", 0, 0)
    row.name:SetWidth(160)
    row.name:SetJustifyH("LEFT")
    row.need = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    row.need:SetPoint("LEFT", row.name, "RIGHT", 4, 0)
    row.need:SetWidth(84)
    row.need:SetJustifyH("LEFT")
    row.status = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    row.status:SetPoint("RIGHT", -72, 0)
    row.status:SetWidth(84)
    row.status:SetJustifyH("RIGHT")
    row.buy = ns.Button(row, 66, "Buy")
    row.buy:SetPoint("RIGHT", 0, 0)
    row.buy:SetScript("OnClick", function() Click(row) end)
    panel.rows[i] = row
  end
  panel:Hide()
end

local function Place()
  panel:ClearAllPoints()
  if AhOpen() and AuctionHouseFrame then
    panel.docked = true
    panel:SetPoint("TOPLEFT", AuctionHouseFrame, "TOPRIGHT", 6, 0)
  elseif merchant and MerchantFrame then
    panel.docked = true
    panel:SetPoint("TOPLEFT", MerchantFrame, "TOPRIGHT", 6, 0)
  else
    panel.docked = false
    panel:SetPoint("CENTER", UIParent, "CENTER", 0, -120)
  end
end

function ns.RefreshShopping()
  if not panel then return end
  local house = ns.inv.House()
  local names = house and house.items or {}
  local atAh = AhOpen()
  local shown = 0
  for i, row in ipairs(panel.rows) do
    local e = list[i]
    row.entry = e
    if e then
      shown = shown + 1
      e.have = ns.inv.Count(e.item) or e.have or 0
      row.name:SetText((ns.ItemName(e.item, names[e.item])) .. (e.recipe and " (recipe)" or ""))
      row.need:SetText(string.format("need %d, have %d", e.units, e.have))
      local n, units = Stacks(e)
      if e.have >= e.units then
        row.status:SetText("|cff40ff40done|r"); row.buy:Hide()
      elseif e.source == "catch" then                            -- a fish of the fishing route: caught, never bought
        row.status:SetText("catch"); row.buy:Hide()
      elseif merchant and merchant[e.item] then                  -- the merchant open sells it: a click buys up to a stack
        if vending and vending.item == e.item and vending.have == e.have then                 -- the bags not yet moved (the row may have moved)
          row.status:SetText(string.format("buying %d...", vending.units)); row.buy:Show(); row.buy:Disable()
        elseif n < 1 then row.status:SetText("sold out"); row.buy:Hide()
        else
          if vending and vending.item == e.item then vending = nil end
          local m = merchant[e.item]                                -- the gold: the bundles at the price of one
          row.status:SetText(m.stack > 1 and string.format("%d x %d, %s", n, m.stack, ns.Money(m.price * n)) or ns.Money(m.price * n))
          row.buy:SetText("Buy " .. units); row.buy:Show(); row.buy:Enable()
        end
      elseif merchant and e.source == "vendor" then
        row.status:SetText("not here"); row.buy:Hide()
      elseif e.source == "vendor" then
        row.status:SetText("vendor"); row.buy:Hide()
      elseif atAh then
        Label(row)
      else
        row.status:SetText(e.price and ("about " .. ns.Money(e.price * Missing(e))) or "auction house"); row.buy:Hide()
      end
      row:Show()
    else
      row:Hide()
    end
  end
  panel:SetHeight(34 + shown * 22 + 30)
  panel.title:SetText(list.title or "What the next step needs")
  panel.note:SetText(atAh and "Buy: the house prices the cheapest up to what is needed; Confirm buys. A vendor's item: the arrow leads there."
    or merchant and "Buy: this vendor's, up to a stack a click; click again for the rest. The auction house's: the arrow leads there."
    or "Open the auction house to buy here; the arrow leads to a vendor's.")
  if atAh then Prime() end
end

-- the list, shown: `entries` as ns.craft.Shopping gives them
function ns.ShowShopping(entries)
  if not panel then Build() end
  list = entries or {}
  Place()
  panel:Show()
  ns.RefreshShopping()
end

function ns.HideShopping() if panel then panel:Hide() end end

-- whether the list has buying to do at the house: shown, and a row the house can sell (not a
-- vendor's, not had, not bought, not "none listed"), or a purchase under way. The full
-- snapshot the scanner takes by itself waits for this (the buying first: a scan holds the
-- house for a while, and a player at the list should not wait for it, 12 Oct 2026)
function ns.ShoppingBusy()
  if not (panel and panel:IsShown() and AhOpen()) then return false end
  if pending then return true end
  for _, e in ipairs(list) do
    local k = known[e.item]
    if e.source ~= "vendor" and e.source ~= "catch" and (e.have or 0) < e.units and not bought[e.item] and not (k and k.none) then return true end
  end
  return false
end

-- the auction house opened, or a merchant: the list, when there is something to buy here,
-- and the setting allows
function ns.OpenShopping()
  if ns.Settings().shop == false then return end
  local entries = ns.craft and ns.craft.Shopping and ns.craft.Shopping()
  local any = false
  for _, e in ipairs(entries or {}) do
    if (e.have or 0) < e.units and (merchant and merchant[e.item] or (not merchant and e.source ~= "vendor" and e.source ~= "catch")) then any = true end
  end
  if any then offered = true; ns.ShowShopping(entries) end
end

-- /fwcs shop: whether the list opens with the auction house; `on` and `off` set it
function ns.ShopCommand(arg)
  local s = ns.Settings()
  if arg == "off" then
    s.shop = false
    ns.HideShopping()
    print(PREFIX .. "the shopping list no longer opens with the auction house or a vendor (/fwcs shop on brings it back; the Make button still shows it)")
  elseif arg == "on" then
    s.shop = nil
    print(PREFIX .. "the shopping list opens with the auction house, or a vendor, when the next step needs something bought there")
  elseif s.shop == false then
    print(PREFIX .. "the shopping list does not open with the auction house or a vendor (/fwcs shop on); the Make button still shows it")
  else
    print(PREFIX .. "the shopping list opens with the auction house, or a vendor, when the next step needs something bought there (/fwcs shop off)")
  end
end

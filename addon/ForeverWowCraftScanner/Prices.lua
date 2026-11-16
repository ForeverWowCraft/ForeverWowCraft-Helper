-- The last known lowest auction price on item tooltips: an item hovered (in the bags, the bank, the
-- auction house, a link in chat, the profession window's reagents, loot) shows what one was last
-- listed for at the character's auction house, what the stack under the mouse comes to, and how old
-- that price is. From FWCS_PRICES (Plans.lua: helper 1.8.4 and later write the site's price list of
-- each house there; fwchelper/plans.py says what it holds); nothing is scanned for it. Without it (an
-- earlier helper), for an item it does not list, or for a character whose house is not known, the
-- tooltip is left as it was. The options page has the switch (Background.lua: Settings().tipPrice).
--
-- The client calls in from ns.ScrollTooltip and ns.ScrollTooltipDrawn (ForeverWowCraftScanner.lua),
-- the one hook on item tooltips. A tooltip costs a look-up in the house's table; nothing is built
-- for an item without a price, and nothing runs every frame. The house is found once a session.

local _, ns = ...

local MAX_STACK = 10000             -- a count above this is not taken for a stack

-- the price list of the character's house, found at the first tooltip that can tell; false: none
local list
local function List()
  if list ~= nil then return list or nil end
  local faction = UnitFactionGroup and UnitFactionGroup("player")
  if not faction or faction == "" or not (ns.inv and ns.inv.House) then return nil end     -- too early: the next tooltip asks again
  local ok, _, key = pcall(ns.inv.House)
  local found = ok and key and FWCS_PRICES[key]
  list = type(found) == "table" and type(found.prices) == "table" and found or false
  return list or nil
end

-- the count in a bag or bank slot, when it holds the item
local function SlotCount(bag, slot, id)
  if type(bag) ~= "number" or type(slot) ~= "number" then return nil end
  local item, count
  if C_Container and C_Container.GetContainerItemInfo then
    local info = C_Container.GetContainerItemInfo(bag, slot)
    if type(info) == "table" then item, count = info.itemID, info.stackCount end
  elseif GetContainerItemInfo then
    local _, n, _, _, _, _, _, _, _, i = GetContainerItemInfo(bag, slot)
    item, count = i, n
  end
  if item == id and type(count) == "number" then return count end
end

-- How many of the item the hovered stack holds, where the client says: what filled the tooltip
-- (a bag slot, on clients with tooltip data), else the bag or bank slot the tooltip belongs to.
-- Nil anywhere else (a link, the auction house, a recipe's reagents): no stack line then.
local function StackCount(tooltip, id)
  local info = tooltip.GetPrimaryTooltipInfo and tooltip:GetPrimaryTooltipInfo()
  if type(info) == "table" and info.getterName == "GetBagItem" and type(info.getterArgs) == "table" then
    return SlotCount(info.getterArgs[1], info.getterArgs[2], id)
  end
  local owner = tooltip.GetOwner and tooltip:GetOwner()
  if type(owner) ~= "table" or type(owner.GetID) ~= "function" then return nil end
  local bag
  if type(owner.GetBagID) == "function" then
    bag = owner:GetBagID()
  else
    local parent = type(owner.GetParent) == "function" and owner:GetParent()
    local name = type(parent) == "table" and type(parent.GetName) == "function" and parent:GetName()
    if type(name) == "string" and name:match("^ContainerFrame%d+$") then bag = parent:GetID()
    elseif name == "BankFrame" then bag = BANK_CONTAINER or -1 end
  end
  return SlotCount(bag, owner:GetID(), id)
end

local function Lines(tooltip, id, prices, each)
  tooltip:AddDoubleLine("Auction house", ns.Money(each) .. " each", 1, 1, 1, 1, 1, 1)
  local n = StackCount(tooltip, id)
  if type(n) == "number" and n > 1 and n <= MAX_STACK then
    tooltip:AddDoubleLine("Stack of " .. math.floor(n), ns.Money(each * math.floor(n)), 1, 1, 1, 1, 1, 1)
  end
  local seen = type(prices.seen) == "table" and prices.seen[id] or prices.at
  if type(seen) == "number" and seen > 0 then
    tooltip:AddLine("Price seen " .. ns.Age(seen), 0.6, 0.6, 0.6)
  end
end

-- Tooltips whose clearing is seen (OnTooltipCleared): a client may set the same item on one twice
-- in a row, and the lines go on once a showing.
local watched = {}
local function Watch(tooltip)
  if type(tooltip) ~= "table" or type(tooltip.HookScript) ~= "function" or watched[tooltip] then return end
  if pcall(tooltip.HookScript, tooltip, "OnTooltipCleared", function(self) self.fwcPriced = nil end) then watched[tooltip] = true end
end
Watch(GameTooltip)
Watch(ItemRefTooltip)

ns.priceFailures = 0
function ns.PriceTooltip(tooltip, id)
  if type(FWCS_PRICES) ~= "table" or type(id) ~= "number" or type(FWCS_DB) ~= "table" or type(tooltip) ~= "table" then return end
  if ns.Settings().tipPrice == false then return end
  local prices = List()
  local each = prices and prices.prices[id]
  if type(each) ~= "number" or each <= 0 or type(tooltip.AddDoubleLine) ~= "function" then return end
  if watched[tooltip] and rawget(tooltip, "fwcPriced") == id then return end
  if pcall(Lines, tooltip, id, prices, each) then
    if watched[tooltip] then tooltip.fwcPriced = id end
  else
    ns.priceFailures = ns.priceFailures + 1
  end
end

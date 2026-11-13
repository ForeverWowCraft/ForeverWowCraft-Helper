-- ForeverWowCraft Scanner (the addon folder and its saved-variables file are ForeverWowCraftScanner)
--
-- WHAT THIS FILE GATHERS, AND WHY (everything the addon gathers: docs/scanner-addon.md, "What the
-- addon gathers")
--   WHAT: for each item on its lists, the auctions the house shows of it: unit price, stack size,
--     the time-left band, how many, when; the item's name. The auction house's realm and faction,
--     and the names of the realms this account's characters have logged in on with the addon (as
--     the client spells them: FWCS_DB.__realms, __groups), sent with a scan so that the site can
--     name the house. And the levels of a recipe scroll (see "recipe scrolls" below).
--   WHEN: prices only with the auction house open, when the player scans or the house opens with a
--     scan due (Interface > AddOns turns that off); never in the background. A scroll's levels only
--     when the player brings up its tooltip.
--   WHY: the routes are priced from them, and a recipe's level gate is learned from the scrolls.
--   NEVER: no character name, gold, bags or bank, chat, guild or position goes with a scan. What a
--     character has is kept for /fwc (FWCS_DB.__chars, Inventory.lua) and is never sent.
--   WHERE: the helper sends a scan to the project's pipe, pooled with other players' scans to
--     price the routes.
--
-- Records auction-house price ladders for the items on its lists.
-- The helper fetches the lists and writes Queue.lua into the Plans addon's folder (ForeverWowCraftPlans,
-- loaded after this one) and its own state folder; the Queue.lua beside this file is the one it ships with:
--     FWCS_QUEUE = { ["list name"] = { {itemID, "item name"}, ... }, ... }
-- With the auction house open, the on-screen button runs one of two things:
--   FULL  - C_AuctionHouse.ReplicateItems(): every auction on the house in one server reply
--           (15-minute cooldown per account). Every queued item gets a ladder, empty if unlisted.
--   SCAN  - one C_AuctionHouse.SendSearchQuery per item of a chosen list, paging until the
--           client has all listings. No cooldown, about 0.6 s per item.
-- Results live in the FWCS_DB saved variable, which the client writes to
--     WTF\Account\<account>\SavedVariables\ForeverWowCraftScanner.lua
-- only on /reload or logout; the green SAVE button does that reload (a protected call, so it
-- must come from a click). The helper reads that file.
--
-- /fwc opens a window of its own (Window.lua): the site's routes for the character's auction
-- house, less what the character has in bags and bank. The helper writes the routes into
-- Plans.lua; what a character has is kept in FWCS_DB.__chars and goes nowhere.
--
-- A realm's two faction auction houses are scanned, the Alliance's and the Horde's. Scans are
-- kept by auction house: the key is "<realm>|<faction>", e.g. "Stonespine|Horde". The one
-- both factions share, in the goblin towns, is told apart from where the character stands
-- (see House below) so that its prices are never filed under a faction's, and it is not
-- scanned: it is thin, used for odd purchases and moves between characters, and the routes
-- buy to level (13 Oct 2026). (Scans from before the addon knew the faction are under the
-- realm's name alone; they are left where they are.)
--
-- Stored shape:
--   FWCS_DB[key][itemID] = { name, t, commodity, total, complete, reason, assumed, full,
--                             l = { {unitPrice, quantity, timeLeft}, ... } }   -- ladder, ascending price
--     timeLeft is the auction house's band: 1 short (under 30 min), 2 medium (under 2 h),
--     3 long (under 12 h), 4 very long; nil when the client did not say. Between two scans an
--     auction that vanished while it had hours left was bought or taken down, not expired.
--   FWCS_DB[key].__history[itemID] = { {time, lowestPrice, unitsListed}, ... }  -- one per scan, the last 48 h (48 at most)
--   FWCS_DB.__ui = { pos, hidden, auto, alert, ding, log, lastFull, lastFullRefused, house, remind, arrow, arrowKeep,
--                    arrowPos, winPos, shop, alts, haveFirst, variant, asideOpen, levelRoutes, fishing } -- settings
--   FWCS_DB.__realms = { [name without spaces] = name as shown }   -- this account's realms
--   FWCS_DB.__groups = { [house's realm] = { connected realms, without spaces } }
--   FWCS_DB.__chars = { ["<house's realm>|<character>"] = what it has: see Window.lua }

local _, ns = ...
FWCS_DB = FWCS_DB or {}

-- the brand's colours (docs/brand.md), as hex for "|cff..." and as 0-1 for textures: the
-- logo's gold, the anvil's steel (lightened for text on the dark ground), the icon's navy
ns.BRAND = { gold = "f2b51d", steel = "8fb0e6", navy = "0b1a3a",
             GOLD = { 0.95, 0.71, 0.11 }, STEEL = { 0.56, 0.69, 0.90 }, NAVY = { 0.04, 0.10, 0.23 } }
-- The project's Discord, for feedback and help with the addon and the site (13 Oct 2026): the
-- link the site has (SITE_DISCORD in the core's config), shown by the /fwc window's Feedback button
ns.DISCORD = "https://discord.gg/XPt2JUCxAg"
ns.HELPER_URL = "https://www.foreverwowcraft.com/helper"   -- the helper, for an install without one (Window.lua, ShowHelper)
local PREFIX = "|cff" .. ns.BRAND.gold .. "ForeverWowCraft|r: "
local function Print(msg) print(PREFIX .. msg) end

-- ================================================================ tunables
local SORTS = { { sortOrder = Enum.AuctionHouseSortOrder.Price, reverseSort = false } }
local MAX_WAIT_TICKS = 120      -- 0.25 s ticks to wait for item info / throttle before deferring an item
local MAX_DEFERRALS = 2         -- times an item goes to the back of the queue before being skipped
local MAX_RETRIES = 3           -- retries after a dropped message or an empty result that should not be
local ITEM_TIMEOUT = 8          -- seconds without a result event before skipping an item
local UNANSWERED_GRACE = 1.5    -- gear with no auctions gets no result event at all; call it empty after this
local FULL_TIMEOUT = 120        -- seconds to wait for the snapshot reply: a big auction house takes a while
local FULL_PATIENCE = 30        -- seconds after which the wait is explained
local FULL_COOLDOWN = 15 * 60   -- server-enforced, per account
local AUTO_WAIT = 120           -- seconds the snapshot by itself waits for the shopping list's buying, at most
local LOGIN_RING_DELAY = 5      -- seconds after a login before the "FULL is ready" sound
local TELEMETRY_EVERY = 25      -- items between progress lines in the panel
local HISTORY_MAX = 48          -- price-history points kept per item, at most (one per complete scan that covered it)
local HISTORY_KEEP = 48 * 3600  -- ... and none older than this, in seconds: only developer tools read it, over the last 24 h
local SCAN_SIZE = { 900, 72 }   -- progress bar
local SAVE_SIZE = { 340, 300 }  -- FULL / SCAN / SAVE box
local LOG_LINES, LOG_LINE_HEIGHT = 8, 17

-- ================================================================ saved data helpers
local function Settings()
  FWCS_DB.__ui = FWCS_DB.__ui or {}
  return FWCS_DB.__ui
end

-- An item's price history as kept: the newest HISTORY_MAX points, none older than HISTORY_KEEP, in
-- the order they were. Until 1.8.0 each item kept 200 points, which grew the saved file from 6 to
-- 35 MB though nothing a player sees reads it and the helper does not send it.
local function TrimmedHistory(h, now)
  local out = {}
  for i = math.max(1, #h - HISTORY_MAX + 1), #h do
    local row = h[i]
    if type(row) == "table" and type(row[1]) == "number" and row[1] >= now - HISTORY_KEEP then table.insert(out, row) end
  end
  return out
end

-- At login, every house's history trimmed, so that a player who no longer scans gets a smaller file too.
local function TrimAllHistory()
  local now = time()
  for key, data in pairs(FWCS_DB) do
    if type(key) == "string" and key:sub(1, 2) ~= "__" and type(data) == "table" and type(data.__history) == "table" then
      for item, h in pairs(data.__history) do       -- existing fields only are changed or cleared: allowed while walking
        local kept = type(h) == "table" and TrimmedHistory(h, now) or {}
        data.__history[item] = #kept > 0 and kept or nil
      end
    end
  end
end

-- Two ways to scan. With the bar (FULL / SCAN / SAVE and the progress box) the scanner is in
-- view, for whoever runs the project. Without it the scanner is in the background: a small
-- button on the auction house frame (Background.lua), a scan by itself when the house opens,
-- a sound when there is something to save. The background is the default for everyone: the
-- bar shows only once it is switched on (the options page, Interface, AddOns, or /fwcs bar),
-- and the switch is kept for the account. Until 1.5.6 a helper run from a checkout of the
-- repository wrote FWCS_DEV into Plans.lua and that showed the bar; a stray copy of such a
-- Plans.lua put the bar in front of a player (6 Nov 2026), so nothing in a file decides now.
local function BarHidden()
  local s = Settings()
  if s.hidden ~= nil then return s.hidden end
  return true
end
local function AutoScanEnabled()
  local s = Settings()
  if s.auto ~= nil then return s.auto end
  return BarHidden()
end

-- The auction houses of the goblin towns are one house, shared by both factions, and it is
-- not scanned. They are told by the map the character is on (the only auction house of each
-- of these zones is the goblins'), or by the town's name where the client is in English. NOT
-- VERIFIED on Forever: /fwcs house says what the addon takes the open house for, /fwcs house
-- neutral (or horde, alliance) overrules it.
local NEUTRAL_MAPS = {
  [1434] = true, [1446] = true, [1452] = true,     -- Stranglethorn Vale, Tanaris, Winterspring (Classic Era maps)
  [210] = true, [71] = true, [83] = true,          -- The Cape of Stranglethorn, Tanaris, Winterspring (later maps)
}
local NEUTRAL_TOWNS = { ["Booty Bay"] = true, ["Gadgetzan"] = true, ["Everlook"] = true }
local openHouse = nil            -- the house last opened in this session; nil before any was

local function HouseHere()
  local map = C_Map and C_Map.GetBestMapForUnit and C_Map.GetBestMapForUnit("player")
  if (map and NEUTRAL_MAPS[map]) or NEUTRAL_TOWNS[GetSubZoneText and GetSubZoneText() or ""]
     or NEUTRAL_TOWNS[GetMinimapZoneText and GetMinimapZoneText() or ""] then
    return "Neutral"
  end
  return (UnitFactionGroup and UnitFactionGroup("player")) or ""
end

-- The faction of the auction house that scans are of: what the player said (/fwcs house), else
-- the house last opened, else the character's own.
local function Faction()
  local said = FWCS_DB.__ui and FWCS_DB.__ui.house
  return said or openHouse or (UnitFactionGroup and UnitFactionGroup("player")) or ""
end

-- The house both factions share is not scanned (see the top of the file); a scan asked for
-- there says so instead.
local SHARED_NOT_SCANNED = "this is the auction house both factions share, and it is not scanned: the site has your faction's house."
  .. " If the addon has the house wrong, /fwcs house horde (or alliance) says which it is."
local function SharedHouse() return Faction() == "Neutral" end

-- Connected realms share one auction house, so its scans are kept under one name: the first
-- of the group's realms as the client spells them without spaces (GetAutoCompleteRealms, which
-- every character of the group sees alike). A realm of its own keeps its name as shown. The
-- names as shown are kept too, for the site.
local function ShortName(name) return (name:gsub("[%s%-']", "")) end

local function ConnectedRealms()
  local group = GetAutoCompleteRealms and GetAutoCompleteRealms() or nil
  if type(group) ~= "table" or #group < 2 then return nil end
  local sorted = {}
  for _, name in ipairs(group) do table.insert(sorted, name) end
  table.sort(sorted)
  return sorted
end

local function RealmKey()
  local group = ConnectedRealms()
  return group and group[1] or GetRealmName() or "?"
end

local function NoteRealmNames()
  local name = GetRealmName() or "?"
  FWCS_DB.__realms = FWCS_DB.__realms or {}
  FWCS_DB.__realms[(GetNormalizedRealmName and GetNormalizedRealmName()) or ShortName(name)] = name
  local group = ConnectedRealms()
  if group then
    FWCS_DB.__groups = FWCS_DB.__groups or {}
    FWCS_DB.__groups[group[1]] = group
  end
end

-- Scans kept under this character's own realm name from before connected realms were told
-- apart go under the group's name; of an item in both, the more recent look stays.
local function AdoptOldKeys()
  local key = RealmKey()
  local own = GetRealmName() or "?"
  if key == own then return end
  local found = {}      -- gathered first: a table is not changed while it is walked
  for old, data in pairs(FWCS_DB) do
    local realm, faction
    if type(old) == "string" then realm, faction = old:match("^(.-)|(.*)$") end
    if realm == own and type(data) == "table" then table.insert(found, { old, faction, data }) end
  end
  for _, f in ipairs(found) do
    local old, faction, data = f[1], f[2], f[3]
    do
      local new = key .. "|" .. faction
      FWCS_DB[new] = FWCS_DB[new] or {}
      local into = FWCS_DB[new]
      for k, v in pairs(data) do
        if k == "__history" then
          into.__history = into.__history or {}
          for item, rows in pairs(v) do
            into.__history[item] = into.__history[item] or {}
            for _, row in ipairs(rows) do table.insert(into.__history[item], row) end
          end
        elseif type(k) == "number" then
          if not into[k] or (v.t or 0) > (into[k].t or 0) then into[k] = v end
        else
          into[k] = into[k] or v
        end
      end
      FWCS_DB[old] = nil
      Print(string.format("scans kept as %s are now kept as %s: this realm shares its auction house with %s.",
        own, key, table.concat(ConnectedRealms() or {}, ", ")))
    end
  end
end

local function DatasetKey()
  return RealmKey() .. "|" .. Faction()
end

local function DatasetName()
  local faction = Faction()
  return RealmKey() .. (faction ~= "" and (" (" .. faction .. ")") or "")
end

local function RealmDB()
  local key = DatasetKey()
  FWCS_DB[key] = FWCS_DB[key] or {}
  return FWCS_DB[key]
end

local function QueueNames()
  local names = {}
  for name in pairs(FWCS_QUEUE or {}) do table.insert(names, name) end
  table.sort(names)
  return names
end

-- union of every queued list: itemID -> name
local function QueuedItems()
  local items = {}
  for _, rows in pairs(FWCS_QUEUE or {}) do
    for _, row in ipairs(rows) do
      if type(row[1]) == "number" then items[row[1]] = row[2] end
    end
  end
  return items
end

local function CountKeys(t)
  local n = 0
  for _ in pairs(t) do n = n + 1 end
  return n
end

local function ItemName(itemID, fallback)
  return C_Item.GetItemInfo(itemID) or fallback
end

local function FormatClock(seconds)
  seconds = math.max(0, math.floor(seconds + 0.5))
  return string.format("%d:%02d", math.floor(seconds / 60), seconds % 60)
end

-- The snapshot's cooldown is the server's, per account, and starts whenever an auction list
-- arrives: at our snapshot, or at another addon's. lastFull is the time of the last list that
-- arrived on this client (account-wide, wall-clock, so it holds across characters and logins).
-- A request nothing came of means a cooldown is running that this client did not see start
-- (another PC, or before the addon was installed): lastFullRefused holds it, and the button
-- stays off until 15 minutes after it at the latest (no shift-click past it since 1.6.23: the user).
local function FullCooldownLeft()
  local s = Settings()
  local since = math.max(s.lastFull or 0, s.lastFullRefused or 0)
  return math.max(0, FULL_COOLDOWN - (time() - since))
end

-- whether the cooldown's end is known, or only its latest possible end (after a refusal)
local function FullCooldownKnown()
  local s = Settings()
  return (s.lastFull or 0) >= (s.lastFullRefused or 0)
end

-- an auction list arrived (ours or another addon's): the cooldown starts now
local function NoteFullArrived()
  local s = Settings()
  s.lastFull, s.lastFullRefused = time(), nil
end

-- ReloadUI first, the newer C_UI.Reload where there is no other, and an error said rather
-- than swallowed. Forever's client lets no addon call either, even from a click (6 Nov 2026):
-- there the buttons that reload are secure ones with a macro of their own, /reload (the bar's
-- SAVE, ui.save; the reminder's Reload now), and this is the typed command's try
local function DoReload()
  local ok, err = pcall(function()
    if ReloadUI then ReloadUI() elseif C_UI and C_UI.Reload then C_UI.Reload() else error("no reload function") end
  end)
  if not ok then Print("the reload was refused: " .. tostring(err) .. ". /reload, typed, does the same.") end
end

-- ================================================================ state
local dirty = false   -- something recorded since the last save
local state = {
  running = false,
  kind = nil,         -- "scan" | "snapshot"
  ahOpen = false,
  listIndex = 1,      -- what the button runs: 1 = FULL, 2.. = SCAN of QueueNames()[listIndex-1]
  debug = false,
  -- per-item scan
  queue = {}, current = nil, ticks = 0, retries = 0,
  token = 0,          -- invalidates timeouts / grace checks when the current item changes
  attempt = 0,        -- invalidates stale AttemptSearch chains
  waitingThrottle = false,
  -- progress + telemetry
  total = 0, done = 0, skipped = 0, deferrals = 0, skipReasons = {},
  pages = 0, listings = 0, withAuctions = 0, noAuctions = 0, assumed = 0,
  startedAt = nil, lastDuration = nil,
}

-- The freshness gate (Fresh.lua, written by the helper from the pipe): the FULL / SCAN box is
-- not offered while this auction house's newest scan, by anyone, is fresh (under `fresh`
-- old) by what the helper fetched in the last half hour: the pipe takes one scan of a house
-- in that time and refuses the rest, however many play, so the box would only waste a
-- cooldown. Decided once a visit. SAVE shows regardless (what was scanned is kept), /fwcs full
-- scans regardless, and /fwcs offer brings the box for this visit.
local function FreshOf()
  local f = FWCS_FRESH
  if type(f) ~= "table" or type(f.houses) ~= "table" then return nil, f end
  local realm = f.houses[RealmKey()]
  return type(realm) == "table" and (realm[Faction()] or realm[""]) or nil, f
end
local function FreshFor()                -- seconds the house's newest scan stays fresh, 0 when it is not (or not known lately)
  local h, f = FreshOf()
  if not (h and h.newest) then return 0 end
  local told, keeps = tonumber(f.written) or 0, tonumber(f.fresh) or 600
  if time() - told >= 1800 then return 0 end
  return math.max(0, tonumber(h.newest) + keeps - time())
end
local function Offered()
  if state.offered == nil then state.offered = FreshFor() <= 0 end
  return state.offered
end

-- forward declarations for functions the UI calls before their definition
local UpdateStatus, StartScan, StartSnapshot

-- ================================================================ status UI
local ui = CreateFrame("Frame", "ForeverWowCraftScannerStatus", UIParent, "BackdropTemplate")
ui:SetFrameStrata("HIGH")
ui:SetClampedToScreen(true)
ui:SetMovable(true)
ui:EnableMouse(true)
ui:RegisterForDrag("LeftButton")
ui:SetBackdrop({ bgFile = "Interface\\Tooltips\\UI-Tooltip-Background", edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
  edgeSize = 12, insets = { left = 3, right = 3, top = 3, bottom = 3 } })
ui:SetBackdropColor(0, 0, 0, 0.8)
ui:Hide()

ui.bar = CreateFrame("StatusBar", nil, ui)
ui.bar:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar")
ui.bar:SetMinMaxValues(0, 1)

-- SAVE as a secure button over the whole bar, with a macro of its own, /reload: the game runs
-- it for a click where it blocks an addon's own ReloadUI (Forever's client, 6 Nov 2026). Shown
-- with the save mode, outside a fight: a protected frame is neither shown nor hidden in one,
-- so the fight's end (PLAYER_REGEN_ENABLED, below) draws the bar again
ui.save = CreateFrame("Button", "ForeverWowCraftScannerSave", ui, "SecureActionButtonTemplate")
ui.save:SetAllPoints(ui)
ui.save:SetFrameLevel(ui:GetFrameLevel() + 5)
ui.save:SetAttribute("type", "macro")
ui.save:SetAttribute("macrotext", "/reload")
ui.save:RegisterForClicks("AnyDown", "AnyUp")
ui.save:RegisterForDrag("LeftButton")
ui.save:Hide()
local function SaveButton(on)
  if InCombatLockdown and InCombatLockdown() then return end
  if on then ui.save:Show() else ui.save:Hide() end
end

local function Font(fs, size, flags)
  local path = fs:GetFont()
  fs:SetFont(path, size, flags or "")
  return fs
end

-- box modes: big label + subtitle
ui.big = Font(ui.bar:CreateFontString(nil, "OVERLAY", "GameFontNormalHuge"), 88, "OUTLINE")
ui.big:SetPoint("CENTER", 0, 12)
ui.text = Font(ui.bar:CreateFontString(nil, "OVERLAY", "GameFontHighlight"), 16)
ui.text:SetPoint("BOTTOM", 0, 12)
ui.text:SetWidth(SAVE_SIZE[1] - 16)

-- scanning mode: fixed columns so nothing shifts as names and numbers change
ui.cols = {}
local function MakeCol(key, width, justify, anchorTo)
  local fs = Font(ui.bar:CreateFontString(nil, "OVERLAY", "GameFontHighlight"), 16)
  fs:SetSize(width, 24)
  fs:SetJustifyH(justify)
  fs:SetWordWrap(false)
  if anchorTo then fs:SetPoint("LEFT", anchorTo, "RIGHT", 8, 0) else fs:SetPoint("LEFT", ui.bar, "LEFT", 16, 0) end
  ui.cols[key] = fs
  return fs
end
MakeCol("count", 190, "LEFT")
MakeCol("item", 380, "LEFT", ui.cols.count)
MakeCol("elapsed", 140, "RIGHT", ui.cols.item)
MakeCol("eta", 130, "RIGHT", ui.cols.elapsed)

-- telemetry panel: chat-style, mouse wheel scrolls, keeps the whole scan's history
ui.log = CreateFrame("ScrollingMessageFrame", nil, ui)
ui.log:SetFontObject(GameFontHighlight)
Font(ui.log, 14)
ui.log:SetJustifyH("LEFT")
ui.log:SetFading(false)
ui.log:SetMaxLines(1000)
ui.log:SetInsertMode(SCROLLING_MESSAGE_FRAME_INSERT_MODE_BOTTOM)
ui.log:SetTextColor(0.85, 0.85, 0.85)
ui.log:EnableMouseWheel(true)
ui.log:SetScript("OnMouseWheel", function(self, delta)
  if IsShiftKeyDown() then
    if delta > 0 then self:ScrollToTop() else self:ScrollToBottom() end
  elseif delta > 0 then self:ScrollUp() else self:ScrollDown() end
end)

-- drop-down arrow: choose what the box runs
ui.arrow = CreateFrame("Button", nil, ui)
ui.arrow:SetSize(40, 40)
ui.arrow:SetPoint("LEFT", ui, "RIGHT", 2, 0)
ui.arrow:SetNormalTexture("Interface\\ChatFrame\\UI-ChatIcon-ScrollDown-Up")
ui.arrow:SetPushedTexture("Interface\\ChatFrame\\UI-ChatIcon-ScrollDown-Down")
ui.arrow:SetHighlightTexture("Interface\\Buttons\\UI-Common-MouseHilight", "ADD")
ui.arrow:SetScript("OnEnter", function(self)
  GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
  GameTooltip:AddLine("Choose what the button runs")
  GameTooltip:Show()
end)
ui.arrow:SetScript("OnLeave", GameTooltip_Hide)
ui.arrow:SetScript("OnClick", function(self)
  local names = QueueNames()
  local function pick(i) state.listIndex = i; UpdateStatus() end
  if MenuUtil and MenuUtil.CreateContextMenu then
    MenuUtil.CreateContextMenu(self, function(_, root)
      root:CreateTitle("What the button runs")
      root:CreateRadio("Full AH snapshot (all lists, 15-min cooldown)",
        function() return state.listIndex == 1 end, function() pick(1) end)
      for i, name in ipairs(names) do
        root:CreateRadio(string.format("Scan %s (%d items)", name, #(FWCS_QUEUE[name] or {})),
          function() return state.listIndex == i + 1 end, function() pick(i + 1) end)
      end
    end)
  else
    pick(state.listIndex % (#names + 1) + 1)
  end
end)

local COLORS = {
  progress = { 0.2, 0.6, 1.0 },
  scan = { 0.2, 0.5, 0.9 }, scanHover = { 0.3, 0.65, 1.0 },
  save = { 0.15, 0.65, 0.25 }, saveHover = { 0.25, 0.85, 0.35 },
  disabled = { 0.35, 0.35, 0.38 },
}
local function BarColor(c) ui.bar:SetStatusBarColor(c[1], c[2], c[3]) end

-- layout helpers: the bar either fills the box or sits on top of the telemetry panel
local function LayoutBox(w, h)
  ui:SetSize(w, h)
  ui.bar:ClearAllPoints()
  ui.bar:SetPoint("TOPLEFT", 4, -4)
  ui.bar:SetPoint("BOTTOMRIGHT", -4, 4)
  ui.bar:SetMinMaxValues(0, 1)
  ui.bar:SetValue(1)
  for _, fs in pairs(ui.cols) do fs:Hide() end
  ui.log:Hide()
  ui.big:Show()
  ui.text:Show()
end

local function LayoutProgress(showLog)
  local logHeight = showLog and (LOG_LINES * LOG_LINE_HEIGHT + 12) or 0
  ui:SetSize(SCAN_SIZE[1], SCAN_SIZE[2] + logHeight)
  ui.bar:ClearAllPoints()
  ui.bar:SetPoint("TOPLEFT", 4, -4)
  ui.bar:SetPoint("TOPRIGHT", -4, -4)
  ui.bar:SetHeight(SCAN_SIZE[2] - 8)
  for _, fs in pairs(ui.cols) do fs:Show() end
  ui.big:Hide()
  ui.text:Hide()
  ui.arrow:Hide()
  if showLog then
    ui.log:ClearAllPoints()
    ui.log:SetPoint("TOPLEFT", ui.bar, "BOTTOMLEFT", 8, -6)
    ui.log:SetSize(SCAN_SIZE[1] - 24, logHeight - 10)
    ui.log:Show()
  else
    ui.log:Hide()
  end
end

UpdateStatus = function()
  local s = Settings()
  if ns.OnScannerChanged then ns.OnScannerChanged() end     -- the small button on the auction house frame
  if BarHidden() then ui:Hide(); return end

  if state.running then
    ui.mode = "progress"; SaveButton(false)
    LayoutProgress(s.log == true)                   -- the telemetry panel: off unless switched on (the shipped defaults, 7 Nov 2026)
    local finished = state.done + state.skipped
    local elapsed = state.startedAt and (GetTime() - state.startedAt) or 0
    ui.bar:SetMinMaxValues(0, math.max(1, state.total))
    ui.bar:SetValue(finished)
    BarColor(COLORS.progress)
    local digits = #tostring(state.total)
    ui.cols.count:SetFormattedText("Scanning %0" .. digits .. "d/%d", finished, state.total)
    if state.current then
      ui.cols.item:SetText(ItemName(state.current.itemID, state.current.name) or "")
    end
    ui.cols.elapsed:SetFormattedText("%s elapsed", FormatClock(elapsed))
    if finished >= 3 and elapsed > 0 then
      ui.cols.eta:SetFormattedText("~%s left", FormatClock(elapsed / finished * (state.total - finished)))
    else
      ui.cols.eta:SetText("~-:-- left")
    end
    ui:Show()

  elseif dirty then
    ui.mode = "save"
    ui.disabled = false
    LayoutBox(SAVE_SIZE[1], SAVE_SIZE[2])
    ui.arrow:Hide()
    BarColor(COLORS.save)
    ui.big:SetText("SAVE")
    ui.big:SetTextColor(1, 1, 1)
    local when = state.lastDuration and ("  in " .. FormatClock(state.lastDuration)) or ""
    if state.kind == "snapshot" and state.snapAuctions then
      ui.text:SetFormattedText("%s auctions read, %s priced%s\nclick to write to disk", FormatLargeNumber(state.snapAuctions),
        FormatLargeNumber(state.snapPriced or 0), when)
    else
      ui.text:SetFormattedText("%d recorded, %d skipped%s\nclick to write to disk", state.done, state.skipped, when)
    end
    ui:Show()
    SaveButton(true)

  elseif state.ahOpen and #QueueNames() > 0 and Offered() then
    local names = QueueNames()
    if state.listIndex < 1 or state.listIndex > #names + 1 then state.listIndex = 1 end
    local isFull = state.listIndex == 1
    local cooldown = isFull and FullCooldownLeft() or 0
    ui.mode = "scan"; SaveButton(false)
    ui.disabled = cooldown > 0
    LayoutBox(SAVE_SIZE[1], SAVE_SIZE[2])
    ui.arrow:Show()
    BarColor(ui.disabled and COLORS.disabled or COLORS.scan)
    ui.big:SetText(isFull and "FULL" or "SCAN")
    ui.big:SetTextColor(ui.disabled and 0.6 or 1, ui.disabled and 0.6 or 1, ui.disabled and 0.6 or 1)
    if isFull then
      ui.text:SetFormattedText("Full AH snapshot, all lists\n%d items  |  %s", CountKeys(QueuedItems()),
        cooldown <= 0 and "ready" or FullCooldownKnown() and ("available in " .. FormatClock(cooldown))
        or ("on cooldown, ready in " .. FormatClock(cooldown) .. " at the latest"))
      if not state.idleTicker then   -- live countdown
        state.idleTicker = C_Timer.NewTicker(1, function()
          if ui.mode ~= "scan" or state.listIndex ~= 1 then
            state.idleTicker:Cancel(); state.idleTicker = nil
          else
            UpdateStatus()
          end
        end)
      end
    else
      local name = names[state.listIndex - 1]
      ui.text:SetFormattedText("Per-item scan\n%s  (%d items)", name, #(FWCS_QUEUE[name] or {}))
    end
    ui:Show()

  else
    ui.mode = nil; SaveButton(false)
    ui.arrow:Hide()
    ui:Hide()
  end
end

ui:SetScript("OnMouseUp", function(self, button)
  if not self.dragging and not state.running then
    if ui.mode == "save" and button == "LeftButton" then
      DoReload()
    elseif ui.mode == "scan" and button == "LeftButton" then
      if state.listIndex == 1 then
        if not ui.disabled then StartSnapshot(false) end
      else
        StartScan(QueueNames()[state.listIndex - 1])
      end
    elseif ui.mode == "scan" and button == "RightButton" then
      state.listIndex = state.listIndex % (#QueueNames() + 1) + 1
      UpdateStatus()
    end
  end
  self.dragging = false
end)
ui:SetScript("OnDragStart", function(self) self.dragging = true; self:StartMoving() end)
ui:SetScript("OnDragStop", function(self)
  self:StopMovingOrSizing()
  local point, _, relPoint, x, y = self:GetPoint()
  Settings().pos = { point, relPoint, x, y }
end)
ui:SetScript("OnEnter", function(self)
  if ui.mode == "save" then BarColor(COLORS.saveHover)
  elseif ui.mode == "scan" and not ui.disabled then BarColor(COLORS.scanHover) end
  GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
  GameTooltip:AddLine("ForeverWowCraft Scanner")
  GameTooltip:AddLine("Drag to move. Blue: click to run (arrow / right-click picks what). Green: click to save (reloads the UI).", 1, 1, 1)
  GameTooltip:AddLine("Telemetry panel: mouse wheel scrolls, shift+wheel jumps to top/bottom. /fwcs for commands.", 1, 1, 1)
  GameTooltip:Show()
end)
ui:SetScript("OnLeave", function()
  if ui.mode == "save" then BarColor(COLORS.save)
  elseif ui.mode == "scan" and not ui.disabled then BarColor(COLORS.scan) end
  GameTooltip:Hide()
end)
-- the SAVE button over the bar is dragged, hovered and left as the bar is
for _, name in ipairs({ "OnDragStart", "OnDragStop", "OnEnter", "OnLeave" }) do
  ui.save:SetScript(name, function() local fn = ui:GetScript(name); if type(fn) == "function" then fn(ui) end end)
end
local regen = CreateFrame("Frame")
regen:RegisterEvent("PLAYER_REGEN_ENABLED")
regen:SetScript("OnEvent", function() UpdateStatus() end)      -- the SAVE button, left as it was through the fight

local function RestorePosition()
  local pos = Settings().pos
  ui:ClearAllPoints()
  if pos then ui:SetPoint(pos[1], UIParent, pos[2], pos[3], pos[4]) else ui:SetPoint("TOP", UIParent, "TOP", 0, -140) end
end

-- ================================================================ telemetry + recording
local function Log(line)
  local elapsed = state.startedAt and (GetTime() - state.startedAt) or 0
  ui.log:AddMessage(string.format("|cff9d9d9d%s|r  %s", FormatClock(elapsed), line))
  if state.debug then Print(line) end
  UpdateStatus()
end

local function LogProgress()
  local finished = state.done + state.skipped
  local elapsed = state.startedAt and (GetTime() - state.startedAt) or 0
  Log(string.format("%d/%d  %.2f s/item  |  %d with auctions, %d none (%d unanswered gear), %d skipped, %d deferred  |  %d extra pages, %s listings",
    finished, state.total, finished > 0 and elapsed / finished or 0, state.withAuctions, state.noAuctions, state.assumed,
    state.skipped, state.deferrals, state.pages, FormatLargeNumber(state.listings)))
end

-- ================================================================ recipe scrolls: three levels
-- WHAT: for a recipe scroll (an item of the Recipe class, nothing else), FWCS_DB.__recipes[item id]
-- = { l, t, tip, made, madel }:
--   l     the scroll's own minimum level from the game's item data (GetItemInfo, 5th value);
--   tip   each "Requires Level N" line on the scroll's tooltip, as { line, N, line, N, ... }:
--         the line's position on the tooltip, then its level (one line on every scroll seen, so
--         two numbers; a second such line would add two more, nothing is merged or dropped);
--   made  the item the recipe makes, when the client says which; madel its minimum level
--         from the item data;
--   t     when a number last changed.
-- WHEN: only when the player brings up a scroll's tooltip (hovering it in the bags, at a vendor,
-- at the auction house, a link in chat), read from the tooltip the game has just drawn; once a
-- scroll a session. The addon never draws a tooltip itself and never walks the bags or the house
-- for scrolls. `l` alone is also looked at for the recipes the auction scan records and the
-- route buys (ns.NoteRecipeLevel).
-- WHY: the level a recipe is gated at. On Forever's client the item data says 1 for every scroll
-- seen; the tooltip of Recipe: Elixir of Intellect (250389) has "Requires Level 45" between the
-- made item's "Use:" text and the scroll's own "Use: Teaches ..." line, and the project takes
-- that line as the recipe's gate (data/overrides/recipe_levels.json, by hand). The three numbers
-- side by side, over every scroll players hover, show how they relate; nothing is gated by them
-- yet.
-- NEVER: nothing of the character: not its name, its level, its gold or what else it carries.
-- WHERE: the helper sends the rows with the vendors met (fwchelper/pipe.py vendors_document) to
-- the project's pipe, pooled with other players' sightings to know Forever's vendors, trainers
-- and recipes. Everything gathered is listed in docs/scanner-addon.md,
-- "What the addon gathers".

local function ItemData(item)                -- the client's item info, whichever name it has
  local info = C_Item and C_Item.GetItemInfo or GetItemInfo
  if info then return info(item) end
end

-- the level of a scroll as the item data gives it, kept from 2 up (a 1 says nothing on its
-- own): for the recipes the auction scan records and the route buys (Verdict.lua). Returns the
-- level when the client has the item's data and it is 2 or more, else nil. A row the tooltip
-- made is updated in place, its other numbers kept.
function ns.NoteRecipeLevel(itemID)
  if type(itemID) ~= "number" then return nil end
  local instant = C_Item and C_Item.GetItemInfoInstant or GetItemInfoInstant
  if not instant then return nil end
  local ok, _, _, _, _, _, classID = pcall(instant, itemID)
  if not ok or classID ~= 9 then return nil end                -- 9: a recipe
  local ok2, _, _, _, _, minLevel = pcall(ItemData, itemID)
  if not ok2 or type(minLevel) ~= "number" then return nil end
  local level = math.floor(minLevel)
  if level <= 1 then return nil end                            -- no level asked: no row, and none made up
  FWCS_DB.__recipes = FWCS_DB.__recipes or {}
  local row = FWCS_DB.__recipes[itemID]
  if not row then FWCS_DB.__recipes[itemID] = { l = level, t = time() }
  elseif row.l ~= level then row.l, row.t = level, time() end
  return level
end
-- the rows with nothing to say, let go once at login: a level of 1 or none and no tooltip
-- level (kept by addons before 1.7.4); no row is sent for them
function ns.DropRecipesWithoutLevel()
  for itemID, row in pairs(FWCS_DB.__recipes or {}) do
    if type(row) ~= "table" or not ((tonumber(row.l) or 0) > 1 or (type(row.tip) == "table" and #row.tip > 0)) then FWCS_DB.__recipes[itemID] = nil end
  end
end

local looked = {}        -- [item id] = true: looked at this session (a scroll read, or not a scroll)
local madeFor = {}       -- [made item id] = scroll, while the made item's data is on its way
local levelPattern       -- ITEM_MIN_LEVEL as a pattern, made once (false: the client has none)

-- "Requires Level %d", in the client's language, as a pattern that takes the number
local function LevelPattern()
  if levelPattern == nil then
    levelPattern = false
    if type(ITEM_MIN_LEVEL) == "string" and ITEM_MIN_LEVEL ~= "" then
      local p = ITEM_MIN_LEVEL:gsub("[%%%(%)%.%+%-%*%?%[%]%^%$]", "%%%0")
      p = p:gsub("%%%%%d+%%%$d", "(%%d+)"):gsub("%%%%d", "(%%d+)"):gsub("%%%%%d*%%?%$?s", ".-")
      levelPattern = "^%s*" .. p .. "%s*$"
    end
  end
  return levelPattern
end

local function Same(a, b)
  if a == b then return true end
  if type(a) ~= "table" or type(b) ~= "table" or #a ~= #b then return false end
  for i = 1, #a do if a[i] ~= b[i] then return false end end
  return true
end

-- the row of a scroll, rewritten only when a number changed
local function Keep(itemID, numbers)
  FWCS_DB.__recipes = FWCS_DB.__recipes or {}
  local row = FWCS_DB.__recipes[itemID] or {}
  local changed = FWCS_DB.__recipes[itemID] == nil
  for k, v in pairs(numbers) do
    if not Same(row[k], v) then row[k], changed = v, true end
  end
  if changed then row.t = time(); FWCS_DB.__recipes[itemID] = row end
end

-- the made item's data came late: its level goes in the scroll's row (one table look-up for any
-- other item the client loads, and the events are let go when nothing is awaited)
local madeLoads = CreateFrame("Frame")
madeLoads:SetScript("OnEvent", function(self, _, item)
  local scroll = madeFor[item]
  if not scroll then return end
  madeFor[item] = nil
  local ok, _, _, _, _, minLevel = pcall(ItemData, item)                  -- as unproven as the tooltip: nothing may escape
  if ok and type(minLevel) == "number" and type(FWCS_DB) == "table" then Keep(scroll, { made = item, madel = math.floor(minLevel) }) end
  if next(madeFor) == nil and self.UnregisterAllEvents then self:UnregisterAllEvents() end
end)

-- a scroll's tooltip, read once: `texts` its lines in order, `made` the made item's id when the
-- tooltip data names it (a nested item block)
local function ReadScroll(itemID, texts, made)
  local _, _, _, _, minLevel = ItemData(itemID)
  if type(minLevel) ~= "number" then return end      -- the scroll's own data not in: the next hover reads it
  looked[itemID] = true
  local tip, pattern = nil, LevelPattern()
  for i, text in ipairs(pattern and texts or {}) do
    local n = tonumber(text:match(pattern))
    if n then tip = tip or {}; table.insert(tip, i); table.insert(tip, n) end
  end
  local level = math.floor(minLevel)
  if not tip and level <= 1 then return end          -- nothing to say: no row
  local numbers = { l = level, tip = tip }
  local madeName
  if not made then                                   -- the made item by its name, the line the client sets off with a new line
    for i = 2, #texts do
      madeName = texts[i]:match("^\n%s*(.-)%s*$")
      if madeName and madeName ~= "" then break end
      madeName = nil
    end
  end
  local _, link, madeLevel
  if made then
    madeLevel = select(5, ItemData(made))            -- one look-up; the client asks the server when it has not the data
  elseif madeName then
    _, link, _, _, madeLevel = ItemData(madeName)    -- by name: only what the client already has, nothing is asked
    made = link and tonumber(link:match("item:(%d+)"))
    if not made then madeLevel = nil end
  end
  if made then
    numbers.made = made
    if type(madeLevel) == "number" then numbers.madel = math.floor(madeLevel)
    else
      madeFor[made] = itemID
      for _, e in ipairs({ "GET_ITEM_INFO_RECEIVED", "ITEM_DATA_LOAD_RESULT" }) do pcall(madeLoads.RegisterEvent, madeLoads, e) end
    end
  end
  Keep(itemID, numbers)
end

local function Recipe(itemID)               -- whether an item is a recipe scroll; looked at once a session
  local instant = C_Item and C_Item.GetItemInfoInstant or GetItemInfoInstant
  local classID = instant and select(6, instant(itemID))
  if classID ~= 9 then looked[itemID] = true; return false end      -- 9: a recipe
  return true
end

local function FromData(id, data)
  if not Recipe(id) then return end
  local surface = TooltipUtil and TooltipUtil.SurfaceArgs
  local texts, made = {}, nil
  for i, line in ipairs(data.lines) do
    if line.leftText == nil and surface then surface(line) end
    texts[i] = type(line.leftText) == "string" and line.leftText or ""
    if not made and type(line.tooltipID) == "number" and (line.tooltipType == nil or not (Enum and Enum.TooltipDataType) or line.tooltipType == Enum.TooltipDataType.Item) then
      made = line.tooltipID ~= id and line.tooltipID or nil
    end
  end
  ReadScroll(id, texts, made)
end

local function FromDrawn(id, tooltip)
  if not Recipe(id) then return end
  local texts, name = {}, tooltip.GetName and tooltip:GetName()
  for i = 1, (name and tooltip.NumLines and tooltip:NumLines()) or 0 do
    local left = _G[name .. "TextLeft" .. i]
    texts[i] = left and left.GetText and left:GetText() or ""
  end
  ReadScroll(id, texts, nil)
end

-- This runs inside the client's own tooltip handling, for every item tooltip, in a fight too, and
-- what this client gives there is not all proven (9 Nov 2026): nothing may escape it. What fails
-- is let be for the session (the item counted as looked at) and counted, for `/fwcs debug`.
ns.scrollFailures = 0
local function Guarded(read, id, arg)
  local ok = pcall(read, id, arg)
  if not ok then looked[id] = true; ns.scrollFailures = ns.scrollFailures + 1 end
end

-- the client's tooltip data for an item (TooltipDataProcessor): data.id is the item, data.lines
-- what the tooltip shows. Anything looked at before costs the one look-up.
function ns.ScrollTooltip(_, data)
  local id = type(data) == "table" and data.id
  if looked[id] or type(id) ~= "number" or type(FWCS_DB) ~= "table" then return end
  Guarded(FromData, id, data)
end

-- a client without tooltip data: the item from the tooltip drawn, its lines from its own text
function ns.ScrollTooltipDrawn(tooltip)
  if type(FWCS_DB) ~= "table" then return end
  local ok, _, link = pcall(tooltip.GetItem, tooltip)
  local id = ok and type(link) == "string" and tonumber(link:match("item:(%d+)"))
  if not id or looked[id] then return end
  Guarded(FromDrawn, id, tooltip)
end

if TooltipDataProcessor and TooltipDataProcessor.AddTooltipPostCall and Enum and Enum.TooltipDataType and Enum.TooltipDataType.Item then
  TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Item, ns.ScrollTooltip)
else
  for _, tooltip in ipairs({ GameTooltip, ItemRefTooltip }) do
    if tooltip and tooltip.HookScript then tooltip:HookScript("OnTooltipSetItem", ns.ScrollTooltipDrawn) end
  end
end

-- entry = { itemID, name, isCommodity?, assumedEmpty?, full?, attempts? }
local function Record(entry, listings, complete, reason)
  dirty = true
  ns.NoteRecipeLevel(entry.itemID)
  local total = 0
  for _, row in ipairs(listings) do total = total + row[2] end
  if complete then
    state.listings = state.listings + #listings
    if #listings > 0 then
      state.withAuctions = state.withAuctions + 1
    else
      state.noAuctions = state.noAuctions + 1
      if entry.assumedEmpty then state.assumed = state.assumed + 1 end
    end
  end
  RealmDB()[entry.itemID] = {
    name = ItemName(entry.itemID, entry.name),
    t = time(),
    commodity = entry.isCommodity and true or nil,
    total = total,
    complete = complete and true or false,
    reason = (not complete) and reason or nil,   -- why it was skipped
    assumed = entry.assumedEmpty or nil,          -- gear that never answered: taken as no auctions
    full = entry.full or nil,                     -- from a snapshot rather than a per-item search
    attempts = entry.attempts,
    l = listings,
  }
  if complete then
    -- compact per-item history: {time, lowest unit price (0 = none listed), units listed}
    local db = RealmDB()
    db.__history = db.__history or {}
    local h = db.__history[entry.itemID] or {}
    table.insert(h, { time(), listings[1] and listings[1][1] or 0, total })
    db.__history[entry.itemID] = TrimmedHistory(h, time())
  end
end

-- ================================================================ scan lifecycle
local function AlertEnabled() return Settings().alert ~= false end

local pulseToken = 0
local function PulseBar()
  if not AlertEnabled() or BarHidden() then return end      -- without the bar, Background.lua rings and glows
  PlaySound(SOUNDKIT.READY_CHECK, "Master")
  pulseToken = pulseToken + 1
  local token, steps = pulseToken, 0
  local function step()
    if token ~= pulseToken or state.running or not dirty then ui:SetAlpha(1); return end
    steps = steps + 1
    ui:SetAlpha(steps % 2 == 0 and 1 or 0.45)
    if steps < 10 then C_Timer.After(0.4, step) else ui:SetAlpha(1) end
  end
  step()
end

local function Begin(kind, total)
  state.running, state.kind, state.total = true, kind, total
  state.queue, state.current = {}, nil
  state.reading, state.readAway, state.readAt, state.readTotal = nil, nil, nil, nil
  state.done, state.skipped, state.deferrals, state.skipReasons = 0, 0, 0, {}
  state.pages, state.listings, state.withAuctions, state.noAuctions, state.assumed = 0, 0, 0, 0, 0
  state.snapAuctions, state.snapPriced = nil, nil   -- a snapshot's real figures, set when it has read the house
  state.token, state.attempt = state.token + 1, state.attempt + 1
  state.startedAt = GetTime()
  if state.ticker then state.ticker:Cancel() end
  state.ticker = C_Timer.NewTicker(1, function() UpdateStatus() end)
  ui.log:Clear()
  UpdateStatus()
end

local searchFrame = CreateFrame("Frame")   -- receives the per-item search events (registered while scanning)
local SEARCH_EVENTS = {
  "COMMODITY_SEARCH_RESULTS_UPDATED", "COMMODITY_SEARCH_RESULTS_ADDED",
  "ITEM_SEARCH_RESULTS_UPDATED", "ITEM_SEARCH_RESULTS_ADDED",
  "AUCTION_HOUSE_THROTTLED_MESSAGE_DROPPED", "AUCTION_HOUSE_THROTTLED_MESSAGE_RESPONSE_RECEIVED",
  "AUCTION_HOUSE_THROTTLED_SYSTEM_READY", "AUCTION_HOUSE_CLOSED",
}

local function Finish(reason)
  state.running, state.current, state.reading = false, nil, nil
  state.token = state.token + 1
  if state.ticker then state.ticker:Cancel(); state.ticker = nil end
  state.lastDuration = state.startedAt and (GetTime() - state.startedAt) or nil
  FrameUtil.UnregisterFrameForEvents(searchFrame, SEARCH_EVENTS)
  local detail = ""
  if state.skipped > 0 then
    local parts = {}
    for why, n in pairs(state.skipReasons) do table.insert(parts, string.format("%d %s", n, why)) end
    table.sort(parts)
    detail = " Skips: " .. table.concat(parts, ", ") .. "."
  end
  if state.deferrals > 0 then detail = detail .. string.format(" %d deferral(s).", state.deferrals) end
  local what = string.format("%d items recorded, %d skipped.", state.done, state.skipped)
  if state.kind == "snapshot" and not reason and state.snapAuctions then
    -- a snapshot records every queued item, so that count is only the list's size: say what was seen
    what = string.format("%s auctions read, %s of %s route items priced.", FormatLargeNumber(state.snapAuctions),
      FormatLargeNumber(state.snapPriced or 0), FormatLargeNumber(state.done))
  end
  Print(string.format("%s %s in %s: %s%s %s",
    state.kind or "scan", reason or "finished", FormatClock(state.lastDuration or 0), what, detail,
    BarHidden() and "Click the ForeverWowCraft button at the auction house (or /reload) to save and send them."
                 or "Click SAVE (or /reload) to write to disk."))
  UpdateStatus()
  if reason == nil and dirty then PulseBar() end
end

-- ================================================================ per-item scan
local NextItem, AttemptSearch

local function Attempt()
  state.attempt = state.attempt + 1
  AttemptSearch(state.attempt)
end

local function Skip(why)
  why = why or "unknown"
  state.skipped = state.skipped + 1
  state.skipReasons[why] = (state.skipReasons[why] or 0) + 1
  if state.current then
    Record(state.current, {}, false, why)
    Log(string.format("|cffff6060skipped|r %s (%s)", ItemName(state.current.itemID, state.current.name), why))
  end
  NextItem()
end

local function ArmTimeout()
  state.token = state.token + 1
  local token = state.token
  C_Timer.After(ITEM_TIMEOUT, function()
    if state.running and state.token == token and state.current then Skip("timeout") end
  end)
end

local function Done(entry, rows)
  Record(entry, rows, true)
  state.done = state.done + 1
  NextItem()
end

NextItem = function()
  state.token = state.token + 1
  local finished = state.done + state.skipped
  if finished > 0 and finished % TELEMETRY_EVERY == 0 then LogProgress() end
  state.current = table.remove(state.queue, 1)
  if not state.current then Finish(); return end
  state.ticks, state.retries = 0, 0
  UpdateStatus()
  Attempt()
end

-- Every chain (polling timer, READY event, retry) carries the attempt token it started with and
-- stops if the token has moved on, so an item is never queried twice at once.
AttemptSearch = function(token)
  local entry = state.current
  if not entry or not state.running or token ~= state.attempt then return end
  local keyInfo = C_AuctionHouse.GetItemKeyInfo(entry.itemKey)
  if not keyInfo or not C_AuctionHouse.IsThrottledMessageSystemReady() then
    state.ticks = state.ticks + 1
    if state.ticks > MAX_WAIT_TICKS then
      -- slow server: send the item to the back of the queue rather than losing it
      local why = keyInfo and "throttled" or "no item info"
      entry.deferred = (entry.deferred or 0) + 1
      if entry.deferred > MAX_DEFERRALS then
        Skip(why)
      else
        state.deferrals = state.deferrals + 1
        table.insert(state.queue, entry)
        Log(string.format("|cffffd060deferred|r %s (%s), will retry later", ItemName(entry.itemID, entry.name), why))
        NextItem()
      end
      return
    end
    state.waitingThrottle = true   -- the READY event restarts the chain; the timer is the fallback
    C_Timer.After(0.25, function() AttemptSearch(token) end)
    return
  end
  state.waitingThrottle = false
  entry.isCommodity = keyInfo.isCommodity
  entry.attempts = (entry.attempts or 0) + 1
  ArmTimeout()
  C_AuctionHouse.SendSearchQuery(entry.itemKey, SORTS, false)
end

local function RetryOrSkip(why)
  state.retries = state.retries + 1
  if state.retries > MAX_RETRIES then Skip(why); return end
  state.ticks = 0
  state.attempt = state.attempt + 1
  local token = state.attempt
  C_Timer.After(0.5, function() AttemptSearch(token) end)
end

local function RequestMore(fn, arg)
  if C_AuctionHouse.IsThrottledMessageSystemReady() then
    state.pages = state.pages + 1
    fn(arg)
  else
    C_Timer.After(0.3, function() RequestMore(fn, arg) end)
  end
end

-- The time an auction has left, as the band the auction house shows (1 short .. 4 very long).
-- A commodity result says it in seconds, and only for the character's own auctions (the
-- others are nil: a per-item SCAN of a commodity records no time left; a FULL snapshot does);
-- an item result as Enum.AuctionHouseTimeLeftBand (0 short .. 3 very long); a snapshot row
-- as the band itself.
local function BandOfSeconds(seconds)
  if not seconds then return nil end
  return seconds < 1800 and 1 or seconds < 7200 and 2 or seconds < 43200 and 3 or 4
end

local function BandOfEnum(band)
  return band and band + 1 or nil
end

local function CollectRows(entry)
  local rows = {}
  if entry.isCommodity then
    for i = 1, C_AuctionHouse.GetNumCommoditySearchResults(entry.itemID) do
      local info = C_AuctionHouse.GetCommoditySearchResultInfo(entry.itemID, i)
      if info and info.unitPrice and info.unitPrice > 0 then
        table.insert(rows, { info.unitPrice, info.quantity or 0, BandOfSeconds(info.timeLeftSeconds) })
      end
    end
  else
    for i = 1, C_AuctionHouse.GetNumItemSearchResults(entry.itemKey) do
      local info = C_AuctionHouse.GetItemSearchResultInfo(entry.itemKey, i)
      if info and info.buyoutAmount and info.buyoutAmount > 0 then
        local q = info.quantity or 1
        -- under a copper a unit: a copper
        table.insert(rows, { math.max(1, math.floor(info.buyoutAmount / q)), q, BandOfSeconds(info.timeLeftSeconds) or BandOfEnum(info.timeLeft) })
      end
    end
  end
  table.sort(rows, function(a, b) return a[1] < b[1] end)
  return rows
end

searchFrame:SetScript("OnEvent", function(_, event, arg1)
  if not state.running then return end
  local cur = state.current
  if event == "AUCTION_HOUSE_CLOSED" then
    -- (this frame hears events during a per-item scan only; a snapshot's closing is
    -- SnapshotHouseClosed, from the loader)
    Finish("aborted (auction house closed)")
  elseif event == "AUCTION_HOUSE_THROTTLED_MESSAGE_DROPPED" then
    if cur then RetryOrSkip("message dropped") end
  elseif event == "AUCTION_HOUSE_THROTTLED_SYSTEM_READY" then
    if cur and state.waitingThrottle then state.waitingThrottle = false; Attempt() end
  elseif event == "AUCTION_HOUSE_THROTTLED_MESSAGE_RESPONSE_RECEIVED" then
    -- gear with no auctions gets no result event at all: after a grace period, call it empty
    if cur and cur.attempts and not cur.isCommodity then
      local token = state.token
      C_Timer.After(UNANSWERED_GRACE, function()
        if state.running and state.current == cur and state.token == token
            and C_AuctionHouse.GetNumItemSearchResults(cur.itemKey) == 0 then
          cur.assumedEmpty = true
          Done(cur, {})
        end
      end)
    end
  elseif cur and (event == "COMMODITY_SEARCH_RESULTS_UPDATED" or event == "COMMODITY_SEARCH_RESULTS_ADDED") then
    if arg1 ~= cur.itemID then return end
    if not C_AuctionHouse.HasFullCommoditySearchResults(arg1) then
      ArmTimeout(); RequestMore(C_AuctionHouse.RequestMoreCommoditySearchResults, arg1); return
    end
    Done(cur, CollectRows(cur))
  elseif cur and (event == "ITEM_SEARCH_RESULTS_UPDATED" or event == "ITEM_SEARCH_RESULTS_ADDED") then
    if type(arg1) ~= "table" or arg1.itemID ~= cur.itemID then return end
    if not C_AuctionHouse.HasFullItemSearchResults(arg1) then
      ArmTimeout(); RequestMore(C_AuctionHouse.RequestMoreItemSearchResults, arg1); return
    end
    Done(cur, CollectRows(cur))
  end
end)

StartScan = function(listName)
  local names = QueueNames()
  if (listName == nil or listName == "") and #names == 1 then listName = names[1] end
  local rows = FWCS_QUEUE and listName and FWCS_QUEUE[listName]
  if not rows and listName then   -- case-insensitive prefix match
    for _, name in ipairs(names) do
      if name:lower():find(listName:lower(), 1, true) == 1 then rows, listName = FWCS_QUEUE[name], name end
    end
  end
  if not rows then
    Print("which list? /fwcs scan <name>. Available: " .. (#names > 0 and table.concat(names, " | ") or "none: start the ForeverWowCraft Helper on this PC, which fetches them, then /reload"))
    return
  end
  if not (AuctionHouseFrame and AuctionHouseFrame:IsShown()) then Print("open the auction house first"); return end
  if SharedHouse() then Print(SHARED_NOT_SCANNED); return end
  if state.running then Print("a scan is already running; /fwcs stop first"); return end
  Begin("scan", 0)
  for _, row in ipairs(rows) do
    if type(row[1]) == "number" then
      C_Item.RequestLoadItemDataByID(row[1])   -- warm the cache so GetItemKeyInfo answers quickly
      table.insert(state.queue, { itemID = row[1], name = row[2], itemKey = C_AuctionHouse.MakeItemKey(row[1]) })
    end
  end
  table.sort(state.queue, function(a, b) return a.itemID < b.itemID end)
  state.total = #state.queue
  FrameUtil.RegisterFrameForEvents(searchFrame, SEARCH_EVENTS)
  Print(string.format("scan '%s' started: %d items ...", listName, state.total))
  NextItem()
end

-- ================================================================ cooldown alert
-- Rings when the full snapshot comes off its cooldown, wherever the character is. lastFull is
-- account-wide and wall-clock time, so the alert survives /reload and a change of character; it
-- is armed again at every login. Nothing can ring while no character is in the world, so a
-- character that logs in with the snapshot ready hears it then (RingAtLogin): the cooldown
-- ended while nobody was there to be told.
-- in the background (no bar) the scan starts by itself at the auction house, so this sound is
-- off unless asked for: the one sound there is the Save button's
local function ReadyAlertEnabled()
  local s = Settings()
  if s.ding ~= nil then return s.ding end
  return not BarHidden()
end

local function RingReady(again)
  PlaySound(SOUNDKIT.ALARM_CLOCK_WARNING_3 or SOUNDKIT.RAID_WARNING or SOUNDKIT.READY_CHECK, "Master")
  Print("the full AH snapshot is ready" .. (again and " again" or "") .. ": open the auction house"
    .. (AutoScanEnabled() and "." or " and click FULL."))
  UIErrorsFrame:AddMessage("ForeverWowCraft: FULL snapshot ready", 0.2, 0.8, 1)
  UpdateStatus()
end

local readyToken = 0
local function ArmReadyAlert()
  readyToken = readyToken + 1
  local token, left = readyToken, FullCooldownLeft()
  if left <= 0 or not ReadyAlertEnabled() then return end
  C_Timer.After(left, function()
    if token ~= readyToken or not ReadyAlertEnabled() then return end
    if FullCooldownLeft() > 0 then ArmReadyAlert(); return end
    RingReady(true)
  end)
end

-- At a login (a character entering the world from the character list: not a /reload, which a
-- SAVE is, and not a change of zone), a little after the loading screen so that it is heard.
local function RingAtLogin()
  if not ReadyAlertEnabled() or #QueueNames() == 0 or FullCooldownLeft() > 0 then return end
  C_Timer.After(LOGIN_RING_DELAY, function()
    if ReadyAlertEnabled() and FullCooldownLeft() <= 0 and not state.running then RingReady(false) end
  end)
end

-- ================================================================ full snapshot
-- GetReplicateItemInfo(i) (0-based) returns positional fields: the 3rd is the count, the 10th the
-- buyout, the 17th the item. These three are present even when the item's data is not cached,
-- which is all a ladder needs. The time left comes from a call of its own, as the band (1 short
-- .. 4 very long) the old auction house API used.

local function ReplicateTimeLeft(i)
  if not C_AuctionHouse.GetReplicateItemTimeLeft then return nil end
  local band = C_AuctionHouse.GetReplicateItemTimeLeft(i)
  return (band and band >= 1 and band <= 4) and band or nil
end
local snapshotFrame = CreateFrame("Frame")

StartSnapshot = function(force)
  if not (AuctionHouseFrame and AuctionHouseFrame:IsShown()) then Print("open the auction house first"); return end
  if SharedHouse() then Print(SHARED_NOT_SCANNED); return end
  if state.running then Print("a scan is already running; /fwcs stop first"); return end
  local wanted = QueuedItems()
  if next(wanted) == nil then Print("no queued lists: start the ForeverWowCraft Helper on this PC, which fetches them, then /reload"); return end
  local left = FullCooldownLeft()
  if left > 0 and not force then
    Print(string.format("full snapshot is on its 15-minute cooldown for another %s", FormatClock(left)))
    return
  end
  Begin("snapshot", CountKeys(wanted))
  state.askedAt = time()                     -- the server's cooldown is taken to run from here
  local token = state.token
  Print(string.format("full AH snapshot requested (%d queued items to price) ...", state.total))
  Log("waiting for the server's auction list ...")

  snapshotFrame:RegisterEvent("REPLICATE_ITEM_LIST_UPDATE")
  snapshotFrame:SetScript("OnEvent", function(self)
    self:UnregisterEvent("REPLICATE_ITEM_LIST_UPDATE")
    if not state.running or state.token ~= token then return end
    local n = C_AuctionHouse.GetNumReplicateItems()
    Log(string.format("server returned %s auctions; reading ...", FormatLargeNumber(n)))
    state.reading, state.readTotal, state.readAt = true, n, 0
    local ladders, seen, distinct, auctions, i = {}, {}, 0, 0, 0
    local bands = { 0, 0, 0, 0, unsaid = 0 }
    local function batch()
      if not state.running or state.token ~= token then return end
      if state.readAway then
        -- the window closed meanwhile: the list must still be there to read on
        local ok, left = pcall(C_AuctionHouse.GetNumReplicateItems)
        if not ok or (left or 0) < n then
          Print("the auction list went with the window: the snapshot is lost. The house must stay open while a snapshot is read.")
          Finish("aborted (the auction list went with the window)")
          return
        end
      end
      local stop = math.min(n, i + 500)
      while i < stop do
        -- the fields by position, with no table made for each auction: a house has over 100,000 of them
        local _, _, count, _, _, _, _, _, _, buyout, _, _, _, _, _, _, itemID = C_AuctionHouse.GetReplicateItemInfo(i)
        if itemID and count and count > 0 and buyout and buyout > 0 then
          auctions = auctions + 1                    -- every auction and item counts in the figures; only a listed item gets a ladder
          if not seen[itemID] then seen[itemID] = true; distinct = distinct + 1 end
          if wanted[itemID] then
            local band = ReplicateTimeLeft(i)
            if band then bands[band] = bands[band] + 1 else bands.unsaid = bands.unsaid + 1 end
            ladders[itemID] = ladders[itemID] or {}
            table.insert(ladders[itemID], { math.max(1, math.floor(buyout / count)), count, band })   -- under a copper a unit: a copper
          end
        end
        i = i + 1
      end
      state.readAt = i
      ui.cols.item:SetFormattedText("reading auction %s / %s", FormatLargeNumber(i), FormatLargeNumber(n))
      if i < n then C_Timer.After(0, batch); return end
      -- every queued item gets a record: its rows, or an empty complete ladder
      local priced, none = 0, 0
      for itemID, name in pairs(wanted) do
        local rows = ladders[itemID] or {}
        table.sort(rows, function(a, b) return a[1] < b[1] end)
        Record({ itemID = itemID, name = name, full = true }, rows, true)
        state.done = state.done + 1
        if #rows > 0 then priced = priced + 1 else none = none + 1 end
      end
      state.snapAuctions, state.snapPriced = auctions, priced
      Log(string.format("snapshot: %s auctions, %s distinct items on the AH; %d queued items priced, %d with no auctions",
        FormatLargeNumber(auctions), FormatLargeNumber(distinct), priced, none))
      Log(string.format("time left of the queued items' auctions: %s short, %s medium, %s long, %s very long, %s unsaid",
        FormatLargeNumber(bands[1]), FormatLargeNumber(bands[2]), FormatLargeNumber(bands[3]), FormatLargeNumber(bands[4]),
        FormatLargeNumber(bands.unsaid)))
      NoteFullArrived()
      ArmReadyAlert()
      if state.readAway then Print("the snapshot was read after the auction house closed: that works. Open the house (or /reload) to save it.") end
      Finish()
    end
    batch()
  end)
  C_AuctionHouse.ReplicateItems()
  -- The server answers a big auction house slowly (well over 20 s has been seen), and not at all
  -- while the snapshot is on its cooldown; nothing tells the two apart but waiting.
  C_Timer.After(FULL_PATIENCE, function()
    if state.running and state.token == token and state.done == 0 then
      Log(string.format("nothing yet after %d s: a big auction house takes a while; on cooldown nothing comes. Giving up at %d s (/fwcs stop gives up now).",
        FULL_PATIENCE, FULL_TIMEOUT))
    end
  end)
  C_Timer.After(FULL_TIMEOUT, function()
    if state.running and state.token == token and state.done == 0 then
      snapshotFrame:UnregisterEvent("REPLICATE_ITEM_LIST_UPDATE")
      Settings().lastFullRefused = time()
      ArmReadyAlert()
      if state.readAway then
        -- the house was closed before the list came (seen 12 Oct 2026: nothing came in 120 s). A
        -- closed house most likely gets no answer; a cooldown this client did not see start
        -- looks the same. Either way the button rests, since the server may have started one.
        Print(string.format("no auction list arrived in %d s, and the auction house was closed while it was awaited: a closed "
          .. "house gets no answer, as far as is known. Next time keep the house open until \"snapshot finished\". FULL stays "
          .. "off for up to 15 minutes in case the server started its cooldown.", FULL_TIMEOUT))
      else
        Print(string.format("no auction list arrived in %d s: the snapshot is on its 15-minute cooldown, started by something this "
          .. "client did not see (another PC, or before the addon was installed). FULL stays off for up to 15 minutes; "
          .. "Use a per-list SCAN meanwhile.", FULL_TIMEOUT))
      end
      Finish("failed (no data)")
    end
  end)
end

-- The auction house closed during a snapshot (12 Oct 2026). The addon never stopped one for
-- that; what the client does is the question, and the reading now finds out instead of
-- recording a cleared list as "nothing listed": the list answered is in the client already,
-- so the reading goes on, and stops with a word if the list went with the window (batch
-- looks); one not yet answered is read if the server still answers, and the timeout says
-- otherwise. Either way the chat tells which, and the snapshot is saved on the next visit.
-- a snapshot let go: the state as after Finish, and one line (not Finish's word about saving:
-- nothing was recorded)
local function Drop(reason)
  state.running, state.current, state.reading = false, nil, nil
  state.token = state.token + 1
  if state.ticker then state.ticker:Cancel(); state.ticker = nil end
  snapshotFrame:UnregisterEvent("REPLICATE_ITEM_LIST_UPDATE")
  Print(reason)
  UpdateStatus()
end

-- (said in the bar's log, not in chat: a player who closes the house while the snapshot is
-- awaited has nothing to do about it, and the words in chat were noise; the user, 8 Nov 2026)
local function SnapshotHouseClosed()
  state.readAway = true
  if state.reading then
    Log(string.format("the auction house closed while the snapshot is read (%s of %s auctions): reading on",
      FormatLargeNumber(state.readAt or 0), FormatLargeNumber(state.readTotal or 0)))
  else
    Log("the auction house closed while the snapshot is awaited: it is read if the server still answers; if nothing comes, FULL waits the cooldown")
  end
end

-- ================================================================ events + slash commands
local loader = CreateFrame("Frame")
loader:RegisterEvent("PLAYER_LOGIN")
loader:RegisterEvent("PLAYER_ENTERING_WORLD")
loader:RegisterEvent("AUCTION_HOUSE_SHOW")
loader:RegisterEvent("AUCTION_HOUSE_CLOSED")
loader:RegisterEvent("REPLICATE_ITEM_LIST_UPDATE")
loader:SetScript("OnEvent", function(_, event, isInitialLogin)
  if event == "PLAYER_ENTERING_WORLD" then
    if isInitialLogin and not FWCS_PLANS_WRITTEN then      -- an install without a helper (CurseForge): the helper stamps FWCS_PLANS_WRITTEN when it writes
      Print("the helper is not on this PC: /fwc says what it does and where to get it. What the addon records stays here until then.")
    end
    if isInitialLogin and C_AuctionHouse and C_AuctionHouse.SendSearchQuery then RingAtLogin() end
    return
  end
  if event == "REPLICATE_ITEM_LIST_UPDATE" then      -- an auction list arrived: ours, or another addon's snapshot
    if C_AuctionHouse.GetNumReplicateItems() > 0 then
      NoteFullArrived()
      ArmReadyAlert()
      UpdateStatus()
    end
    return
  end
  if event == "AUCTION_HOUSE_SHOW" or event == "AUCTION_HOUSE_CLOSED" then
    state.ahOpen = event == "AUCTION_HOUSE_SHOW"
    state.offered = nil                                   -- the gate: decided once a visit
    if not state.ahOpen and state.running and state.kind == "snapshot" then SnapshotHouseClosed() end
    if state.ahOpen and state.running and state.kind == "snapshot" and state.readAway and not state.reading and state.done == 0 then
      -- the snapshot awaited went with the window: a closed house gets no answer (12 Oct 2026),
      -- and waiting the 120 s out kept the button at "Scanning..." on the reopened house (6 Nov
      -- 2026). Let go at once, and the server's cooldown taken to run from the ask: whether it
      -- does is not known (the user, 6 Nov 2026: the first ask most likely starts it), and a
      -- /fwcs full force tries sooner, for a test (the shift-click that did went in 1.6.23)
      Settings().lastFullRefused = state.askedAt or time()
      ArmReadyAlert()
      Drop(string.format("the snapshot awaited was lost with the window: a closed house gets no answer, and the cooldown runs from the ask. "
        .. "Prices in %s at the latest.", FormatClock(FullCooldownLeft())))
    end
    if state.ahOpen then
      local was = Faction()
      openHouse = HouseHere()
      if SharedHouse() then
        if Faction() ~= was then Print(SHARED_NOT_SCANNED) end
      elseif Faction() ~= was then
        Print("this is the auction house of " .. DatasetName() .. "; scans are kept as that.")
      end
      -- by itself: the full snapshot when it can be taken and there is nothing waiting to be
      -- saved; after the shopping list's buying when it has some (Shop.lua: the buying first,
      -- so that a player is not held at the list while the house answers the scan), up to
      -- AUTO_WAIT seconds of it
      if AutoScanEnabled() and not SharedHouse() and not state.running and not dirty and FullCooldownLeft() <= 0 and next(QueuedItems()) and Offered() then
        local since = GetTime()
        local function soon()
          if not (state.ahOpen and not state.running and not dirty and FullCooldownLeft() <= 0) then return end
          if not (AuctionHouseFrame and AuctionHouseFrame:IsShown()) then return end
          if ns.ShoppingBusy and ns.ShoppingBusy() and GetTime() - since < AUTO_WAIT then C_Timer.After(2, soon); return end
          StartSnapshot(false)
        end
        C_Timer.After(1, soon)
      end
    end
    UpdateStatus()
    return
  end
  ns.DropRecipesWithoutLevel()                           -- PLAYER_LOGIN: the saved file is in
  TrimAllHistory()
  if not (C_AuctionHouse and C_AuctionHouse.SendSearchQuery) then
    Print("this client does not use the modern auction house API; scanner disabled")
    return
  end
  RestorePosition()
  NoteRealmNames()
  AdoptOldKeys()
  ArmReadyAlert()
  local n = #QueueNames()
  if n == 0 then
    Print("loaded, but no queued lists: start the ForeverWowCraft Helper on this PC, which fetches them, then /reload.")
  elseif BarHidden() then
    Print(string.format("loaded. Prices are recorded at the auction house%s; /fwc shows what your professions need. /fwcs for commands.",
      AutoScanEnabled() and " by itself" or " (/fwcs full)"))
  else
    Print(string.format("loaded with %d queued list(s). Open the auction house and click FULL. /fwcs for commands.", n))
  end
  if n > 0 and FullCooldownLeft() > 0 and not BarHidden() then
    Print(string.format("the full snapshot is ready in %s%s%s.", FormatClock(FullCooldownLeft()),
      FullCooldownKnown() and "" or " at the latest",
      ReadyAlertEnabled() and "; a sound will tell you" or " (/fwcs ding turns the sound on)"))
  end
end)

-- what Window.lua and Background.lua use of this file
ns.Print, ns.Settings, ns.RealmKey, ns.QueuedItems = Print, Settings, RealmKey, QueuedItems
ns.Debug = function(line) if state.debug then Print(line); return true end end       -- a line in chat while /fwcs debug is on; true when it was printed
ns.scanner = {
  Dirty = function() return dirty end,
  Running = function() return state.running end,
  Snapshot = function() return state.running and state.kind == "snapshot" end,
  Open = function() return state.ahOpen end,
  CooldownLeft = FullCooldownLeft, CooldownKnown = FullCooldownKnown, Clock = FormatClock,
  HasLists = function() return #QueueNames() > 0 end,
  StartSnapshot = function(force) StartSnapshot(force == true) end,       -- force: past the cooldown (/fwcs full force, a test's)
  Reload = DoReload,
  ResetBar = function() Settings().pos = nil; RestorePosition() end,
  BarHidden = BarHidden, AutoScanEnabled = AutoScanEnabled, AlertEnabled = AlertEnabled, ReadyAlertEnabled = ReadyAlertEnabled,
  Refresh = function() UpdateStatus() end, ArmReadyAlert = ArmReadyAlert,
}

-- /fwcs house neutral | alliance | horde | auto: the auction house the prices are kept as, when
-- not the one where the character stands (the options page has the same four)
local function HouseCommand(arg)
  local named = { neutral = "Neutral", alliance = "Alliance", horde = "Horde" }
  local function Where()
    return SharedHouse() and "the auction house both factions share, which is not scanned" or DatasetName()
  end
  if named[arg] then
    Settings().house = named[arg]
    Print((SharedHouse() and "the open house is taken for " or "scans are kept as ") .. Where()
          .. " from now on, wherever you are. /fwcs house auto undoes that.")
  elseif arg == "auto" then
    Settings().house = nil
    Print("the auction house is told from where you stand again: now " .. Where())
  else
    Print((SharedHouse() and "the open house is taken for " or "scans are kept as ") .. Where()
          .. (Settings().house and " (you said so)" or "") .. ". /fwcs house neutral | alliance | horde | auto")
  end
  UpdateStatus()
end
ns.HouseCommand = HouseCommand

SLASH_FOREVERWOWCRAFTSCANNER1 = "/fwcs"
SLASH_FOREVERWOWCRAFTSCANNER2 = "/fcs"    -- what it was before the addon was renamed
SlashCmdList.FOREVERWOWCRAFTSCANNER = function(msg)
  msg = (msg or ""):lower():gsub("^%s+", ""):gsub("%s+$", "")
  local cmd, arg = msg:match("^(%S*)%s*(.-)$")
  if cmd == "full" then
    StartSnapshot(arg == "force")
  elseif cmd == "scan" then
    StartScan(arg)
  elseif cmd == "lists" then
    local names = QueueNames()
    Print(#names > 0 and ("queued lists: " .. table.concat(names, " | ")) or "no queued lists: start the ForeverWowCraft Helper on this PC, which fetches them, then /reload")
  elseif cmd == "stop" then
    if state.running then Finish("stopped") else Print("not running") end
  elseif cmd == "save" then
    DoReload()
    Print("if nothing happens, /reload does it: the game lets no addon reload for you on this client")
  elseif cmd == "clear" then
    FWCS_DB[DatasetKey()] = {}
    Print("cleared the scan data of " .. DatasetName() .. " (takes effect on /reload)")
  elseif cmd == "house" then
    HouseCommand(arg)
  elseif cmd == "bar" then
    Settings().hidden = not BarHidden()
    Print(BarHidden() and "the scanner's bar is hidden: it scans in the background, with a button at the auction house"
                       or "the scanner's bar is shown (FULL / SCAN / SAVE)")
    UpdateStatus()
  elseif cmd == "offer" then
    local h = FreshOf()
    if state.ahOpen then
      state.offered = true
      UpdateStatus()
      Print("the FULL / SCAN box is offered this visit")
    elseif h and h.newest then
      local left = FreshFor()
      Print(string.format("%s was last scanned by anyone %d min ago: %s. At the auction house, /fwcs offer shows the box regardless.",
        DatasetName(), math.floor(math.max(0, time() - tonumber(h.newest)) / 60),
        left > 0 and ("fresh for " .. math.ceil(left / 60) .. " min more, so no box until then") or "a scan is wanted, the box shows"))
    else
      Print(DatasetName() .. ": the pipe has not said when it was scanned (the helper writes that); the box shows every time")
    end
  elseif cmd == "auto" then
    Settings().auto = not AutoScanEnabled()
    Print(AutoScanEnabled() and "the full snapshot is taken by itself when the auction house opens and it can be"
                             or "the full snapshot is taken only when asked (FULL, or /fwcs full)")
  elseif cmd == "reset" then
    Settings().pos = nil
    RestorePosition()
    Print("status bar position reset")
  elseif cmd == "alert" then
    Settings().alert = not AlertEnabled()
    Print(AlertEnabled() and "finish alert ON: a sound when prices are ready to save" or "finish alert OFF: no sound when prices are ready to save")
  elseif cmd == "ding" then
    Settings().ding = not ReadyAlertEnabled()
    ArmReadyAlert()
    local left = FullCooldownLeft()
    Print(ReadyAlertEnabled() and ("cooldown alert ON: a sound when the full snapshot is ready again"
            .. (left > 0 and (", in " .. FormatClock(left)) or "")) or "cooldown alert OFF")
  elseif cmd == "log" then
    Settings().log = not (Settings().log == true)
    Print("telemetry panel " .. (Settings().log == true and "shown" or "hidden"))
    UpdateStatus()
  elseif cmd == "plan" or cmd == "plans" then
    ns.ToggleWindow()
  elseif cmd == "options" or cmd == "config" then
    ns.OpenOptions()
  elseif cmd == "arrow" then
    ns.ArrowCommand(arg)
  elseif cmd == "remind" or cmd == "reload" then
    ns.RemindCommand(arg)
  elseif cmd == "places" then
    ns.PlacesCommand()
  elseif cmd == "shop" then
    ns.ShopCommand(arg)
  elseif cmd == "have" then
    ns.HaveCommand(arg)
  elseif cmd == "fishing" or cmd == "fish" then
    ns.FishingCommand(arg)
  elseif cmd == "needs" then
    ns.NeedsCommand(arg)
  elseif cmd == "debug" then
    state.debug = not state.debug
    Print("telemetry echo to chat " .. (state.debug and "on" or "off")
      .. ((ns.scrollFailures or 0) > 0 and string.format("; %d recipe scroll tooltip(s) could not be read this session", ns.scrollFailures) or ""))
  else
    local n = 0
    for k in pairs(RealmDB()) do if type(k) == "number" then n = n + 1 end end
    if state.running then
      Print(string.format("%s running: %d/%d done", state.kind, state.done + state.skipped, state.total))
    else
      Print(string.format("idle. %d items stored for %s%s. Commands: /fwcs full [force] | scan [list] | lists | stop | save | clear | house | bar | auto | offer | plan | options | reset | alert | ding | remind | log | arrow | places | shop | have | fishing | needs | debug. /fwc: what your professions still need",
        n, DatasetName(), dirty and " (unsaved: click SAVE, /fwcs save or /reload)" or ""))
    end
  end
end

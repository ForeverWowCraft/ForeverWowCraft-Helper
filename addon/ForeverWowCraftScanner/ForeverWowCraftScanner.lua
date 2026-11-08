-- ForeverWowCraft Scanner (the addon folder and its saved-variables file are ForeverWowCraftScanner)
--
-- Records auction-house price ladders for the items on its lists.
-- The helper (`python fwch.py lists`) writes Queue.lua next to this file:
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
--   FWCS_DB[key].__history[itemID] = { {time, lowestPrice, unitsListed}, ... }  -- one per scan
--   FWCS_DB.__ui = { pos, hidden, auto, alert, ding, log, lastFull, lastFullRefused, house } -- settings
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
local HISTORY_MAX = 200         -- price-history points kept per item (one per scan that covered it)
local SCAN_SIZE = { 900, 72 }   -- progress bar
local SAVE_SIZE = { 340, 300 }  -- FULL / SCAN / SAVE box
local LOG_LINES, LOG_LINE_HEIGHT = 8, 17

-- ================================================================ saved data helpers
local function Settings()
  FWCS_DB.__ui = FWCS_DB.__ui or {}
  return FWCS_DB.__ui
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
-- stays off until 15 minutes after it at the latest. Shift-click tries sooner.
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
    ui.text:SetFormattedText("%d recorded, %d skipped%s\nclick to write to disk", state.done, state.skipped,
      state.lastDuration and ("  in " .. FormatClock(state.lastDuration)) or "")
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
        if not ui.disabled or IsShiftKeyDown() then StartSnapshot(IsShiftKeyDown()) end
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

-- The character level a recipe scroll asks for, as this client shows it (a hotfix the public
-- tables lack: Recipe: Elixir of Intellect asks for 45, 8 Nov 2026), kept in FWCS_DB.__recipes
-- for the helper to send with the vendors met; nothing of the player in it. Looked at for
-- every recipe item the scan meets, and for the recipe a route buys (Verdict.lua). Returns
-- the level when the client has the item's data, else nil.
function ns.NoteRecipeLevel(itemID)
  if type(itemID) ~= "number" then return nil end
  local instant = C_Item and C_Item.GetItemInfoInstant or GetItemInfoInstant
  if not instant then return nil end
  local ok, _, _, _, _, _, classID = pcall(instant, itemID)
  if not ok or classID ~= 9 then return nil end                -- 9: a recipe
  local info = C_Item and C_Item.GetItemInfo or GetItemInfo
  if not info then return nil end
  local ok2, _, _, _, _, minLevel = pcall(info, itemID)
  if not ok2 or type(minLevel) ~= "number" then return nil end
  local level = math.max(1, math.floor(minLevel))
  FWCS_DB.__recipes = FWCS_DB.__recipes or {}
  local row = FWCS_DB.__recipes[itemID]
  if not row or row.l ~= level then FWCS_DB.__recipes[itemID] = { l = level, t = time() } end
  return level
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
    while #h > HISTORY_MAX do table.remove(h, 1) end
    db.__history[entry.itemID] = h
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
  Print(string.format("%s %s in %s: %d items recorded, %d skipped.%s %s",
    state.kind or "scan", reason or "finished", FormatClock(state.lastDuration or 0), state.done, state.skipped, detail,
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
    Print("which list? /fwcs scan <name>. Available: " .. (#names > 0 and table.concat(names, " | ") or "none (run fwch.py lists, then /reload)"))
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
-- GetReplicateItemInfo(i) (0-based) returns positional fields; these three are present even when
-- the item's data is not cached, which is all a ladder needs. The time left comes from a call
-- of its own, as the band (1 short .. 4 very long) the old auction house API used.
local REPLICATE = { count = 3, buyout = 10, itemID = 17 }

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
  if next(wanted) == nil then Print("no queued lists (run fwch.py lists, then /reload)"); return end
  local left = FullCooldownLeft()
  if left > 0 and not force then
    Print(string.format("full snapshot is on its 15-minute cooldown for another %s (shift-click FULL or '/fwcs full force' to try anyway)", FormatClock(left)))
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
    local ladders, distinct, auctions, i = {}, 0, 0, 0
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
        local info = { C_AuctionHouse.GetReplicateItemInfo(i) }
        local itemID, count, buyout = info[REPLICATE.itemID], info[REPLICATE.count], info[REPLICATE.buyout]
        if itemID and count and count > 0 and buyout and buyout > 0 then
          if not ladders[itemID] then ladders[itemID] = {}; distinct = distinct + 1 end
          local band = ReplicateTimeLeft(i)
          if band then bands[band] = bands[band] + 1 else bands.unsaid = bands.unsaid + 1 end
          table.insert(ladders[itemID], { math.max(1, math.floor(buyout / count)), count, band })   -- under a copper a unit: a copper
          auctions = auctions + 1
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
      Log(string.format("snapshot: %s auctions, %s distinct items on the AH; %d queued items priced, %d with no auctions",
        FormatLargeNumber(auctions), FormatLargeNumber(distinct), priced, none))
      Log(string.format("time left: %s short, %s medium, %s long, %s very long, %s unsaid",
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
          .. "off for up to 15 minutes in case the server started its cooldown; shift-click it to try sooner.", FULL_TIMEOUT))
      else
        Print(string.format("no auction list arrived in %d s: the snapshot is on its 15-minute cooldown, started by something this "
          .. "client did not see (another PC, or before the addon was installed). FULL stays off for up to 15 minutes; "
          .. "shift-click it to try sooner. Use a per-list SCAN meanwhile.", FULL_TIMEOUT))
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

local function SnapshotHouseClosed()
  state.readAway = true
  if state.reading then
    Print(string.format("the auction house closed while the snapshot is read (%s of %s auctions): reading on",
      FormatLargeNumber(state.readAt or 0), FormatLargeNumber(state.readTotal or 0)))
  else
    Print("the auction house closed while the snapshot is awaited: it is read if the server still answers; if nothing comes, FULL waits the cooldown")
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
      -- shift-click on the button, or /fwcs full force, tries sooner for whoever wants to see
      Settings().lastFullRefused = state.askedAt or time()
      ArmReadyAlert()
      Drop(string.format("the snapshot awaited was lost with the window: a closed house gets no answer, and the cooldown runs from the ask. "
        .. "Prices in %s at the latest; shift-click the button to try sooner.", FormatClock(FullCooldownLeft())))
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
    Print("loaded, but no queued lists: run `python fwch.py lists`, then /reload.")
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
ns.scanner = {
  Dirty = function() return dirty end,
  Running = function() return state.running end,
  Snapshot = function() return state.running and state.kind == "snapshot" end,
  Open = function() return state.ahOpen end,
  CooldownLeft = FullCooldownLeft, CooldownKnown = FullCooldownKnown, Clock = FormatClock,
  HasLists = function() return #QueueNames() > 0 end,
  StartSnapshot = function(force) StartSnapshot(force == true) end,       -- force: a shift-click, past the cooldown
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
    Print(#names > 0 and ("queued lists: " .. table.concat(names, " | ")) or "no queued lists (run fwch.py lists, then /reload)")
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
    Print(AlertEnabled() and "finish alert ON: sound + pulsing bar" or "finish alert OFF")
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
  elseif cmd == "needs" then
    ns.NeedsCommand(arg)
  elseif cmd == "debug" then
    state.debug = not state.debug
    Print("telemetry echo to chat " .. (state.debug and "on" or "off"))
  else
    local n = 0
    for k in pairs(RealmDB()) do if type(k) == "number" then n = n + 1 end end
    if state.running then
      Print(string.format("%s running: %d/%d done", state.kind, state.done + state.skipped, state.total))
    else
      Print(string.format("idle. %d items stored for %s%s. Commands: /fwcs full [force] | scan [list] | lists | stop | save | clear | house | bar | auto | options | reset | alert | ding | log | arrow | places | shop | needs | debug. /fwc: what your professions still need",
        n, DatasetName(), dirty and " (unsaved: click SAVE, /fwcs save or /reload)" or ""))
    end
  end
end

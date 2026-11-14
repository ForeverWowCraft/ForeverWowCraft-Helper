-- The scanner in the background: a small button on the auction house frame, and the options
-- page (Interface, AddOns, ForeverWowCraft).
--
-- The button says where the scanner is. On its cooldown: dim, with the time left. Ready:
-- "Scan Prices" (and the scan starts by itself when the house opens, unless that is turned
-- off). Scanning: "Scanning...". Done: a lit "Save Prices", pulsing a few times, with a short
-- sound once. A click on it saves (/reload), after which the helper sends what was recorded.
-- That click is the only thing asked of a player.

local _, ns = ...

local WIDTH, HEIGHT = 118, 22
local PULSES = 6                          -- times the lit button dims and brightens
local button, told, ticker

local function Scanner() return ns.scanner end

local function Tip(self)
  local sc = Scanner()
  GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
  GameTooltip:AddLine("ForeverWowCraft")
  if sc.Dirty() then
    GameTooltip:AddLine("Prices were recorded. Click to save them (the interface reloads); the helper then sends them "
      .. "to foreverwowcraft.com, where the routes come from.", 1, 1, 1, true)
  elseif sc.Running() then
    GameTooltip:AddLine("Recording the auction house's prices. Keep the auction house open; it takes a moment.", 1, 1, 1, true)
  elseif sc.CooldownLeft() > 0 then
    GameTooltip:AddLine(string.format("The auction house can be read once every 15 minutes%s. Next in %s%s.",
      sc.AutoScanEnabled() and ", by itself when it is open" or "", sc.Clock(sc.CooldownLeft()),
      sc.CooldownKnown() and "" or " at the latest"), 1, 1, 1, true)
  else
    GameTooltip:AddLine("Click to record the auction house's prices. Only AH pricing information is sent to "
      .. "foreverwowcraft.com. Thanks for helping the community by running and saving a scan!", 1, 1, 1, true)
  end
  GameTooltip:AddLine("Interface > AddOns > ForeverWowCraft has the switches.", 0.6, 0.6, 0.6, true)
  GameTooltip:Show()
end

local function Pulse()
  local n = 0
  local function step()
    if not button or not Scanner().Dirty() then if button then button:SetAlpha(1) end return end
    n = n + 1
    button:SetAlpha(n % 2 == 1 and 0.5 or 1)
    if n < PULSES * 2 then C_Timer.After(0.35, step) else button:SetAlpha(1) end
  end
  step()
end

local Button

-- The auction house's frame is built by the game when the house first opens, on the same
-- event this file sees, and may not be there yet when it does: so the button is made at
-- whichever draw first finds the frame.
local function Draw()
  if not button and not Button() then return end
  local sc = Scanner()
  button:SetAlpha(1)
  if sc.Dirty() then
    button:Enable()
    button:SetText("|cff40ff40Save Prices|r")
    if not told then
      told = true
      if sc.AlertEnabled() then PlaySound(SOUNDKIT.READY_CHECK, "Master") end
      Pulse()
    end
    return
  end
  told = false
  if sc.Running() then
    button:Disable()
    button:SetText("Scanning...")
  elseif not sc.HasLists() then
    button:Disable()
    button:SetText("No lists yet")
  elseif sc.CooldownLeft() > 0 then
    button:Enable()                                                  -- for the tooltip
    button:SetText(string.format("|cff808080Prices in %s|r", sc.Clock(sc.CooldownLeft())))
  else
    button:Enable()
    button:SetText("Scan Prices")
  end
end

Button = function()
  if button or not AuctionHouseFrame then return button end
  button = CreateFrame("Button", "ForeverWowCraftAHButton", AuctionHouseFrame, "UIPanelButtonTemplate")
  button:SetSize(WIDTH, HEIGHT)
  button:SetPoint("TOPRIGHT", AuctionHouseFrame, "TOPRIGHT", -28, -2)      -- left of the close button
  -- pieces of the game's own frame are painted at high frame levels: a strata of its own
  -- puts the button above all of them (seen on the beta, 6 Oct 2026: level 11 was under)
  button:SetFrameStrata("DIALOG")
  button:SetToplevel(true)
  button:SetScript("OnClick", function()
    local sc = Scanner()
    if sc.Dirty() then sc.Reload()
    elseif not sc.Running() and sc.CooldownLeft() <= 0 then sc.StartSnapshot(false) end       -- no shift-click past the cooldown
  end)
  button:SetScript("OnEnter", Tip)
  button:SetScript("OnLeave", GameTooltip_Hide)
  return button
end

ns.OnScannerChanged = Draw

local watcher = CreateFrame("Frame")
watcher:RegisterEvent("AUCTION_HOUSE_SHOW")
watcher:RegisterEvent("AUCTION_HOUSE_CLOSED")
watcher:RegisterEvent("ADDON_LOADED")
watcher:SetScript("OnEvent", function(_, event, name)
  if event == "ADDON_LOADED" then
    if name == "Blizzard_AuctionHouseUI" or name == "Blizzard_AuctionUI" then Draw() end     -- the frame is there now
  elseif event == "AUCTION_HOUSE_SHOW" then
    if Button() then Draw() end
    if not ticker then ticker = C_Timer.NewTicker(1, Draw) end        -- the countdown
  elseif ticker then
    ticker:Cancel()
    ticker = nil
  end
end)

-- ================================================================ the options page
local function CheckBox(panel, y, label, note, get, set)
  local box = CreateFrame("CheckButton", nil, panel, "UICheckButtonTemplate")
  box:SetPoint("TOPLEFT", 16, y)
  box:SetSize(26, 26)
  box.label = panel:CreateFontString(nil, "ARTWORK", "GameFontNormal")
  box.label:SetPoint("LEFT", box, "RIGHT", 4, 0)
  box.label:SetText(label)
  box.note = panel:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
  box.note:SetPoint("TOPLEFT", box, "BOTTOMLEFT", 30, 2)
  box.note:SetWidth(520)
  box.note:SetJustifyH("LEFT")
  box.note:SetWordWrap(true)
  box.note:SetText(note)
  box:SetScript("OnClick", function(self) set(self:GetChecked() and true or false); Scanner().Refresh() end)
  box.refresh = function(self) self:SetChecked(get()) end
  box.get = get                              -- the switch as it stands (the tests read the shipped defaults by it)
  return box
end

local function BuildOptions()
  local panel = CreateFrame("Frame", "ForeverWowCraftOptions")
  panel.name = "ForeverWowCraft"
  -- every setting of the addon is here (a box or an entry for each, not a
  -- command alone); more than the options canvas is tall, so the page scrolls
  local scroll = CreateFrame("ScrollFrame", "ForeverWowCraftOptionsScroll", panel, "UIPanelScrollFrameTemplate")
  scroll:SetPoint("TOPLEFT", 0, -4)
  scroll:SetPoint("BOTTOMRIGHT", -28, 4)
  local page = CreateFrame("Frame", nil, scroll)
  page:SetSize(600, 960)
  scroll:SetScrollChild(page)
  local title = page:CreateFontString(nil, "ARTWORK", "GameFontNormalLarge")
  title:SetPoint("TOPLEFT", 16, -16)
  title:SetText("ForeverWowCraft")
  local blurb = page:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
  blurb:SetPoint("TOPLEFT", 16, -40)
  blurb:SetWidth(560)
  blurb:SetJustifyH("LEFT")
  blurb:SetWordWrap(true)
  blurb:SetText("The addon records the auction house's prices and sends them, through the helper on this PC, to "
    .. "foreverwowcraft.com, where every scanner's prices make the routes that /fwc shows. Nothing of yours is sent: "
    .. "only prices and the merchants and trainers you visit. Most switches here also have a command (type /fwcs for the list).")
  local saved = ns.Settings
  local y = -92
  local function Next(h) local at = y; y = y - h; return at end
  panel.boxes = {
    CheckBox(page, Next(54), "Scan by itself when the auction house opens",
      "When the auction house can be read again (once every 15 minutes). Otherwise the button on the auction house "
      .. "frame, or /fwcs full, starts a scan.",
      function() return Scanner().AutoScanEnabled() end, function(v) saved().auto = v end),
    CheckBox(page, Next(44), "A sound when prices are ready to save",
      "With the button lighting up on the auction house frame.",
      function() return Scanner().AlertEnabled() end, function(v) saved().alert = v end),
    CheckBox(page, Next(54), "Show the scanner's own bar (FULL, SCAN, SAVE, progress)",
      "For running scans by hand and watching them: the per-list SCAN, the telemetry panel. Off, the scanner is in "
      .. "the background and the button on the auction house frame is all there is.",
      function() return not Scanner().BarHidden() end, function(v) saved().hidden = not v end),
    CheckBox(page, Next(44), "The telemetry panel under the bar",
      "What the scan is doing, list by list. Only with the bar.",
      function() return saved().log == true end, function(v) saved().log = v end),
    CheckBox(page, Next(54), "A sound when the auction house can be read again",
      "Wherever you are, every 15 minutes. Off by default without the bar: the scan then starts by itself anyway.",
      function() return Scanner().ReadyAlertEnabled() end, function(v) saved().ding = v; Scanner().ArmReadyAlert() end),
    CheckBox(page, Next(54), "The arrow to what the Make button needs",
      "A trainer, a vendor, an auctioneer or a crafting station, and how far. The Arrow box at the top of the /fwc "
      .. "window is the same switch.",
      function() return saved().arrow ~= false end, function(v) ns.ArrowCommand(v and "on" or "off") end),
    CheckBox(page, Next(54), "The arrow stays when the profession window closes",
      "Kept until what it points at is reached or it is right-clicked. Unticked, it goes with the window.",
      function() return saved().arrowKeep ~= false end, function(v) saved().arrowKeep = v end),
    CheckBox(page, Next(44), "The shopping list opens with the auction house",
      "What the next step of the route needs bought, with a Buy button an item. Off, the Make button still opens it.",
      function() return saved().shop ~= false end, function(v) saved().shop = v end),
    CheckBox(page, Next(54), "Count other characters' bags and banks",
      "What your other characters of this auction house hold is taken off the /fwc window's list too. The "
      .. "'other characters' button in the window is the same switch.",
      function() return saved().alts ~= false end,
      function(v) saved().alts = v; if ns.RefreshWindow then ns.RefreshWindow() end end),
    CheckBox(page, Next(54), "Routes for my level",
      "A recipe whose scroll asks for a higher character level than yours is swapped for the next best recipe of that "
      .. "stretch, as the site does when you type your level. Where none fits, the Make button and the /fwc window say so.",
      function() return saved().levelRoutes ~= false end,
      function(v) saved().levelRoutes = v; if ns.RefreshWindow then ns.RefreshWindow() end; if ns.RoutePicked then ns.RoutePicked() end end),
    CheckBox(page, Next(54), "Use what I already have first",
      "Where a next-best recipe of a stretch costs you less with what is in your bags, bank and mail, the Make button, the "
      .. "shopping list, the arrow and the /fwc window use it, and say so. /fwcs have is the same switch.",
      function() return saved().haveFirst ~= false end,
      function(v) ns.HaveCommand(v and "on" or "off", true) end),
    CheckBox(page, Next(76), "A reminder to reload, every hour",
      "A small box at the top of the screen with a Reload now button, when there is something to save "
      .. "or the routes may have changed on the site: both move only at a reload. Never in combat, "
      .. "nor while the auction house, a merchant or a profession window is open. Later puts it off an hour.",
      function() return ns.remind.Enabled() end, function(v) ns.RemindCommand(v and "on" or "off") end),
    CheckBox(page, Next(76), "Cooking: Fishing only",
      "Plans this character's cooking from the fish you catch, a vendor's goods and a vendor's recipes, nothing from the "
      .. "auction house. It is also the third choice of the Mode button in the /fwc window, and /fwcs fishing is the same. "
      .. "Where the fish are caught is the Classic-era world's data. Kept for this character; it needs the route from the site.",
      function() return ns.FishingOn and ns.FishingOn() or false end,
      function(v) if ns.FishingCommand then ns.FishingCommand(v and "on" or "off", true) end end),
  }
  -- where the prices are kept: told from where the character stands, unless said here
  local where = page:CreateFontString(nil, "ARTWORK", "GameFontNormal")
  where:SetPoint("TOPLEFT", 20, Next(22))
  where:SetText("Keep the prices as the auction house of")
  local wnote = page:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
  wnote:SetPoint("TOPLEFT", 20, Next(34))
  wnote:SetWidth(540)
  wnote:SetJustifyH("LEFT")
  wnote:SetWordWrap(true)
  wnote:SetText("Told from where you stand, unless you say otherwise: a character who scans the other faction's house, or the "
    .. "neutral one both factions share (which is not scanned), says which. /fwcs house is the same.")
  panel.houses = {}
  local row, x = Next(30), 20
  for _, choice in ipairs({ { "auto", "Where you stand" }, { "alliance", "Alliance" }, { "horde", "Horde" }, { "neutral", "Neutral" } }) do
    local b = ns.Button(page, 130, choice[2], "ForeverWowCraftOptionsHouse" .. choice[2]:gsub(" ", ""))
    b:SetPoint("TOPLEFT", x, row)
    x = x + 136
    b.choice, b.label = choice[1], choice[2]
    b:SetScript("OnClick", function() ns.HouseCommand(choice[1]); panel:refresh() end)
    table.insert(panel.houses, b)
  end
  -- what was dragged, back where it started
  local reset = ns.Button(page, 200, "Put things back where they were", "ForeverWowCraftOptionsReset")
  reset:SetPoint("TOPLEFT", 20, Next(26))
  reset:SetScript("OnClick", function() ns.ResetPositions() end)
  local rnote = page:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
  rnote:SetPoint("TOPLEFT", 20, Next(20))
  rnote:SetWidth(540)
  rnote:SetJustifyH("LEFT")
  rnote:SetText("The scanner's bar, the /fwc window and the arrow, after being dragged about.")
  panel.refresh = function(self)
    for _, box in ipairs(self.boxes) do box:refresh(box) end
    local now = saved().house
    for _, hb in ipairs(self.houses) do
      local on = (now == nil and hb.choice == "auto") or (now ~= nil and now:lower() == hb.choice)
      hb:SetText((on and "|cff40ff40[x]|r " or "") .. hb.label)
    end
  end
  panel:SetScript("OnShow", function(self) self:refresh() end)
  -- The page showed every box unticked after an update: the frame is
  -- made at load with no parent, so it counts as shown from the start and OnShow never fires
  -- when the Settings window displays it. So: the Settings window's own call when the page
  -- is displayed (OnRefresh), and while the page is in sight, the boxes are read again every
  -- second (a /fwcs command typed meanwhile shows too). The settings themselves were never
  -- lost: FWCS_DB.__ui is the account's saved file, which no update touches.
  panel.OnRefresh = function(self) self:refresh() end
  panel.OnCommit = function() end
  panel.OnDefault = function(self)                 -- the Settings window's Defaults button: the shipped defaults again
    local s = saved()
    for _, key in ipairs({ "auto", "alert", "hidden", "log", "ding", "arrow", "arrowKeep", "shop", "alts", "levelRoutes", "haveFirst", "remind" }) do s[key] = nil end
    if ns.FishingCommand then ns.FishingCommand("off", true) end         -- this character's, not the account's: the same shipped default
    self:refresh()
    Scanner().Refresh()
  end
  if C_Timer and C_Timer.NewTicker then
    C_Timer.NewTicker(1, function() if panel:IsVisible() then panel:refresh() end end)
  end
  if _G.Settings and _G.Settings.RegisterCanvasLayoutCategory and _G.Settings.RegisterAddOnCategory then
    local category = _G.Settings.RegisterCanvasLayoutCategory(panel, panel.name)
    category.ID = panel.name
    _G.Settings.RegisterAddOnCategory(category)
    ns.optionsCategory = category
  elseif InterfaceOptions_AddCategory then
    InterfaceOptions_AddCategory(panel)
  end
  ns.options = panel
end

-- the scanner's bar, the /fwc window and the arrow back where they started (the options page)
function ns.ResetPositions()
  Scanner().ResetBar()
  ns.ArrowCommand("reset")
  if ns.ResetWindowPosition then ns.ResetWindowPosition() end
  ns.Print("the bar and the window are back where they started too")
end
pcall(BuildOptions)                       -- a client with neither way of registering still has the slash commands

function ns.OpenOptions()
  if _G.Settings and _G.Settings.OpenToCategory and ns.optionsCategory then _G.Settings.OpenToCategory(ns.optionsCategory.ID or ns.optionsCategory)
  elseif InterfaceOptionsFrame_OpenToCategory and ns.options then InterfaceOptionsFrame_OpenToCategory(ns.options); InterfaceOptionsFrame_OpenToCategory(ns.options)
  else ns.Print("the options are: /fwcs auto | bar | log | alert | ding | arrow | shop | have | house | remind") end
end

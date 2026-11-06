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
    GameTooltip:AddLine(string.format("The auction house can be read once every 15 minutes%s. Next in %s%s.%s",
      sc.AutoScanEnabled() and ", by itself when it is open" or "", sc.Clock(sc.CooldownLeft()),
      sc.CooldownKnown() and "" or " at the latest", sc.CooldownKnown() and "" or " Shift-click tries now."), 1, 1, 1, true)
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
    elseif not sc.Running() and (sc.CooldownLeft() <= 0 or IsShiftKeyDown and IsShiftKeyDown()) then sc.StartSnapshot(IsShiftKeyDown and IsShiftKeyDown() or false) end
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
  return box
end

local function BuildOptions()
  local panel = CreateFrame("Frame", "ForeverWowCraftOptions")
  panel.name = "ForeverWowCraft"
  local title = panel:CreateFontString(nil, "ARTWORK", "GameFontNormalLarge")
  title:SetPoint("TOPLEFT", 16, -16)
  title:SetText("ForeverWowCraft")
  local blurb = panel:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
  blurb:SetPoint("TOPLEFT", 16, -40)
  blurb:SetWidth(560)
  blurb:SetJustifyH("LEFT")
  blurb:SetWordWrap(true)
  blurb:SetText("The addon records the auction house's prices and sends them, through the helper on this PC, to "
    .. "foreverwowcraft.com, where every scanner's prices make the routes that /fwc shows. Nothing of yours is sent: "
    .. "prices only.")
  local saved = ns.Settings
  panel.boxes = {
    CheckBox(panel, -96, "Scan by itself when the auction house opens",
      "When the auction house can be read again (once every 15 minutes). Otherwise the button on the auction house "
      .. "frame, or /fwcs full, starts a scan.",
      function() return Scanner().AutoScanEnabled() end, function(v) saved().auto = v end),
    CheckBox(panel, -152, "A sound when prices are ready to save",
      "With the button lighting up on the auction house frame.",
      function() return Scanner().AlertEnabled() end, function(v) saved().alert = v end),
    CheckBox(panel, -196, "Show the scanner's own bar (FULL, SCAN, SAVE, progress)",
      "For running scans by hand and watching them: the per-list SCAN, the telemetry panel. Off, the scanner is in "
      .. "the background and the button on the auction house frame is all there is.",
      function() return not Scanner().BarHidden() end, function(v) saved().hidden = not v end),
    CheckBox(panel, -252, "A sound when the auction house can be read again",
      "Wherever you are, every 15 minutes. Off by default without the bar: the scan then starts by itself anyway.",
      function() return Scanner().ReadyAlertEnabled() end, function(v) saved().ding = v; Scanner().ArmReadyAlert() end),
    CheckBox(panel, -308, "The arrow stays when the profession window closes",
      "The Make button's arrow to a trainer, a vendor or an anvil: kept until what it points at is reached or it is "
      .. "right-clicked. Unticked, it goes with the window. /fwcs arrow off turns the arrow off altogether.",
      function() return saved().arrowKeep ~= false end, function(v) saved().arrowKeep = v end),
    CheckBox(panel, -352, "The shopping list opens with the auction house",
      "What the next step of the route needs bought, with a Buy button an item. Off, the Make button still opens it.",
      function() return saved().shop ~= false end, function(v) saved().shop = v end),
  }
  panel:SetScript("OnShow", function(self) for _, b in ipairs(self.boxes) do b:refresh(b) end end)
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
pcall(BuildOptions)                       -- a client with neither way of registering still has the slash commands

function ns.OpenOptions()
  if _G.Settings and _G.Settings.OpenToCategory and ns.optionsCategory then _G.Settings.OpenToCategory(ns.optionsCategory.ID or ns.optionsCategory)
  elseif InterfaceOptionsFrame_OpenToCategory and ns.options then InterfaceOptionsFrame_OpenToCategory(ns.options); InterfaceOptionsFrame_OpenToCategory(ns.options)
  else ns.Print("the options are: /fwcs auto | bar | alert | ding") end
end

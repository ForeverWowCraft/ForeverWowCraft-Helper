-- A reminder to reload, now and then: a small box at the top of the screen with a red "Reload
-- now" button (the user, 6 Nov 2026: another addon does this every quarter of an hour, and it
-- keeps what goes in and out in step).
--
-- Why a reload: what the addon records reaches the disk, and so the helper and the site,
-- only when the interface reloads or the character logs out;
-- and the routes the helper writes (Plans.lua, as the site has them) load only then. So every
-- EVERY seconds, when there is a reason, the box is shown. It waits while a reload would get
-- in the way: in combat, dead, while the scanner records, while the auction house, a merchant
-- or a profession window is open (the auction house has its own Save Prices button).
--
-- "Later" puts it off for LATER seconds; the small "off" turns the reminder off for good (the
-- box in Interface > AddOns > ForeverWowCraft, or /fwcs remind on, brings it back).

local _, ns = ...

local EVERY = 15 * 60                      -- seconds between reminders
local LATER = 15 * 60                      -- what "Later" buys
local RETRY = 30                           -- seconds between looks while something is in the way

local box, due
local loadedAt = time()

local function Settings() return ns.Settings() end
local function Enabled() return Settings().remind ~= false end
local function Scanner() return ns.scanner end

-- what a reload would do now; nothing when nothing
local function Reasons()
  local out = {}
  local sc = Scanner()
  -- prices named; the rest of what the addon notes is not spelt out (the user, 6 Nov 2026)
  if sc and sc.Dirty() then table.insert(out, "prices recorded, not yet saved")
  elseif (ns.notedAt or 0) > loadedAt then table.insert(out, "something noted, not yet saved") end
  -- the helper runs (it writes the routes as the site has them; a reload loads them): the routes
  -- may be newer than those on show
  if FWCS_PLANS_WRITTEN then table.insert(out, "the routes may have changed on the site") end
  return out
end

-- whether a reload now would get in the way
local function Busy()
  if InCombatLockdown and InCombatLockdown() then return true end
  if UnitAffectingCombat and UnitAffectingCombat("player") then return true end
  if UnitIsDeadOrGhost and UnitIsDeadOrGhost("player") then return true end
  local sc = Scanner()
  if sc and (sc.Running() or sc.Open()) then return true end
  for _, name in ipairs({ "MerchantFrame", "TradeSkillFrame", "ProfessionsFrame", "CraftFrame" }) do
    local f = _G[name]
    if f and f.IsShown and f:IsShown() then return true end
  end
  return false
end

local function Build()
  box = CreateFrame("Frame", "ForeverWowCraftReload", UIParent, "BackdropTemplate")
  box:SetSize(400, 64)
  box:SetPoint("TOP", UIParent, "TOP", 0, -140)
  box:SetFrameStrata("DIALOG")
  if box.SetBackdrop then
    box:SetBackdrop({ bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background", edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
                      tile = true, tileSize = 32, edgeSize = 24, insets = { left = 6, right = 6, top = 6, bottom = 6 } })
  end
  box:EnableMouse(true)
  box.title = box:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  box.title:SetPoint("TOPLEFT", 14, -12)
  box.title:SetWidth(252)                    -- short of the buttons: the title ran under them (the user, 7 Nov 2026)
  box.title:SetJustifyH("LEFT")
  box.title:SetWordWrap(false)
  box.title:SetText("|cff" .. ns.BRAND.gold .. "ForeverWowCraft|r: reload to save")
  box.why = box:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  box.why:SetPoint("TOPLEFT", box.title, "BOTTOMLEFT", 0, -4)
  box.why:SetWidth(252)
  box.why:SetJustifyH("LEFT")
  box.why:SetWordWrap(true)
  -- a secure button with a macro of its own, /reload: the game lets no addon call ReloadUI
  -- on Forever's client (the box showed and the button did nothing, two players, 6 Nov 2026),
  -- but a macro run by a click of a secure button it reloads for. The box goes with the click
  box.now = CreateFrame("Button", "ForeverWowCraftReloadNow", box, "SecureActionButtonTemplate, UIPanelButtonTemplate")
  box.now:SetSize(100, 22)
  box.now:SetText("Reload now")
  box.now:SetPoint("TOPRIGHT", -12, -12)
  box.now:SetAttribute("type", "macro")
  box.now:SetAttribute("macrotext", "/reload")
  box.now:RegisterForClicks("AnyDown", "AnyUp")
  box.now:SetScript("PostClick", function() box:Hide() end)
  box.later = ns.Button(box, 56, "Later", "ForeverWowCraftReloadLater")
  box.later:SetPoint("TOPRIGHT", box.now, "BOTTOMRIGHT", 0, -2)
  box.later:SetScript("OnClick", function() box:Hide(); due = time() + LATER end)
  box.off = CreateFrame("Button", "ForeverWowCraftReloadOff", box)
  box.off:SetSize(30, 20)
  box.off:SetPoint("RIGHT", box.later, "LEFT", -4, 0)
  box.off.text = box.off:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  box.off.text:SetPoint("CENTER")
  box.off.text:SetText("off")
  box.off:SetScript("OnClick", function() ns.RemindCommand("off") end)
  box.off:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
    GameTooltip:AddLine("No more reminders. Interface > AddOns > ForeverWowCraft, or /fwcs remind on, brings them back.", 1, 1, 1, true)
    GameTooltip:Show()
  end)
  box.off:SetScript("OnLeave", function() GameTooltip:Hide() end)
  box:Hide()
end

local function Show(reasons)
  if not box then Build() end
  box.why:SetText(table.concat(reasons, "; ") .. ".")
  if not box:IsShown() then
    box:Show()
    if PlaySound and SOUNDKIT and SOUNDKIT.IG_MAINMENU_OPEN then PlaySound(SOUNDKIT.IG_MAINMENU_OPEN, "Master") end
  end
end

-- every RETRY seconds: when the reminder is due, and nothing is in the way, and there is a
-- reason, the box; shown, it stays until a button is clicked, hiding while a fight is on
local function Check()
  if not Enabled() then if box then box:Hide() end return end
  if box and box:IsShown() then
    if Busy() then box:Hide(); due = time() end     -- back as soon as the way is clear
    return
  end
  due = due or loadedAt + EVERY
  if time() < due or Busy() then return end
  local reasons = Reasons()
  if #reasons == 0 then due = time() + EVERY; return end
  Show(reasons)
end

function ns.RemindCommand(arg)
  if arg == "on" then
    Settings().remind = nil
    due = time() + EVERY
    ns.Print(string.format("reload reminder on: every %d minutes, when there is something to save or routes may have changed", EVERY / 60))
  elseif arg == "off" then
    Settings().remind = false
    if box then box:Hide() end
    ns.Print("reload reminder off (/fwcs remind on brings it back)")
  elseif arg == "now" then
    local reasons = Reasons()
    if #reasons == 0 then ns.Print("nothing a reload would change right now") else Show(reasons) end
  else
    ns.Print("reload reminder " .. (Enabled() and "on" or "off") .. ": /fwcs remind on | off | now")
  end
  if ns.options and ns.options.boxes then for _, b in ipairs(ns.options.boxes) do b:refresh(b) end end
end

ns.remind = { Check = Check, Enabled = Enabled, Reasons = Reasons, Busy = Busy, Every = EVERY }
if C_Timer and C_Timer.NewTicker then C_Timer.NewTicker(RETRY, Check) end

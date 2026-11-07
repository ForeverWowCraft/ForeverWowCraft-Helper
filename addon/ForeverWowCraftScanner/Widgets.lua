-- Pieces of the window the game does not have ready-made, or has differently by client.

local _, ns = ...

-- a standard button, with a name when something has to find it
local function Button(parent, width, text, name)
  local b = CreateFrame("Button", name, parent, "UIPanelButtonTemplate")
  b:SetSize(width, 22)
  b:SetText(text)
  return b
end
ns.Button = Button

-- A reload the client allows. ReloadUI is C_UI.Reload, a protected function: called from the
-- addon's own code (a click on an ordinary button, a slash command) it is refused, "the client
-- refused UNKNOWN() from the addon (ADDON_ACTION_BLOCKED)" (WoW Forever 1.60, 7 Nov 2026).
-- What /reload typed does, a secure button with the macro "/reload" does: the game runs it, not
-- the addon. So over a button that reloads lies an invisible secure one that takes the click.
--
-- ns.ReloadOver(target, wanted, after, moves): over `target` while it is shown and wanted() is
-- true; after(), when given, is called after the click; with `moves`, a drag moves `target` as
-- a drag on it would (its OnDragStart and OnDragStop). A secure frame can be made, shown,
-- hidden and moved only out of combat: so it is made and placed out of combat only, and goes
-- the moment a fight starts; the button below it is clicked then, and says /reload does it.
local wishes, catchers = {}, {}

local function Make(w)
  local target = w.target
  local name = target.GetName and target:GetName()
  local c = CreateFrame("Button", name and (name .. "Secure") or nil, UIParent, "SecureActionButtonTemplate")
  c:RegisterForClicks("AnyUp")
  c:SetAttribute("useOnKeyDown", false)             -- the click acts on release, as the button below did
  c:SetAttribute("type", "macro")
  c:SetAttribute("macrotext", "/reload")
  c.target, c.wanted = target, w.wanted
  -- the button below looks as if it is the one pointed at
  c:SetScript("OnEnter", function()
    if target.LockHighlight then target:LockHighlight() end
    local f = target:GetScript("OnEnter"); if f then f(target) end
  end)
  c:SetScript("OnLeave", function()
    if target.UnlockHighlight then target:UnlockHighlight() end
    local f = target:GetScript("OnLeave"); if f then f(target) end
  end)
  c:SetScript("PostClick", function() if w.after then w.after() end end)
  if w.moves then
    c:RegisterForDrag("LeftButton")
    c:SetScript("OnDragStart", function() local f = target:GetScript("OnDragStart"); if f then f(target) end end)
    c:SetScript("OnDragStop", function() local f = target:GetScript("OnDragStop"); if f then f(target) end end)
  end
  c:Hide()
  table.insert(catchers, c)
  return c
end

local function Place(c)
  local t = c.target
  local show = t:IsVisible() and c.wanted() and t:GetLeft() ~= nil
  if not show then if c:IsShown() then c:Hide() end return end
  local s = t:GetEffectiveScale() / UIParent:GetEffectiveScale()
  local left, bottom, width, height = t:GetLeft() * s, t:GetBottom() * s, t:GetWidth() * s, t:GetHeight() * s
  if c.left ~= left or c.bottom ~= bottom or c.width ~= width or c.height ~= height then
    c.left, c.bottom, c.width, c.height = left, bottom, width, height
    c:ClearAllPoints()
    c:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", left, bottom)
    c:SetSize(width, height)
  end
  c:SetFrameStrata(t:GetFrameStrata())
  c:SetFrameLevel(t:GetFrameLevel() + 10)
  if not c:IsShown() then c:Show() end
end

local function InFight() return InCombatLockdown and InCombatLockdown() end

-- out of combat: made what is wished for, and every one placed (or hidden)
local function PlaceAll()
  if InFight() then return end
  while #wishes > 0 do Make(table.remove(wishes, 1)) end
  for _, c in ipairs(catchers) do Place(c) end
end

local placer = CreateFrame("Frame")
local since = 0
placer:SetScript("OnUpdate", function(_, elapsed)
  since = since + (elapsed or 0)
  if since < 0.1 then return end
  since = 0
  PlaceAll()
end)
placer:RegisterEvent("PLAYER_REGEN_DISABLED")       -- comes just before the lockdown: still allowed
placer:SetScript("OnEvent", function()
  for _, c in ipairs(catchers) do c:Hide() end
end)

local function ReloadOver(target, wanted, after, moves)
  table.insert(wishes, { target = target, wanted = wanted, after = after, moves = moves })
  PlaceAll()
end
ns.ReloadOver = ReloadOver
ns.reloadCatchers = catchers

-- A slider with two ends, which the game does not have: a track, a thumb at each end dragged
-- along it, the part between them filled. Values are whole skill points; the ends keep a
-- point apart. r.OnChanged(from, upto) is called when the mouse moves an end; r:Set does not.
local PAD = 8                                 -- the track's inset, so a thumb at an end is whole
local function RangeSlider(parent, width)
  local r = CreateFrame("Frame", "ForeverWowCraftRange", parent)
  r:SetSize(width, 20)
  r:EnableMouse(true)
  r.min, r.max, r.from, r.upto, r.dragging = 1, 2, 1, 2, false
  r.track = r:CreateTexture(nil, "BACKGROUND")
  r.track:SetPoint("LEFT", PAD, 0)
  r.track:SetPoint("RIGHT", -PAD, 0)
  r.track:SetHeight(4)
  r.track:SetColorTexture(0.25, 0.25, 0.3, 1)
  r.fill = r:CreateTexture(nil, "BORDER")
  r.fill:SetHeight(4)
  r.fill:SetColorTexture(0.2, 0.8, 1, 1)
  local function X(v) return PAD + (v - r.min) / math.max(1, r.max - r.min) * (width - 2 * PAD) end
  local function V(x) return r.min + (x - PAD) / (width - 2 * PAD) * math.max(1, r.max - r.min) end
  local function Under()                      -- the value under the mouse
    local x = GetCursorPosition() / r:GetEffectiveScale() - r:GetLeft()
    return V(x)
  end
  local function Thumb(which)
    local t = CreateFrame("Button", nil, r)
    t:SetSize(16, 16)
    t:SetFrameLevel(r:GetFrameLevel() + 2)
    t:SetNormalTexture("Interface\\Buttons\\UI-SliderBar-Button-Horizontal")
    t:SetHighlightTexture("Interface\\Buttons\\UI-SliderBar-Button-Horizontal", "ADD")
    t:SetScript("OnMouseDown", function() r.dragging = which end)
    t:SetScript("OnMouseUp", function() r.dragging = false end)
    return t
  end
  r.fromThumb, r.uptoThumb = Thumb("from"), Thumb("upto")
  function r:Draw()
    self.fromThumb:SetPoint("CENTER", self, "LEFT", X(self.from), 0)
    self.uptoThumb:SetPoint("CENTER", self, "LEFT", X(self.upto), 0)
    self.fill:SetPoint("LEFT", self, "LEFT", X(self.from), 0)
    self.fill:SetPoint("RIGHT", self, "LEFT", X(self.upto), 0)
    for _, box in ipairs({ { self.fromText, self.from }, { self.uptoText, self.upto } }) do
      if box[1] and not box[1]:HasFocus() then box[1]:SetText(box[2]) end     -- not under what is being typed
    end
  end
  function r:Set(min, max, from, upto)
    self.min, self.max, self.from, self.upto = min, max, from, upto
    self:Draw()
  end
  function r:Moved(which, value)              -- an end put at a value, by the mouse or by hand
    value = math.floor(value + 0.5)
    if which == "from" then value = math.max(self.min, math.min(value, self.upto - 1))
    else value = math.min(self.max, math.max(value, self.from + 1)) end
    if value == self[which] then return end
    self[which] = value
    self:Draw()
    if self.OnChanged then self.OnChanged(self.from, self.upto) end
  end
  r:SetScript("OnUpdate", function(self)
    if not self.dragging then return end
    if IsMouseButtonDown and not IsMouseButtonDown("LeftButton") then self.dragging = false return end
    self:Moved(self.dragging, Under())
  end)
  r:SetScript("OnMouseDown", function(self)   -- a click on the track: the nearer end comes to it
    local v = Under()
    self.dragging = math.abs(v - self.from) <= math.abs(v - self.upto) and "from" or "upto"
    self:Moved(self.dragging, v)
  end)
  r:SetScript("OnMouseUp", function(self) self.dragging = false end)
  r:SetScript("OnMouseWheel", function(self, delta)       -- the wheel moves the nearer end a point
    local v = Under()
    self:Moved(math.abs(v - self.from) <= math.abs(v - self.upto) and "from" or "upto",
      (math.abs(v - self.from) <= math.abs(v - self.upto) and self.from or self.upto) + delta)
  end)
  r:EnableMouseWheel(true)
  return r
end
ns.RangeSlider = RangeSlider

-- The game's profession panel: beside each recipe, what making one comes to. What it makes is
-- worth, less what its reagents cost, at the prices of the site's last scan of this
-- character's auction house (FWCS_PLANS[house].recipes[spell] = { reagents, worth }, from the
-- routes' document; fwchelper/plans.py says what it holds). Green when making one pays, red
-- when it costs; a grey ? where a reagent had no price.
--
-- The panel comes in three makes, and the client decides which. Forever's is
-- Blizzard_Professions (ProfessionsFrame, the newest): a scroll box that makes a row for each
-- recipe as it comes into view, the recipe in the row's element data. Blizzard_TradeSkillUI
-- with a RecipeList: rows that each hold their recipe (tradeSkillInfo.recipeID is the spell),
-- drawn by RecipeList:RefreshDisplay. The older TradeSkillFrame: fixed rows
-- TradeSkillSkill1.., an index into the list, drawn by TradeSkillFrame_Update, the spell from
-- the recipe link. All are loaded by the game when the panel first opens, so the hooks are
-- put in then.

local _, ns = ...
local House = ns.inv.House

local WIDTH = 84                           -- the text's room at the right of a row

-- (what making one comes to, reagents, worth as the route counts it, what it sells for if it
-- does, the chance that it sells, what a vendor pays) for a spell; nil when the document has
-- no such recipe; false in the first place when it has one without a price. The number is
-- the plain sale less the reagents (12 Oct 2026: what the house pays, which a maker of one
-- can check against it); a document from before that day has the first two alone, and the
-- route's count is the number then.
local function Margin(spell)
  local house = House()
  local row = house and house.recipes and house.recipes[spell]
  if row == nil then return nil end
  if row == false then return false end
  local sure = row[3] or row[2]
  return sure - row[1], row[1], row[2], sure, row[4], row[5]
end

-- an amount in one colour: green with a + when making one pays, red when it costs, grey for nothing
local function Plain(copper) return (ns.Money(copper):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")) end
local function Text(net)
  if net == nil then return "" end
  if net == false then return "|cff808080?|r" end
  if net > 0 then return "|cff40ff40+" .. Plain(net) .. "|r" end
  if net < 0 then return "|cffff6060" .. Plain(net) .. "|r" end
  return "|cff808080" .. Plain(0) .. "|r"
end

local function Tip(row)
  local spell = rawget(row, "fwcSpell")
  if not spell then return end
  local net, mats, worth, sure, chance, vendor = Margin(spell)
  if net == nil then return end
  -- once a hover: the row's own OnEnter and the hit frame over the number (Paint) both come here
  if rawget(GameTooltip, "fwcFor") == row and GameTooltip:IsShown() then return end
  GameTooltip.fwcFor = row
  local house = House()
  -- under the row's own tooltip when it has one (the newest panel shows the item's), else alone
  if not (GameTooltip.IsOwned and GameTooltip:IsOwned(row) and GameTooltip:IsShown()) then
    GameTooltip:SetOwner(row, "ANCHOR_RIGHT")
  else
    GameTooltip:AddLine(" ")
  end
  GameTooltip:AddLine("Making one")
  if net == false then
    GameTooltip:AddLine("A reagent had no price when the auction house was last scanned.", 1, 1, 1, true)
  elseif chance == nil then                       -- a document from before 12 Oct 2026: the route's count alone
    GameTooltip:AddDoubleLine("Reagents", ns.Money(mats), 1, 1, 1, 1, 1, 1)
    GameTooltip:AddDoubleLine("What it makes is worth", ns.Money(worth), 1, 1, 1, 1, 1, 1)
    GameTooltip:AddDoubleLine("Comes to", ns.Money(net), 1, 1, 1, 1, 1, 1)
    GameTooltip:AddLine("Reagents at the auction house or the vendor, or made where that is cheaper; what it makes "
      .. "valued as the route sells it, after the auction house's cut. foreverwowcraft.com's prices"
      .. (house and house.scanned_at and (", scanned " .. ns.Age(house.scanned_at)) or "") .. ".", 0.6, 0.6, 0.6, true)
  else
    local listed = sure ~= vendor or (vendor or 0) == 0
    GameTooltip:AddDoubleLine("Reagents", ns.Money(mats), 1, 1, 1, 1, 1, 1)
    if sure > 0 then
      GameTooltip:AddDoubleLine(listed and "Sells for, after the house's cut" or "A vendor pays", ns.Money(sure), 1, 1, 1, 1, 1, 1)
    end
    GameTooltip:AddDoubleLine("Comes to", ns.Money(net), 1, 1, 1, 1, 1, 1)
    if listed and sure > 0 then
      GameTooltip:AddLine(" ")
      GameTooltip:AddDoubleLine("Chance that it sells", string.format("%d%%", math.floor(chance * 100 + 0.5)), 0.8, 0.8, 0.8, 0.8, 0.8, 0.8)
      if (vendor or 0) > 0 then
        GameTooltip:AddDoubleLine("A vendor pays otherwise", ns.Money(vendor), 0.8, 0.8, 0.8, 0.8, 0.8, 0.8)
      end
      GameTooltip:AddDoubleLine("Counted as the route does", ns.Money(worth) .. ", comes to " .. ns.Money(worth - mats), 0.8, 0.8, 0.8, 0.8, 0.8, 0.8)
    end
    GameTooltip:AddLine("Reagents at the auction house or the vendor, or made where that is cheaper. The route counts a "
      .. "sale at the auction price after the cut, weighted by the chance that it sells, and the vendor's price otherwise. foreverwowcraft.com's prices"
      .. (house and house.scanned_at and (", scanned " .. ns.Age(house.scanned_at)) or "") .. ".", 0.6, 0.6, 0.6, true)
  end
  GameTooltip:Show()
end

local function Untip(row)
  if rawget(GameTooltip, "fwcFor") == row then GameTooltip.fwcFor = nil end
  if GameTooltip:GetOwner() == row then GameTooltip:Hide() end
end

-- the row's text, made the first time: at the right, over nothing of the row's own
local function Paint(row, spell)
  if not rawget(row, "fwcText") then
    row.fwcText = row:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    row.fwcText:SetPoint("RIGHT", row, "RIGHT", -6, 0)
    row.fwcText:SetWidth(WIDTH)
    row.fwcText:SetJustifyH("RIGHT")
    row:HookScript("OnEnter", Tip)
    row:HookScript("OnLeave", function() Untip(row) end)
    -- the number has a mouse of its own where the client lets a frame pass clicks and motion
    -- on to the row under it (12 Oct 2026: on the newest panel the row's own OnEnter was not
    -- seen to bring the tooltip; the row still selects and highlights)
    if type(row.SetPropagateMouseClicks) == "function" then
      local hit = CreateFrame("Frame", nil, row)
      hit:SetPoint("TOPLEFT", row.fwcText, "TOPLEFT", -2, 2)
      hit:SetPoint("BOTTOMRIGHT", row.fwcText, "BOTTOMRIGHT", 2, -2)
      hit:EnableMouse(true)
      hit:SetPropagateMouseClicks(true)
      if hit.SetPropagateMouseMotion then hit:SetPropagateMouseMotion(true) end
      hit:SetScript("OnEnter", function() Tip(row) end)
      hit:SetScript("OnLeave", function() Untip(row) end)
      row.fwcHit = hit
    end
  end
  row.fwcSpell = spell
  row.fwcText:SetText(spell and Text((Margin(spell))) or "")
end

-- Blizzard_Professions (the newest panel, Forever's): ProfessionsFrame.CraftingPage.RecipeList
-- .ScrollBox, whose rows are made for an element as it scrolls into view; the recipe is in
-- the element's data (a tree node holding { recipeInfo = { recipeID = the spell } }, or that
-- table itself)
local function RecipeOf(elementData)
  local data = elementData
  if type(data) == "table" and type(rawget(data, "GetData") or data.GetData) == "function" then
    local ok, inner = pcall(data.GetData, data)
    if ok then data = inner end
  end
  local info = type(data) == "table" and data.recipeInfo
  return type(info) == "table" and info.recipeID or nil
end
local function PaintBox(box)
  box:ForEachFrame(function(frame, elementData) Paint(frame, RecipeOf(elementData)) end)
end

-- Blizzard_TradeSkillUI's list: every row that holds a recipe
local function PaintList(list)
  for _, row in ipairs(list.buttons or {}) do
    local info = rawget(row, "tradeSkillInfo")
    local spell = type(info) == "table" and info.recipeID and (info.type == nil or info.type == "recipe") and info.recipeID or nil
    Paint(row, spell)
  end
end

-- the older panel: the rows shown are an index into the list, from the scroll
local function SpellOfLink(link)
  return link and tonumber(link:match("enchant:(%d+)")) or nil
end
local function PaintOld()
  local offset = FauxScrollFrame_GetOffset and TradeSkillListScrollFrame and FauxScrollFrame_GetOffset(TradeSkillListScrollFrame) or 0
  for i = 1, TRADE_SKILLS_DISPLAYED or 0 do
    local row = _G["TradeSkillSkill" .. i]
    if row then
      local index = i + offset
      local _, kind = GetTradeSkillInfo(index)
      Paint(row, kind ~= "header" and SpellOfLink(GetTradeSkillRecipeLink(index)) or nil)
    end
  end
end

local hooked = {}
local panel = CreateFrame("Frame")
local function Hook()
  local page = ProfessionsFrame and ProfessionsFrame.CraftingPage
  local box = page and page.RecipeList and page.RecipeList.ScrollBox
  if box and not hooked.box then
    hooked.box = true
    -- a row made for an element, and the box drawn again (a scroll, a filter, a search)
    local view = box.GetView and box:GetView()
    local made = ScrollBoxListViewMixin and ScrollBoxListViewMixin.Event and ScrollBoxListViewMixin.Event.OnInitializedFrame
    if view and view.RegisterCallback and made then
      view:RegisterCallback(made, function(_, frame, elementData) Paint(frame, RecipeOf(elementData)) end, panel)
    end
    local drawn = ScrollBoxListMixin and ScrollBoxListMixin.Event and ScrollBoxListMixin.Event.OnUpdate
    if box.RegisterCallback and drawn then
      box:RegisterCallback(drawn, function() PaintBox(box) end, panel)
    end
    pcall(PaintBox, box)
  end
  local list = TradeSkillFrame and TradeSkillFrame.RecipeList
  if list and list.RefreshDisplay and not hooked.list then
    hooked.list = true
    hooksecurefunc(list, "RefreshDisplay", function() PaintList(list) end)
    PaintList(list)
  end
  if TradeSkillFrame_Update and GetTradeSkillRecipeLink and not hooked.old then
    hooked.old = true
    hooksecurefunc("TradeSkillFrame_Update", PaintOld)
  end
end

for _, event in ipairs({ "ADDON_LOADED", "TRADE_SKILL_SHOW", "TRADE_SKILL_LIST_UPDATE", "TRADE_SKILL_UPDATE" }) do pcall(panel.RegisterEvent, panel, event) end
panel:SetScript("OnEvent", function(_, event, name)
  if event == "ADDON_LOADED" and name ~= "Blizzard_Professions" and name ~= "Blizzard_TradeSkillUI" then return end
  Hook()
  if event ~= "ADDON_LOADED" then      -- drawn again with the prices, in case the panel was already up
    local page = ProfessionsFrame and ProfessionsFrame.CraftingPage
    local box = page and page.RecipeList and page.RecipeList.ScrollBox
    if box and hooked.box then pcall(PaintBox, box) end
    local list = TradeSkillFrame and TradeSkillFrame.RecipeList
    if list and hooked.list then PaintList(list) end
    if hooked.old then PaintOld() end
  end
end)
Hook()

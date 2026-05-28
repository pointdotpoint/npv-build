-- npv_dumper: dumps the live player V's Character Customization (CC) state
-- to a JSON file that npv-build can consume via --cc-json.
--
-- Install: copy this file into
--   <CP2077>/bin/x64/plugins/cyber_engine_tweaks/mods/npv_dumper/init.lua
-- Load a save, open CET overlay (default hotkey: Ctrl+Home), run in console:
--   GetMod("npv_dumper").Dump()
-- Or press the bound hotkey (configure in CET Bindings -> npv_dumper).

local NPVDumper = {}

local function safeCNameStr(c)
  if c == nil then return nil end
  local t = type(c)
  if t == "string" then return c end
  if t == "userdata" then
    local v = nil
    pcall(function() v = c.value end)
    if v ~= nil then return tostring(v) end
    return tostring(c)
  end
  return tostring(c)
end

local function jsonEncode(value, indent)
  indent = indent or ""
  local nextIndent = indent .. "  "
  local t = type(value)
  if value == nil then return "null" end
  if t == "boolean" then return value and "true" or "false" end
  if t == "number" then return tostring(value) end
  if t == "string" then
    local s = value:gsub("\\", "\\\\"):gsub('"', '\\"'):gsub("\n", "\\n"):gsub("\r", "\\r"):gsub("\t", "\\t")
    return '"' .. s .. '"'
  end
  if t == "userdata" then
    return jsonEncode(safeCNameStr(value) or "<userdata>", indent)
  end
  if t == "table" then
    local isArray = true
    local n = 0
    for k, _ in pairs(value) do
      n = n + 1
      if type(k) ~= "number" then isArray = false break end
    end
    if n == 0 then return "{}" end
    local parts = {}
    if isArray then
      for i = 1, #value do
        table.insert(parts, nextIndent .. jsonEncode(value[i], nextIndent))
      end
      return "[\n" .. table.concat(parts, ",\n") .. "\n" .. indent .. "]"
    end
    local keys = {}
    for k, _ in pairs(value) do table.insert(keys, k) end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    for _, k in ipairs(keys) do
      table.insert(parts, nextIndent .. jsonEncode(tostring(k), nextIndent) .. ": " .. jsonEncode(value[k], nextIndent))
    end
    return "{\n" .. table.concat(parts, ",\n") .. "\n" .. indent .. "}"
  end
  return "null"
end

local function gather()
  local out = {
    patch = "2.13",
    body_rig = "unknown",
    head = {},
    hair = {},
    skin = {},
    diagnostics = {}
  }

  local player = Game.GetPlayer()
  if not player then
    out.diagnostics.error = "Game.GetPlayer() returned nil; load a save first."
    return out
  end

  local genderName = nil
  pcall(function() genderName = safeCNameStr(player:GetResolvedGenderName()) end)
  if genderName then
    out.diagnostics.gender = genderName
    local g = genderName:lower()
    if g:find("female") or g == "w" or g == "wa" then
      out.body_rig = "pwa"
    elseif g:find("male") or g == "m" or g == "ma" then
      out.body_rig = "pma"
    end
  end

  local appName = nil
  pcall(function() appName = safeCNameStr(player:GetCurrentAppearanceName()) end)
  if appName then
    out.diagnostics.current_appearance = appName
    local presetNum = appName:match("h0_(%d%d%d)")
    if presetNum then
      out.head.preset_id = tonumber(presetNum)
    end
    local tone = appName:match("__%d%d_ca_([a-z_]+)")
    if tone then
      out.skin.tone_id = tone
    end
  end

  -- TemplatePath / ResourcePath: extract the .ent path string
  pcall(function()
    local tp = player:GetTemplatePath()
    if tp ~= nil then
      local hashStr = nil
      pcall(function() hashStr = tostring(tp.hash) end)
      pcall(function()
        local v = tp.value
        if v ~= nil then out.diagnostics.template_path = safeCNameStr(v) end
      end)
      if not out.diagnostics.template_path and hashStr then
        out.diagnostics.template_path_hash = hashStr
      end
    end
  end)

  -- Try walking visualController.GetAppearance() on the player
  pcall(function()
    local visualCtrl = player:GetVisualControllerComponent()
    if visualCtrl then
      out.diagnostics.has_visual_controller = true
      local currApp = visualCtrl:GetAppearance()
      if currApp then
        out.diagnostics.visual_appearance = safeCNameStr(currApp)
      end
    end
  end)

  -- The CC state for the player is restored from save into the
  -- gameuiCharacterCustomizationGameController. Try Game.GetScriptableSystemsContainer.
  for _, sysName in ipairs({"CharacterCustomizationSystem", "PreviewSystem", "PlayerDevelopmentSystem", "EquipmentSystem"}) do
    pcall(function()
      local s = Game.GetScriptableSystemsContainer():Get(CName.new(sysName))
      if s then
        out.diagnostics["sys_" .. sysName] = "found"
      end
    end)
  end

  -- Try accessing the CC state via the global puppet preview chain
  pcall(function()
    local cs = player:GetCharacterCustomizationState()
    if cs then
      out.diagnostics.cc_state_via_player = "found"
      -- Probe what methods are on it
      for _, getter in ipairs({"GetCCStateString", "GetHash", "ToString"}) do
        pcall(function()
          local val = cs[getter] and cs[getter](cs)
          if val ~= nil then out.diagnostics["cc_" .. getter] = safeCNameStr(val) end
        end)
      end
    end
  end)

  -- Try a wider set of likely system names — naming has shifted across patches
  for _, sysName in ipairs({
    "CharacterCustomizationSaveSystem",
    "CharacterCustomizationGameController",
    "CharacterCustomizationCustomTabUserData",
    "MorphMenuUserData",
    "CCustomizationSystem",
    "PlayerVisualController",
    "AppearanceChangerSystem",
  }) do
    pcall(function()
      local s = Game.GetScriptableSystemsContainer():Get(CName.new(sysName))
      if s then out.diagnostics["sys_" .. sysName] = "found" end
    end)
  end

  -- Try the registered global Game.* helpers
  for _, helper in ipairs({
    "GetCharacterCustomizationOwnerSystem",
    "GetCharacterCustomizationSaveSystem",
    "GetCustomCharacterCustomizationSystem",
    "GetTransactionSystem",
  }) do
    pcall(function()
      local f = Game[helper]
      if f then
        local s = f()
        if s then out.diagnostics["helper_" .. helper] = "found" end
      end
    end)
  end

  -- Walk child entities mounted on the player puppet via the AttachmentSlots
  pcall(function()
    local atSlots = nil
    pcall(function() atSlots = player:GetAttachmentSlots() end)
    if atSlots then
      out.diagnostics.has_attachment_slots = true
      pcall(function()
        local slots = atSlots:GetAllSlots()
        if slots then
          out.diagnostics.slot_count = #slots
        end
      end)
    end
  end)

  -- Inspect the parts/character via the puppet's PartsManager (TPP_full_body chain)
  pcall(function()
    local appCtrl = player:GetVisualControllerComponent()
    if appCtrl then
      pcall(function()
        local apps = appCtrl:GetAppearancesNames()
        if apps then
          local list = {}
          for _, a in ipairs(apps) do table.insert(list, safeCNameStr(a)) end
          out.diagnostics.appearances_names = list
        end
      end)
    end
  end)

  -- Enumerate ALL component names + derive CC selections from them
  pcall(function()
    local comps = player:GetComponents()
    if comps then
      local names = {}
      local overlays = {}
      local hair_components = {}
      local body_components = {}
      for _, comp in ipairs(comps) do
        local cn = nil
        pcall(function() cn = safeCNameStr(comp:GetName()) end)
        if cn then
          table.insert(names, cn)
          -- Preset derivation: hx_NNN, heb_NNN, ht_NNN all carry the head preset id
          local presetNum = cn:match("^h[bextx]_(%d%d%d)_pwa") or cn:match("^h[bextx]_(%d%d%d)_pma")
          if presetNum and not out.head.preset_id then
            out.head.preset_id = tonumber(presetNum)
            out.diagnostics.preset_source = cn
          end
          -- Track overlay morphs (makeup, scars, tattoos, pimples, cyberware)
          local overlay = cn:match("^hx_%d+_p[wm]?a_*_+(.+)$") or cn:match("^hx_%d+_p[wmf]?a?_*_+(.+)$")
          if cn:find("^hx_") or cn:find("^morph_") then
            table.insert(overlays, cn)
          end
          -- Hair: hh_NNN_* numeric or fhair_<name>
          if cn:find("^hh_") or cn:find("^fhair_") then
            table.insert(hair_components, cn)
            if not out.hair.style_id then
              local hh = cn:match("^hh_(%d+)") or cn:match("^fhair_(%w+)")
              if hh then out.hair.style_id = hh end
            end
          end
          -- Body / skin tone: t0_NNN_pwa_base...
          if cn:find("^t0_") and cn:find("base") then
            table.insert(body_components, cn)
          end
        end
      end
      out.diagnostics.all_component_names = names
      out.diagnostics.overlays = overlays
      out.diagnostics.hair_components = hair_components
      out.diagnostics.body_components = body_components
    end
  end)

  -- Inspect the entity's components for hints about which head mesh is mounted
  pcall(function()
    local comps = player:GetComponents()
    if comps then
      local meshes = {}
      for _, comp in ipairs(comps) do
        local cn = nil
        pcall(function() cn = safeCNameStr(comp:GetName()) end)
        if cn and (cn:find("^h0_") or cn:find("^hh_") or cn:find("^t0_")) then
          local mesh = nil
          pcall(function()
            local m = comp.mesh
            if m and m.value then mesh = safeCNameStr(m.value) end
          end)
          table.insert(meshes, { name = cn, mesh = mesh })
        end
      end
      out.diagnostics.head_components = meshes
      -- Look for the h0_ component to derive preset_id
      for _, m in ipairs(meshes) do
        if m.name and m.name:find("^h0_") then
          local presetNum = m.name:match("h0_(%d%d%d)")
          if presetNum and not out.head.preset_id then
            out.head.preset_id = tonumber(presetNum)
            out.diagnostics.preset_source = "h0_component_name"
          end
        end
        if m.name and m.name:find("^hh_") then
          local hairNum = m.name:match("hh_(%d%d%d)")
          if hairNum then out.hair.style_id = hairNum end
        end
      end
    end
  end)

  return out
end

function NPVDumper.Dump()
  local data = gather()
  local path = "cc_dump.json"
  local file, err = io.open(path, "w")
  if not file then
    print("[npv_dumper] ERROR: cannot open " .. path .. " for write: " .. tostring(err))
    return nil
  end
  file:write(jsonEncode(data))
  file:close()
  print("[npv_dumper] Wrote " .. path .. " (preset_id=" .. tostring(data.head.preset_id) .. ", body_rig=" .. tostring(data.body_rig) .. ", tone=" .. tostring(data.skin.tone_id) .. ")")
  print("[npv_dumper] Full path: <CP2077>/bin/x64/plugins/cyber_engine_tweaks/mods/npv_dumper/" .. path)
  return path
end

registerForEvent("onInit", function()
  print("[npv_dumper] Loaded. Run GetMod('npv_dumper').Dump() in the CET console.")
end)

registerHotkey("npv_dumper_dump", "Dump CC to cc_dump.json", function()
  NPVDumper.Dump()
end)

return NPVDumper

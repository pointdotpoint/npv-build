// Injected before page scripts run. Provides window.__mockApi so Api.call()
// (see npv_build/webui/js/api.js) short-circuits to these in-browser mocks
// instead of reaching for window.pywebview.api.
window.__mockApi = {
  get_state: async () => ({
    settings: { game_dir: "/g", output_dir: null, clothing_images_dir: null },
    default_output_root: "/out",
    deps: { wolvenkit: true, blender: false, npv_inject: true, game_dir_valid: true },
    tool_paths: { wolvenkit: "/cache/tools/wolvenkit/cp77tools", blender: null },
    needs_onboarding: false, version: "test",
  }),
  _cacheEntries: [
    { name: "index", path: "/cache/index", size: 2048576, clearable: true },
    { name: "tools", path: "/cache/tools", size: 1073741824, clearable: true },
  ],
  cache_info: async function () { return { ok: true, entries: this._cacheEntries }; },
  _cleared: [],
  clear_cache: async function (name) {
    this._cleared.push(name);
    this._cacheEntries = this._cacheEntries.filter((e) => e.name !== name);
    return { ok: true };
  },
  install_tools: async () => ({ ok: true }),
  _toolPolls: 0,
  poll_tool_events: async function () {
    this._toolPolls += 1;
    if (this._toolPolls === 1) return [
      { kind: "tool_progress", message: "Downloading Blender", value: 50 },
    ];
    if (this._toolPolls === 2) return [{ kind: "tool_done" }];
    return [];
  },
  list_saves: async () => [
    { path: "/saves/good/sav.dat", name: "ManualSave-3", mtime: 1752800000,
      thumbnail: null, patch: "2.31" },
    { path: "/saves/bad/sav.dat", name: "BadSave-1", mtime: 1752700000,
      thumbnail: null, patch: null },
  ],
  list_presets: async () => ({
    ok: true,
    presets: [
      { rig: "pwa", available: true },
      { rig: "pma", available: false },
    ],
  }),
  preview_preset: async () => ({
    ok: true,
    body_rig: "pwa",
    skin_tone: "01_ca_pale",
    hair_style: "hh_040",
    hair_color: "copper",
    selections_count: 150,
  }),
  browse_for_save: async () => ({
    ok: true,
    save: { path: "/saves/browsed/sav.dat", name: "BrowsedSave", mtime: 1752900000,
            thumbnail: null, patch: "2.31" },
  }),
  add_save_path: async (path) => ({
    ok: true,
    save: { path: path, name: "DroppedSave", mtime: 1752950000,
            thumbnail: null, patch: "2.31" },
  }),
  preview_save: async (path) => {
    if (path === "/saves/bad/sav.dat") {
      return { ok: false, error: "Unsupported patch", remediation: "Update npv-build" };
    }
    return { ok: true, body_rig: "pwa", skin_tone: "03",
      hair_style: "bob", hair_color: "copper", selections_count: 152 };
  },
  _startRequests: [],
  start_build: async function (request) {
    this._startRequests.push(request);
    return { ok: true };
  },
  _polls: 0,
  poll_events: async function () {
    this._polls += 1;
    if (this._polls === 1) return [
      { kind: "stage", stage: "parse_save", status: "started", message: "Parsing" },
      { kind: "log", text: "[parse_save] Parsing...\n" },
      { kind: "stage", stage: "parse_save", status: "completed", message: "ok" },
    ];
    if (this._polls === 2) return [{ kind: "done", output_dir: "/out/v" }];
    return [];
  },
  _mods: [{ mod_id: "v_abc", archive_path: "/out/v/archive/pc/mod/v_abc.archive",
            installed: false, built_at: 1752900000, npv_name: "TestV",
            save_path: "/saves/good/sav.dat" }],
  list_mods: async function () { return { ok: true, mods: this._mods }; },
  delete_mod: async function (modId) {
    this._mods = this._mods.filter((m) => m.mod_id !== modId);
    return { ok: true };
  },
  install_mod: async () => ({ ok: true }),
  cancel_build: async () => ({ ok: true }),
  zip_info: async () => ({ ok: true, zip: {
    path: "/out/v/v_abc.zip", size: 6626117,
    files: [
      { name: "archive/pc/mod/v_abc.archive", size: 6615040 },
      { name: "bin/x64/plugins/cyber_engine_tweaks/mods/AppearanceMenuMod/Collabs/Custom Entities/v_abc.lua", size: 10683 },
    ],
  } }),
  _opened: [],
  open_folder: async function (path) { this._opened.push(path); return { ok: true }; },
  appearance_data: async () => ({
    ok: true,
    categories: ["Skin", "Hair", "Eyes", "Body", "Face morphs"],
    overrides: {},
    rows: [
      { category: "Skin", slot_id: "skin_tone", label: "Skin tone",
        value_label: "01_ca_pale", value_raw: "01_ca_pale", editable: true,
        options: ["01_ca_pale", "03_ca_medium"] },
      { category: "Hair", slot_id: "hair_style", label: "Hair style",
        value_label: "winona_2", value_raw: "winona_2", editable: true,
        options: ["winona_2", "hh_041_pwa__bob"] },
      { category: "Hair", slot_id: "hair_color", label: "Hair color",
        value_label: "51_succulent", value_raw: "51_succulent", editable: true,
        options: ["51_succulent", "06_black_carbon"] },
      { category: "Face morphs", slot_id: "face_morph_eyes",
        label: "Eyes (morph preset)", value_label: "h091", value_raw: "h091",
        editable: false, options: [] },
    ],
  }),
  preset_appearance_data: async function () {
    const out = await this.appearance_data();
    const current = '{"label":"cyberware_01","raw":"hx_000_pwa__cyberware_01__03_ca_senna"}';
    const alternate = '{"label":"cyberware_02","raw":"hx_000_pwa__cyberware_02__03_ca_senna"}';
    out.categories.push("Face accessories");
    out.rows.push({
      category: "Face accessories", slot_id: "cc:cyberware_01",
      label: "Cyberware", value_label: "cyberware 01 · 03 ca senna",
      value_raw: current, editable: true,
      options: [
        { value: current, label: "Cyberware 01 · 03 ca senna" },
        { value: alternate, label: "Cyberware 02 · 03 ca senna" },
      ],
    });
    return out;
  },
  _overrides: {},
  set_overrides: async function (path, overrides) {
    if (overrides.skin_tone === "reject_me")
      return { ok: false, error: "skin_tone: not a known option", remediation: "" };
    this._overrides = overrides;
    return { ok: true };
  },
  browse_for_hair_mod: async () => ({
    ok: true, token: "edie", source: "edie_hair.archive",
    warning: "The NPV needs this hair mod to stay installed.",
  }),
  add_hair_mod: async (path) => ({
    ok: true, token: "edie", source: "edie_hair.archive",
    warning: "The NPV needs this hair mod to stay installed.",
  }),
};

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
  _catalogBuilt: true,
  clothing_catalog_status: async function () {
    return {
      ok: true, built: this._catalogBuilt, count: this._catalogBuilt ? 2 : 0,
    };
  },
  clothing_search: async (q, slot, rig) => ({ ok: true, items: [
    { item_id: "A", name: "RED SWEATER", image: "/i/a.jpg", slot: "inner_torso",
      mesh: "base\\characters\\garment\\player_equipment\\torso\\t1_024_pwa_tshirt__sweater.mesh",
      appearance: "red",
      selection: {
        item_id: "A", name: "RED SWEATER", slot: "inner_torso",
        mesh: "base\\characters\\garment\\player_equipment\\torso\\t1_024_pwa_tshirt__sweater.mesh",
        appearance: "red", occupied_slots: ["inner_torso"],
        source_kind: "catalog",
        components: [{
          type: "entGarmentSkinnedMeshComponent", name: "red_sweater",
          mesh: "base\\characters\\garment\\player_equipment\\torso\\t1_024_pwa_tshirt__sweater.mesh",
          appearance: "red", bind_to: "root", chunk_mask: "",
        }],
      },
      buildable: true },
    { item_id: "C", name: "GHOST SWEATER", image: "/i/c.jpg", slot: "inner_torso",
      mesh: null, buildable: false },
  ].filter((item) =>
    item.slot === slot && (!q || item.name.toLowerCase().includes(q.toLowerCase()))
  ) }),
  clothing_thumb: async () => ({ ok: true, b64: null }),
  build_clothing_catalog: async () => ({ ok: true }),
  poll_catalog_events: async function () {
    this._catalogBuilt = true;
    return [{ kind: "catalog_done", count: 2 }];
  },
  list_saves: async () => [
    { path: "/saves/good/sav.dat", name: "ManualSave-3", mtime: 1752800000,
      thumbnail: "/saves/good/screenshot.png", patch: "2.31" },
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
  add_photomode_thumbnail: async (path) => ({
    ok: true,
    thumbnail: {
      path: path, name: "screenshot.png", width: 1920, height: 1080,
      preview: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Crect width='200' height='200' fill='%23d02080'/%3E%3C/svg%3E",
    },
  }),
  browse_for_photomode_thumbnail: async function () {
    return this.add_photomode_thumbnail("/picked/portrait.png");
  },
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
            save_path: "/saves/good/sav.dat", output_dir: "/out/v",
            photomode_thumbnail: {
              path: "/saves/good/screenshot.png", name: "screenshot.png",
              width: 1920, height: 1080, preview: null,
            }, photomode_thumbnail_missing: false },
           { mod_id: "v_preset", archive_path: "/out/p/archive/pc/mod/v_preset.archive",
             installed: false, built_at: 1752900001, npv_name: "PresetV",
             preset_rig: "pwa", output_dir: "/out/p",
             photomode_thumbnail: null, photomode_thumbnail_missing: false }],
  list_mods: async function () { return { ok: true, mods: this._mods }; },
  delete_mod: async function (modId) {
    this._mods = this._mods.filter((m) => m.mod_id !== modId);
    return { ok: true };
  },
  install_mod: async () => ({ ok: true }),
  _renderActive: false,
  render_preview_progress: async function (outputDir) {
    if (!this._renderActive) return { active: false, message: "", current: 0, total: 0 };
    return { active: true, message: "Exporting torso", current: 12, total: 28 };
  },
  render_npv_preview: async function (outputDir) {
    this._renderActive = true;
    // Long enough for the frontend's progress poll to fire at least once.
    await new Promise((resolve) => setTimeout(resolve, 1500));
    this._renderActive = false;
    return {
    ok: true,
    fidelity: "clay",
    fidelity_note: "Untextured preview: shape, outfit and hairstyle are accurate, but colours and patterns (skin tone, tattoos, makeup, hair colour) are not shown. Check those in game.",
    images: [
      { view: "full_front", path: "/out/x/preview/full_front.png",
        data_url: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==" },
      { view: "face_front", path: "/out/x/preview/face_front.png",
        data_url: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==" },
    ],
    };
  },
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
    overrides: JSON.parse(localStorage.getItem("npv-test-overrides") || "{}"),
    garments: {
      inner_torso: "t1_024_pwa_tshirt__sweater",
      legs: "l1_012_pwa_pants__jeans_tight",
      feet: "s1_066_pwa_boot__bovver",
    },
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
    localStorage.setItem("npv-test-overrides", JSON.stringify(overrides));
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

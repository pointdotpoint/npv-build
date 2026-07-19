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
  start_build: async () => ({ ok: true }),
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
};

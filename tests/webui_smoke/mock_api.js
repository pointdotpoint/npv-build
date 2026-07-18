// Injected before page scripts run. Provides window.__mockApi so Api.call()
// (see npv_build/webui/js/api.js) short-circuits to these in-browser mocks
// instead of reaching for window.pywebview.api.
window.__mockApi = {
  get_state: async () => ({
    settings: { game_dir: "/g", output_dir: "/out" },
    deps: { wolvenkit: true, blender: true, npv_inject: true, game_dir_valid: true },
    needs_onboarding: false, version: "test",
  }),
  list_saves: async () => [
    { path: "/saves/good/sav.dat", name: "ManualSave-3", mtime: 1752800000, thumbnail: null },
    { path: "/saves/bad/sav.dat", name: "BadSave-1", mtime: 1752700000, thumbnail: null },
  ],
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
  list_mods: async () => [{ mod_id: "v_abc", archive_path: "/out/v/v_abc.archive",
                            installed: false }],
  install_mod: async () => ({ ok: true }),
  cancel_build: async () => ({ ok: true }),
};

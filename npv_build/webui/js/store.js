"use strict";
window.store = {
  state: {
    screen: "source",
    stepsDone: { source: false, appearance: false, build: false },
    appState: null,            // get_state() payload
    save: null,                // selected save {path, name, preview}
    preset: null,              // selected default-V preset {rig, preview}
    npvName: "", outputDir: "",
    photomodeThumbnail: null,   // {path, name, width, height, preview}
    appearanceBusy: false,     // true while a hair mod is being loaded/validated
    build: { running: false, stages: [], log: "", error: null, outputDir: null },
  },
  _subs: [],
  set(patch) {
    Object.assign(this.state, patch);
    for (const fn of this._subs) fn(this.state);
  },
  subscribe(fn) { this._subs.push(fn); },
};

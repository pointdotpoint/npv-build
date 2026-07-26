"use strict";

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

window.screens = window.screens || {};
window.screens.source = {
  saves: null,
  presets: null,
  scratchOpen: false,
  _presetError: null,
  _pickToken: 0,
  async load() {
    const [saves, presetsOut] = await Promise.all([
      Api.call("list_saves"),
      Api.call("list_presets"),
    ]);
    this.saves = saves;
    this.presets = presetsOut.ok ? presetsOut.presets : [];
    store.set({});
  },
  render(el, s) {
    if (this.saves === null || this.presets === null) {
      el.innerHTML = "<h1>Source</h1><p class='subtitle'>Scanning for saves…</p>";
      this.load();
      return;
    }
    el.innerHTML = "<h1>Source</h1>" +
      "<p class='subtitle'>Pick the save to turn into an NPC, or start from scratch.</p>";
    const list = document.createElement("div");
    for (const save of this.saves) {
      const card = document.createElement("div");
      const isSelected = s.save && s.save.path === save.path;
      card.className = "card selectable save-card" + (isSelected ? " selected" : "");
      const date = new Date(save.mtime * 1000).toLocaleString();
      let previewHtml = "…";
      if (isSelected && s.save.preview) {
        const preview = s.save.preview;
        if (preview.ok) {
          previewHtml = esc(`${preview.body_rig} · skin ${preview.skin_tone} · ${preview.hair_style}`);
        } else {
          card.classList.add("error-card");
          previewHtml = `<span class="err">${esc(preview.error)}</span>` +
            `<div class="remediation">${esc(preview.remediation)}</div>`;
        }
      }
      const badge = save.patch ? `<span class="badge">${esc(save.patch)}</span>` : "";
      card.innerHTML = `<div class="row"><span><strong>${esc(save.name)}</strong>${badge}</span>` +
        `<span class="muted">${date}</span></div>` +
        `<div class="muted preview">${previewHtml}</div>`;
      card.onclick = () => this.pick(save, card);
      list.appendChild(card);
    }
    const scratch = document.createElement("div");
    const hasPreset = this.presets.some((preset) => preset.available);
    scratch.className = "card" + (hasPreset ? " selectable" : "") +
      (s.preset ? " selected" : "");
    if (!hasPreset) scratch.style.opacity = ".5";
    scratch.innerHTML = "<strong>From scratch</strong>" +
      `<div class='muted'>${hasPreset
        ? "Start from a bundled default V preset."
        : "Default V presets have not been generated yet."}</div>`;
    if (hasPreset) {
      scratch.onclick = () => {
        this.scratchOpen = true;
        store.set({});
      };
    }
    if (this.scratchOpen || s.preset) {
      const rigRow = document.createElement("div");
      rigRow.className = "row";
      rigRow.style.marginTop = "12px";
      for (const preset of this.presets) {
        const button = document.createElement("button");
        button.id = `rig-${preset.rig}`;
        button.className = "secondary";
        button.textContent = preset.rig;
        button.disabled = !preset.available;
        button.title = preset.available
          ? `Use the default ${preset.rig} V preset`
          : `The default ${preset.rig} V preset is not bundled yet`;
        button.onclick = (event) => {
          event.stopPropagation();
          this.pickPreset(preset.rig);
        };
        rigRow.appendChild(button);
      }
      scratch.appendChild(rigRow);
    }
    list.appendChild(scratch);
    el.appendChild(list);

    const sourceError = document.createElement("div");
    sourceError.className = "form-error err";
    sourceError.style.display = "none";
    sourceError.style.marginTop = "12px";
    el.appendChild(sourceError);
    const showError = (msg) => {
      sourceError.textContent = msg;
      sourceError.style.display = "";
    };
    if (this._presetError) {
      showError(this._presetError);
      this._presetError = null;
    }

    const browse = document.createElement("button");
    browse.className = "secondary";
    browse.textContent = "Browse…";
    browse.style.marginTop = "12px";
    browse.onclick = async () => {
      const out = await Api.call("browse_for_save");
      if (out.cancelled) return;
      if (!out.ok) { showError(out.error + " " + (out.remediation || "")); return; }
      this.addSave(out.save);
    };
    el.appendChild(browse);

    // Drag & drop a sav.dat (or its folder) anywhere on the screen. Full
    // paths are only exposed by the pywebview desktop shell.
    el.ondragover = (e) => e.preventDefault();
    el.ondrop = async (e) => {
      e.preventDefault();
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      const path = f && (f.pywebviewFullPath || f.path);
      if (!path) {
        showError("Drag & drop needs the desktop app — use Browse… instead.");
        return;
      }
      const out = await Api.call("add_save_path", path);
      if (!out.ok) { showError(out.error + " " + (out.remediation || "")); return; }
      this.addSave(out.save);
    };

    const cont = document.createElement("button");
    cont.textContent = "Continue →";
    cont.style.marginTop = "16px";
    cont.disabled = !(
      (s.save && s.save.preview && s.save.preview.ok) ||
      s.preset
    );
    cont.onclick = () => {
      store.set({
        stepsDone: { ...store.state.stepsDone, source: true },
        screen: "appearance",
      });
    };
    el.appendChild(cont);
  },
  addSave(save) {
    this.saves = [save, ...this.saves.filter((s) => s.path !== save.path)];
    this.pick(save);
  },
  async pick(save, card) {
    const token = (this._pickToken = (this._pickToken || 0) + 1);
    store.set({ save: null, preset: null, photomodeThumbnail: null });
    if (card) card.querySelector(".preview").textContent = "Parsing…";
    const preview = await Api.call("preview_save", save.path);
    if (token !== this._pickToken) return; // superseded by a newer click
    if (!preview.ok) {
      store.set({ save: { ...save, preview }, preset: null });
      return;
    }
    const defaults = {};
    if (!store.state.npvName) defaults.npvName = save.name;
    const outRoot = store.state.appState.default_output_root ||
      store.state.appState.settings.output_dir;
    if (!store.state.outputDir && outRoot)
      defaults.outputDir = outRoot + "/" + save.name;
    store.set({ save: { ...save, preview }, preset: null, ...defaults });
  },
  async pickPreset(rig) {
    const token = (this._pickToken = (this._pickToken || 0) + 1);
    store.set({ save: null, preset: null, photomodeThumbnail: null });
    const preview = await Api.call("preview_preset", rig);
    if (token !== this._pickToken) return;
    if (!preview.ok) {
      this._presetError = preview.error + " " + (preview.remediation || "");
      store.set({});
      return;
    }
    const defaults = {};
    if (!store.state.npvName) defaults.npvName = "Default V";
    const outRoot = store.state.appState.default_output_root ||
      store.state.appState.settings.output_dir || "";
    if (!store.state.outputDir && outRoot)
      defaults.outputDir = outRoot + "/DefaultV-" + rig;
    store.set({
      preset: { rig, preview },
      save: null,
      ...defaults,
    });
  },
};

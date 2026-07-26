"use strict";

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

window.screens = window.screens || {};
window.screens.library = {
  mods: null,
  error: null,
  async load() {
    const out = await Api.call("list_mods");
    if (!out.ok) {
      this.mods = [];
      this.error = out.error + (out.remediation ? " — " + out.remediation : "");
    } else {
      this.mods = out.mods;
      this.error = null;
    }
    store.set({});
  },
  render(el) {
    if (this.mods === null) {
      el.innerHTML = "<h1>My NPVs</h1><p class='subtitle'>Loading…</p>";
      this.load();
      return;
    }
    el.innerHTML = "<h1>My NPVs</h1>" +
      "<p class='subtitle'>Built NPVs found in your output directory.</p>";
    if (this.error) {
      const err = document.createElement("p");
      err.className = "err";
      err.textContent = this.error;
      el.appendChild(err);
    }
    const grid = document.createElement("div");
    grid.className = "grid";
    for (const mod of this.mods) {
      const card = document.createElement("div");
      card.className = "card";
      const built = mod.built_at
        ? new Date(mod.built_at * 1000).toLocaleString() : "";
      card.innerHTML = `<strong>${esc(mod.npv_name || mod.mod_id)}</strong>` +
        (mod.npv_name
          ? `<div class="muted" style="font-size:12px">${esc(mod.mod_id)}</div>` : "") +
        `<div style="margin:8px 0"><span class="badge">` +
        `${mod.installed ? "installed" : "built"}</span>` +
        (built ? ` <span class="muted" style="font-size:12px">built ${esc(built)}</span>` : "") +
        `</div>`;
      const btn = document.createElement("button");
      btn.className = mod.installed ? "secondary" : "";
      btn.textContent = mod.installed ? "Uninstall" : "Install";
      btn.onclick = async () => {
        btn.disabled = true;
        try {
          const method = mod.installed ? "uninstall_mod" : "install_mod";
          const out = await Api.call(method, mod.mod_id);
          if (out.ok) this.load();
          else {
            btn.textContent = out.error;
            btn.classList.add("err");
          }
        } finally {
          btn.disabled = false;
        }
      };
      card.appendChild(btn);

      const rebuild = document.createElement("button");
      rebuild.className = "secondary";
      rebuild.style.marginLeft = "8px";
      rebuild.textContent = "Rebuild";
      if ((mod.save_path || mod.preset_rig) && mod.npv_name) {
        rebuild.onclick = () => {
          const outputDir = mod.archive_path
            .replace(/[\\/]archive[\\/]pc[\\/]mod[\\/][^\\/]+$/, "");
          const needsThumbnail = mod.photomode_thumbnail_missing ||
            !mod.photomode_thumbnail;
          store.set({
            save: mod.save_path
              ? { path: mod.save_path, name: mod.npv_name, preview: null }
              : null,
            preset: mod.preset_rig
              ? { rig: mod.preset_rig, preview: null, overrides: {} }
              : null,
            photomodeThumbnail: mod.photomode_thumbnail || null,
            npvName: mod.npv_name, outputDir,
            stepsDone: {
              source: true,
              appearance: !needsThumbnail,
              build: false,
            },
            build: { running: false, stages: {}, log: "", error: null, outputDir: null },
            screen: needsThumbnail ? "appearance" : "build",
          });
        };
      } else {
        rebuild.disabled = true;
        rebuild.title = "Built before rebuild metadata existed — build from the save instead.";
      }
      card.appendChild(rebuild);

      const del = document.createElement("button");
      del.className = "secondary";
      del.style.marginLeft = "8px";
      del.textContent = "Delete";
      del.onclick = async () => {
        if (del.textContent === "Delete") {
          del.textContent = "Really delete?";
          del.classList.add("err");
          return;
        }
        del.disabled = true;
        try {
          const out = await Api.call("delete_mod", mod.mod_id);
          if (out.ok) this.load();
          else { del.textContent = out.error; }
        } finally {
          del.disabled = false;
        }
      };
      card.appendChild(del);
      grid.appendChild(card);
    }
    if (!this.mods.length) {
      grid.innerHTML = "<p class='muted'>Nothing built yet.</p>";
    }
    el.appendChild(grid);
  },
};

"use strict";

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

window.screens = window.screens || {};
window.screens.library = {
  mods: null,
  async load() { this.mods = await Api.call("list_mods"); store.set({}); },
  render(el) {
    if (this.mods === null) {
      el.innerHTML = "<h1>My NPVs</h1><p class='subtitle'>Loading…</p>";
      this.load();
      return;
    }
    el.innerHTML = "<h1>My NPVs</h1>" +
      "<p class='subtitle'>Built NPVs found in your output directory.</p>";
    const grid = document.createElement("div");
    grid.className = "grid";
    for (const mod of this.mods) {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `<strong>${esc(mod.mod_id)}</strong>` +
        `<div style="margin:8px 0"><span class="badge">` +
        `${mod.installed ? "installed" : "built"}</span></div>`;
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
            btn.textContent = esc(out.error);
            btn.classList.add("err");
          }
        } finally {
          btn.disabled = false;
        }
      };
      card.appendChild(btn);
      grid.appendChild(card);
    }
    if (!this.mods.length) {
      grid.innerHTML = "<p class='muted'>Nothing built yet.</p>";
    }
    el.appendChild(grid);
  },
};

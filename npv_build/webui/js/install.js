"use strict";

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

window.screens = window.screens || {};
window.screens.install = {
  render(el, s) {
    el.innerHTML = "<h1>Done</h1>" +
      `<p class="subtitle">"${esc(s.npvName)}" built successfully.</p>`;
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `<div class="row"><span>Output</span>` +
      `<strong>${esc(s.build.outputDir || "")}</strong></div>` +
      `<div class="muted">The mod zip inside is ready for AMM: spawn it from ` +
      `Appearance Menu Mod → Custom Entities after installing.</div>`;
    el.appendChild(card);
    const row = document.createElement("div");
    row.className = "row"; row.style.marginTop = "16px";
    const install = document.createElement("button");
    install.textContent = "Install to game";
    install.onclick = async () => {
      install.disabled = true;
      try {
        const mods = await Api.call("list_mods");
        const mine = mods.find((m) => s.build.outputDir &&
          m.archive_path.startsWith(s.build.outputDir));
        const out = mine ? await Api.call("install_mod", mine.mod_id)
                         : { ok: false, error: "Build not found in library." };
        install.textContent = out.ok ? "Installed ✓" : "Failed";
        if (!out.ok) install.classList.add("err");
      } finally {
        install.disabled = false;
      }
    };
    const again = document.createElement("button");
    again.className = "secondary"; again.textContent = "Build another";
    again.onclick = () => store.set({
      save: null, npvName: "", outputDir: "",
      stepsDone: { source: false, appearance: false, build: false },
      build: { running: false, stages: {}, log: "", error: null, outputDir: null },
      screen: "source",
    });
    row.appendChild(install); row.appendChild(again);
    el.appendChild(row);
  },
};

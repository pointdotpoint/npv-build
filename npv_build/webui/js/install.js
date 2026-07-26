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

    const pmDeps = (s.appState && s.appState.photomode_deps) || {};
    const pmReady = Object.values(pmDeps).length > 0 &&
      Object.values(pmDeps).every(Boolean);
    const pmCard = document.createElement("div");
    pmCard.className = "card" + (pmReady ? "" : " error-card");
    pmCard.innerHTML =
      `<strong>Photo Mode ${pmReady ? "ready ✓" : "needs runtime dependencies"}</strong>` +
      `<div class="muted">The NPV archive includes its picker thumbnail, dedicated entity, ` +
      `poses, facial setup, and localization.</div>` +
      Object.entries(pmDeps).map(([name, ok]) =>
        `<div class="row"><span>${esc(name)}</span>` +
        `<span class="${ok ? "ok" : "err"}">${ok ? "✓ found" : "✗ missing"}</span></div>`
      ).join("");
    el.appendChild(pmCard);

    const zipCard = document.createElement("div");
    zipCard.className = "card zip-summary";
    zipCard.innerHTML = `<div class="muted">Reading mod zip…</div>`;
    el.appendChild(zipCard);
    if (s.build.outputDir) {
      Api.call("zip_info", s.build.outputDir).then((out) => {
        if (!out.ok) {
          zipCard.innerHTML = `<span class="err">${esc(out.error)}</span>`;
          return;
        }
        const mb = (out.zip.size / (1024 * 1024)).toFixed(1) + " MB";
        const name = out.zip.path.split(/[\\/]/).pop();
        zipCard.innerHTML =
          `<div class="row"><strong>${esc(name)}</strong>` +
          `<span class="muted">${esc(mb)}</span></div>` +
          out.zip.files.map((f) =>
            `<div class="row muted" style="font-size:12px">` +
            `<span>${esc(f.name)}</span><span>${(f.size / 1024).toFixed(0)} KB</span></div>`
          ).join("");
      });
    } else {
      zipCard.style.display = "none";
    }

    const row = document.createElement("div");
    row.className = "row"; row.style.marginTop = "16px";
    const install = document.createElement("button");
    install.textContent = "Install to game";
    install.onclick = async () => {
      install.disabled = true;
      try {
        const modsOut = await Api.call("list_mods");
        const mods = modsOut.ok ? modsOut.mods : [];
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
    const openBtn = document.createElement("button");
    openBtn.className = "secondary"; openBtn.textContent = "Open folder";
    openBtn.onclick = async () => {
      const out = await Api.call("open_folder", s.build.outputDir || "");
      if (!out.ok) { openBtn.textContent = "Failed"; openBtn.classList.add("err"); }
    };
    const again = document.createElement("button");
    again.className = "secondary"; again.textContent = "Build another";
    again.onclick = () => store.set({
      save: null, preset: null, npvName: "", outputDir: "",
      photomodeThumbnail: null,
      appearanceBusy: false,
      stepsDone: { source: false, appearance: false, build: false },
      build: { running: false, stages: {}, log: "", error: null, outputDir: null },
      screen: "source",
    });
    row.appendChild(install); row.appendChild(openBtn); row.appendChild(again);
    el.appendChild(row);
  },
};

"use strict";

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

window.screens = window.screens || {};
window.screens.source = {
  saves: null,
  async load() {
    this.saves = await Api.call("list_saves");
    store.set({});
  },
  render(el, s) {
    if (this.saves === null) {
      el.innerHTML = "<h1>Source</h1><p class='subtitle'>Scanning for saves…</p>";
      this.load();
      return;
    }
    el.innerHTML = "<h1>Source</h1>" +
      "<p class='subtitle'>Pick the save to turn into an NPC, or start from scratch.</p>";
    const list = document.createElement("div");
    for (const save of this.saves) {
      const card = document.createElement("div");
      card.className = "card selectable" +
        (s.save && s.save.path === save.path ? " selected" : "");
      const date = new Date(save.mtime * 1000).toLocaleString();
      card.innerHTML = `<div class="row"><strong>${esc(save.name)}</strong>` +
        `<span class="muted">${date}</span></div>` +
        `<div class="muted preview">…</div>`;
      card.onclick = () => this.pick(save, card);
      list.appendChild(card);
    }
    const scratch = document.createElement("div");
    scratch.className = "card";
    scratch.style.opacity = ".5";
    scratch.innerHTML = "<strong>From scratch</strong>" +
      "<div class='muted'>Start from the default V preset — coming soon.</div>";
    list.appendChild(scratch);
    el.appendChild(list);

    const form = document.createElement("div");
    form.innerHTML = `
      <label>NPV name (AMM spawn label)</label>
      <input type="text" id="npv-name" value="${esc(s.npvName || "")}">
      <label>Output directory</label>
      <input type="text" id="output-dir" value="${esc(s.outputDir || "")}">`;
    el.appendChild(form);

    const cont = document.createElement("button");
    cont.textContent = "Continue →";
    cont.style.marginTop = "16px";
    cont.disabled = !(s.save && s.save.preview && s.save.preview.ok);
    cont.onclick = () => {
      const npvName = document.getElementById("npv-name").value.trim();
      const outputDir = document.getElementById("output-dir").value.trim();
      if (!npvName || !outputDir) return;
      store.set({
        npvName, outputDir,
        stepsDone: { ...store.state.stepsDone, source: true },
        screen: "appearance",
      });
    };
    el.appendChild(cont);
  },
  async pick(save, card) {
    card.querySelector(".preview").textContent = "Parsing…";
    const preview = await Api.call("preview_save", save.path);
    if (!preview.ok) {
      store.set({ save: null });
      card.classList.add("error-card");
      card.querySelector(".preview").innerHTML =
        `<span class="err">${esc(preview.error)}</span>` +
        `<div class="remediation">${esc(preview.remediation)}</div>`;
      return;
    }
    const defaults = {};
    if (!store.state.npvName) defaults.npvName = save.name;
    if (!store.state.outputDir && store.state.appState.settings.output_dir)
      defaults.outputDir = store.state.appState.settings.output_dir + "/" + save.name;
    card.querySelector(".preview").textContent =
      `${preview.body_rig} · skin ${preview.skin_tone} · ${preview.hair_style}`;
    store.set({ save: { ...save, preview }, ...defaults });
  },
};

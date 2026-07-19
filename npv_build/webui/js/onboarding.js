"use strict";

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

window.screens = window.screens || {};
window.screens.onboarding = {
  _dirs: null,
  async load() {
    const out = await Api.call("detect_game_dirs");
    this._dirs = out.ok ? out.dirs : [];
    store.set({});
  },
  render(el, s) {
    el.innerHTML = "<h1>Welcome</h1>" +
      "<p class='subtitle'>Point npv-build at your Cyberpunk 2077 install. " +
      "Everything else is optional and lives in Settings.</p>";

    if (this._dirs === null) {
      el.innerHTML += "<p class='muted'>Looking for game installs…</p>";
      this.load();
      return;
    }

    const form = document.createElement("div");
    form.innerHTML = `
      <label>Cyberpunk 2077 game directory</label>
      <input type="text" id="onboard-game-dir" value="">`;
    const input = form.querySelector("#onboard-game-dir");

    if (this._dirs.length) {
      const found = document.createElement("div");
      for (const dir of this._dirs) {
        const card = document.createElement("div");
        card.className = "card selectable";
        card.innerHTML = `<strong>${esc(dir)}</strong>` +
          `<div class="muted">Detected install</div>`;
        card.onclick = () => {
          input.value = dir;
          [...found.children].forEach((c) => c.classList.remove("selected"));
          card.classList.add("selected");
        };
        found.appendChild(card);
      }
      el.appendChild(found);
    } else {
      const none = document.createElement("p");
      none.className = "muted";
      none.textContent =
        "No install detected automatically — enter the game folder below.";
      el.appendChild(none);
    }

    el.appendChild(form);

    const st = s.appState || { deps: {} };
    const deps = document.createElement("div");
    deps.className = "card";
    deps.style.marginTop = "16px";
    deps.innerHTML = Object.entries(st.deps)
      .filter(([name]) => name !== "game_dir_valid")
      .map(([name, ok]) =>
        `<div class="row"><span>${esc(name)}</span>` +
        `<span class="${ok ? "ok" : "err"}">${ok ? "✓ found" : "✗ will auto-install on first build"}</span></div>`
      ).join("");
    el.appendChild(deps);

    const err = document.createElement("p");
    err.className = "err";

    const cont = document.createElement("button");
    cont.textContent = "Save & continue";
    cont.style.marginTop = "16px";
    cont.onclick = async () => {
      const gameDir = input.value.trim();
      if (!gameDir) {
        err.textContent = "Game directory is required.";
        return;
      }
      cont.disabled = true;
      try {
        const out = await Api.call("save_config", { game_dir: gameDir });
        if (!out.ok) {
          err.textContent = out.errors.join("; ");
          return;
        }
        store.set({ appState: await Api.call("get_state"), screen: "source" });
      } finally {
        cont.disabled = false;
      }
    };
    el.appendChild(cont);
    el.appendChild(err);
  },
};

"use strict";

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

window.screens = window.screens || {};
window.screens.settings = {
  _draft: {},
  render(el, s) {
    const st = s.appState || { settings: {}, deps: {}, needs_onboarding: false };
    el.innerHTML = "<h1>Settings</h1>";

    if (st.needs_onboarding) {
      const banner = document.createElement("div");
      banner.className = "card";
      banner.innerHTML = "<strong>Welcome!</strong> " +
        "<span class='muted'>Point npv-build at your Cyberpunk 2077 install " +
        "to get started.</span>";
      el.appendChild(banner);
    }

    const deps = document.createElement("div");
    deps.className = "card";
    deps.innerHTML = Object.entries(st.deps).map(([name, ok]) =>
      `<div class="row"><span>${esc(name)}</span>` +
      `<span class="${ok ? "ok" : "err"}">${ok ? "✓ found" : "✗ missing"}</span></div>`
    ).join("");
    el.appendChild(deps);

    const form = document.createElement("div");
    form.innerHTML = `
      <label>Cyberpunk 2077 game directory</label>
      <input type="text" id="cfg-game-dir" value="${esc(this._draft.game_dir !== undefined ? this._draft.game_dir : (st.settings.game_dir || ""))}">
      <label>Default output directory</label>
      <input type="text" id="cfg-output-dir" value="${esc(this._draft.output_dir !== undefined ? this._draft.output_dir : (st.settings.output_dir || ""))}">`;
    el.appendChild(form);

    const gameDirInput = form.querySelector("#cfg-game-dir");
    const outputDirInput = form.querySelector("#cfg-output-dir");

    gameDirInput.addEventListener("input", (e) => {
      this._draft.game_dir = e.target.value;
    });

    outputDirInput.addEventListener("input", (e) => {
      this._draft.output_dir = e.target.value;
    });

    const err = document.createElement("p");
    err.className = "err";

    const save = document.createElement("button");
    save.textContent = "Save settings";
    save.style.marginTop = "16px";
    save.onclick = async () => {
      save.disabled = true;
      try {
        const out = await Api.call("save_config", {
          game_dir: gameDirInput.value.trim() || null,
          output_dir: outputDirInput.value.trim() || null,
        });
        if (!out.ok) {
          err.textContent = out.errors.join("; ");
          return;
        }
        this._draft = {};
        store.set({ appState: await Api.call("get_state") });
      } finally {
        save.disabled = false;
      }
    };

    el.appendChild(save);
    el.appendChild(err);
  },
};

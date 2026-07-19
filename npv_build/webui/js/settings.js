"use strict";

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function fmtSize(bytes) {
  if (bytes >= 1024 * 1024 * 1024) return (bytes / (1024 ** 3)).toFixed(1) + " GB";
  if (bytes >= 1024 * 1024) return (bytes / (1024 ** 2)).toFixed(1) + " MB";
  return Math.ceil(bytes / 1024) + " KB";
}

window.screens = window.screens || {};
window.screens.settings = {
  _draft: {},
  _cache: null,
  _installing: false,
  async loadCache() {
    const out = await Api.call("cache_info");
    this._cache = out.ok ? out.entries : [];
    store.set({});
  },
  render(el, s) {
    const st = s.appState || { settings: {}, deps: {}, tool_paths: {}, needs_onboarding: false };
    el.innerHTML = "<h1>Settings</h1>";

    if (st.needs_onboarding) {
      const banner = document.createElement("div");
      banner.className = "card";
      banner.innerHTML = "<strong>Welcome!</strong> " +
        "<span class='muted'>Point npv-build at your Cyberpunk 2077 install " +
        "to get started.</span>";
      el.appendChild(banner);
    }

    const toolPaths = st.tool_paths || {};
    const deps = document.createElement("div");
    deps.className = "card";
    deps.innerHTML = Object.entries(st.deps).map(([name, ok]) => {
      const path = toolPaths[name];
      return `<div class="row"><span>${esc(name)}` +
        (path ? `<div class="muted" style="font-size:11px">${esc(path)}</div>` : "") +
        `</span><span class="${ok ? "ok" : "err"}">${ok ? "✓ found" : "✗ missing"}</span></div>`;
    }).join("");
    el.appendChild(deps);

    const missingTools = Object.entries(st.deps)
      .some(([name, ok]) => !ok && name !== "game_dir_valid");
    if (missingTools || this._installing) {
      const installBtn = document.createElement("button");
      installBtn.className = "secondary";
      installBtn.id = "install-tools";
      installBtn.textContent = this._installing ? "Installing…" : "Install missing tools";
      installBtn.disabled = this._installing;
      const progress = document.createElement("div");
      progress.className = "muted tool-progress";
      progress.style.margin = "8px 0";
      installBtn.onclick = async () => {
        await Api.call("install_tools");
        this._installing = true;
        installBtn.disabled = true;
        installBtn.textContent = "Installing…";
        const timer = setInterval(async () => {
          const events = await Api.call("poll_tool_events");
          for (const ev of events) {
            if (ev.kind === "tool_progress") {
              progress.textContent = `${ev.message} (${ev.value}%)`;
            } else if (ev.kind === "tool_done" || ev.kind === "tool_error") {
              clearInterval(timer);
              this._installing = false;
              if (ev.kind === "tool_error") {
                progress.innerHTML = `<span class="err">${esc(ev.message)}</span>`;
              } else {
                store.set({ appState: await Api.call("get_state") });
              }
            }
          }
        }, 500);
      };
      el.appendChild(installBtn);
      el.appendChild(progress);
    }

    const form = document.createElement("div");
    const draftOr = (key) =>
      this._draft[key] !== undefined ? this._draft[key] : (st.settings[key] || "");
    form.innerHTML = `
      <label>Cyberpunk 2077 game directory</label>
      <input type="text" id="cfg-game-dir" value="${esc(draftOr("game_dir"))}">
      <label>Default output directory</label>
      <input type="text" id="cfg-output-dir" value="${esc(draftOr("output_dir"))}">
      <label>Clothing images directory (thumbnails for the clothing picker)</label>
      <input type="text" id="cfg-clothing-images-dir" value="${esc(draftOr("clothing_images_dir"))}">`;
    el.appendChild(form);

    const bind = (id, key) => {
      form.querySelector(id).addEventListener("input", (e) => {
        this._draft[key] = e.target.value;
      });
    };
    bind("#cfg-game-dir", "game_dir");
    bind("#cfg-output-dir", "output_dir");
    bind("#cfg-clothing-images-dir", "clothing_images_dir");

    const err = document.createElement("p");
    err.className = "err";

    const save = document.createElement("button");
    save.textContent = "Save settings";
    save.style.marginTop = "16px";
    save.onclick = async () => {
      save.disabled = true;
      try {
        const out = await Api.call("save_config", {
          game_dir: form.querySelector("#cfg-game-dir").value.trim() || null,
          output_dir: form.querySelector("#cfg-output-dir").value.trim() || null,
          clothing_images_dir:
            form.querySelector("#cfg-clothing-images-dir").value.trim() || null,
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

    const cacheCard = document.createElement("div");
    cacheCard.className = "card cache-card";
    cacheCard.style.marginTop = "24px";
    if (this._cache === null) {
      cacheCard.innerHTML = "<strong>Cache</strong><div class='muted'>Measuring…</div>";
      this.loadCache();
    } else {
      cacheCard.innerHTML = "<strong>Cache</strong>";
      for (const entry of this._cache) {
        const row = document.createElement("div");
        row.className = "row";
        row.style.margin = "6px 0";
        row.innerHTML = `<span>${esc(entry.name)} ` +
          `<span class="muted">${fmtSize(entry.size)}</span></span>`;
        if (entry.clearable) {
          const clear = document.createElement("button");
          clear.className = "secondary";
          clear.textContent = "Clear";
          clear.onclick = async () => {
            // tools are a large re-download: two-step confirm
            if (entry.name === "tools" && clear.textContent === "Clear") {
              clear.textContent = "Really clear?";
              clear.classList.add("err");
              return;
            }
            clear.disabled = true;
            const out = await Api.call("clear_cache", entry.name);
            if (!out.ok) { clear.textContent = "Failed"; return; }
            this.loadCache();
          };
          row.appendChild(clear);
        }
        cacheCard.appendChild(row);
      }
      if (!this._cache.length) {
        cacheCard.innerHTML += "<div class='muted'>Cache is empty.</div>";
      }
    }
    el.appendChild(cacheCard);
  },
};

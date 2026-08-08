"use strict";

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// What an NPV was built from. A from-scratch preset build legitimately looks
// like a default V; saying so on the card prevents that from reading as a bug.
function buildSource(mod) {
  if (mod.save_path) {
    const file = String(mod.save_path).split(/[\\/]/).filter(Boolean);
    const saveName = file.length > 1 ? file[file.length - 2] : mod.save_path;
    return `From save: ${saveName}`;
  }
  if (mod.preset_rig) {
    const body = mod.preset_rig === "pma" ? "male" : "female";
    return `From scratch: default ${body} V preset (${mod.preset_rig})`;
  }
  return "Source unknown (built by an older version)";
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
        `</div>` +
        // Which source this NPV came from. Without it a preset build and a
        // save build look identical on the card, so a default-looking preview
        // reads as a bug rather than as "this NPV really is a default V".
        `<div class="mod-source muted" style="font-size:12px;margin:-4px 0 8px">` +
        `${esc(buildSource(mod))}</div>`;
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

      const render = document.createElement("button");
      render.className = "secondary btn-render-preview";
      render.style.marginLeft = "8px";
      render.textContent = "Render preview";
      const previewArea = document.createElement("div");
      render.onclick = async () => {
        render.disabled = true;
        render.textContent = "Rendering…";
        previewArea.innerHTML = "";
        const updateProgress = async () => {
          try {
            const p = await Api.call("render_preview_progress", mod.output_dir);
            if (p.active && p.total) {
              render.textContent = `Rendering… ${p.current}/${p.total}`;
            }
          } catch (e) {
            /* progress is best-effort; the render call itself reports errors */
          }
        };
        updateProgress();
        const poll = setInterval(updateProgress, 1000);
        try {
          const out = await Api.call("render_npv_preview", mod.output_dir);
          if (out.ok) {
            if (out.skipped && out.skipped.length) {
              const warn = document.createElement("p");
              warn.className = "err";
              const names = out.skipped.map((s) => s.name).join(", ");
              warn.textContent =
                `Preview is incomplete: ${out.skipped.length} component(s) could not be ` +
                `rendered (${names}).`;
              previewArea.appendChild(warn);
            }
            const strip = document.createElement("div");
            strip.className = "preview-strip";
            for (const img of out.images) {
              const el = document.createElement("img");
              el.className = "preview-img";
              el.src = img.data_url;
              el.alt = img.view;
              strip.appendChild(el);
            }
            previewArea.appendChild(strip);
          } else {
            const err = document.createElement("p");
            err.className = "err";
            err.textContent = out.error + (out.remediation ? " — " + out.remediation : "");
            previewArea.appendChild(err);
          }
        } finally {
          clearInterval(poll);
          render.disabled = false;
          render.textContent = "Render preview";
        }
      };
      card.appendChild(render);

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
      card.appendChild(previewArea);
      grid.appendChild(card);
    }
    if (!this.mods.length) {
      grid.innerHTML = "<p class='muted'>Nothing built yet.</p>";
    }
    el.appendChild(grid);
  },
};

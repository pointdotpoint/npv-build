"use strict";

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

const GARMENT_SLOTS = [
  ["inner_torso", "Inner torso"],
  ["outer_torso", "Outer torso"],
  ["legs", "Legs"],
  ["feet", "Feet"],
];

window.screens = window.screens || {};
window.screens.appearance = {
  _data: null,
  _forSource: null,
  _overrides: {},
  _search: "",
  _hairModWarning: null,
  _hairModLoading: false,
  _thumbnailLoading: false,
  _thumbnailSource: null,
  _picker: null,
  _pickerSearchSerial: 0,
  async load(sourceKey, method, source) {
    this._forSource = sourceKey;
    const out = await Api.call(method, source);
    if (this._forSource !== sourceKey) return; // superseded by a newer source pick
    this._data = out;
    this._overrides = out.ok ? { ...out.overrides } : {};
    store.set({});
  },
  render(el, s) {
    const sourceKey = s.preset
      ? `preset:${s.preset.rig}`
      : s.save ? `save:${s.save.path}` : null;
    el.innerHTML = "<h1>Appearance</h1>" +
      `<p class='subtitle'>Adjust every resolved customization option. ` +
      `Overridden rows are marked; everything else builds exactly as ` +
      `${s.preset ? "the default preset" : "saved"}.</p>`;
    if (!sourceKey) {
      el.innerHTML += "<p class='muted'>Pick a source first.</p>";
      return;
    }

    if (this._forSource !== sourceKey) {
      // Selected source changed since we last loaded — reset and reload.
      this._data = null;
      this._overrides = {};
      this._hairModWarning = null;
      this._thumbnailSource = null;
      this.closeClothingPicker();
    }

    if (this._data === null) {
      el.innerHTML += "<p class='muted'>Decoding…</p>";
      if (s.preset) {
        this.load(sourceKey, "preset_appearance_data", s.preset.rig);
      } else {
        this.load(sourceKey, "appearance_data", s.save.path);
      }
      return;
    }
    if (!this._data.ok) {
      el.innerHTML += `<p class="err">${esc(this._data.error)}</p>`;
      return;
    }

    const formError = document.createElement("div");
    formError.className = "form-error err";
    formError.style.display = "none";
    formError.style.marginTop = "12px";
    const showFormError = (msg) => {
      formError.textContent = msg;
      formError.style.display = "";
    };
    if (this._hairModError) {
      showFormError(this._hairModError);
      this._hairModError = null;
    }

    const wrap = document.createElement("div");
    wrap.className = "inspector";

    const cats = document.createElement("div");
    cats.className = "inspector-cats";
    const categories = [...this._data.categories];
    if (!categories.includes("Clothing")) categories.push("Clothing");
    for (const cat of categories) {
      const rows = cat === "Clothing"
        ? GARMENT_SLOTS.map(([slot, label]) => ({
            slot_id: `garment_${slot}`, label,
          }))
        : this._data.rows.filter((r) => r.category === cat);
      let n = rows.filter((r) => r.slot_id in this._overrides).length;
      if (cat === "Hair" && "hair_mod" in this._overrides) n += 1;
      const div = document.createElement("div");
      div.className = "cat";
      const rowCount = rows.length + (cat === "Hair" ? 1 : 0);
      div.innerHTML = `<span>${esc(cat)}</span><span class="muted">${rowCount}</span>` +
        (n ? `<span class="badge override-count">${n}</span>` : "");
      cats.appendChild(div);
    }
    wrap.appendChild(cats);

    const right = document.createElement("div");
    const header = document.createElement("div");
    header.className = "row";
    const search = document.createElement("input");
    search.type = "text";
    search.id = "inspector-search";
    search.placeholder = "Search settings…";
    search.value = this._search;
    search.addEventListener("input", (e) => {
      this._search = e.target.value;
      store.set({});
    });
    header.appendChild(search);

    const reset = document.createElement("button");
    reset.id = "reset-all";
    reset.className = "secondary";
    reset.textContent = "Reset all";
    reset.disabled = this._hairModLoading;
    reset.onclick = () => {
      this._overrides = {};
      this._hairModWarning = null;
      store.set({});
    };
    header.appendChild(reset);
    right.appendChild(header);

    const rowsEl = document.createElement("div");
    rowsEl.className = "inspector-rows";
    const q = this._search.toLowerCase();
    for (const row of this._data.rows) {
      if (q && !(row.label + row.value_label).toLowerCase().includes(q)) continue;
      const overridden = row.slot_id in this._overrides;
      const div = document.createElement("div");
      div.className = "irow" + (overridden ? " overridden" : "");
      div.innerHTML = `<span>${esc(row.label)}</span>`;
      if (row.editable) {
        const sel = document.createElement("select");
        const optionValues = [];
        for (const opt of row.options) {
          const value = typeof opt === "object" ? opt.value : opt;
          const label = typeof opt === "object" ? opt.label : opt;
          const o = document.createElement("option");
          o.value = value; o.textContent = label;
          sel.appendChild(o);
          optionValues.push(value);
        }
        if (!optionValues.includes(row.value_raw)) {
          const o = document.createElement("option");
          o.value = row.value_raw;
          o.textContent = row.value_label + " (current)";
          sel.appendChild(o);
        }
        sel.value = overridden ? this._overrides[row.slot_id] : row.value_raw;
        sel.disabled = this._hairModLoading;
        sel.onchange = () => {
          if (sel.value === row.value_raw) delete this._overrides[row.slot_id];
          else this._overrides[row.slot_id] = sel.value;
          if (row.slot_id === "hair_style") {
            // Vanilla hair style and a modded hair file are mutually exclusive.
            delete this._overrides.hair_mod;
            this._hairModWarning = null;
          }
          store.set({});
        };
        div.appendChild(sel);
        if (overridden) {
          const rv = document.createElement("button");
          rv.className = "secondary revert"; rv.textContent = "↺";
          rv.title = "Revert to the save's value";
          rv.disabled = this._hairModLoading;
          rv.onclick = () => { delete this._overrides[row.slot_id]; store.set({}); };
          div.appendChild(rv);
        }
      } else {
        div.innerHTML += `<span class="muted" title="Not editable yet">` +
          `${esc(row.value_label)} 🔒</span>`;
      }
      rowsEl.appendChild(div);
    }

    // Modded hair row — appended to the Hair category, not part of the
    // backend's inspector_rows (mirrors clothing's row-append pattern).
    const savedHair = this._data.saved_hair &&
      !("hair_style" in this._overrides)
      ? this._data.saved_hair
      : null;
    const currentHairToken = this._overrides.hair_mod ||
      (savedHair && savedHair.selection_label) || "";
    if (!q || "modded hair saved hair".includes(q) ||
        currentHairToken.toLowerCase().includes(q)) {
      const hairOverridden = "hair_mod" in this._overrides;
      const hrow = document.createElement("div");
      hrow.className = "irow hair-mod-row"
        + (hairOverridden ? " overridden" : "")
        + (savedHair && savedHair.state === "registered" ? " saved-loaded" : "")
        + (this._hairModLoading ? " loading" : "");
      hrow.setAttribute("aria-busy", String(this._hairModLoading));
      if (this._hairModLoading) {
        hrow.innerHTML = `<span>Modded hair</span><span class="hair-loading-value">` +
          `<span class="hair-spinner" aria-hidden="true"></span>Loading…</span>`;
      } else {
        hrow.innerHTML = `<span>Modded hair</span>` +
          `<span>${esc(currentHairToken || "—")}</span>`;
      }

      const browseBtn = document.createElement("button");
      browseBtn.className = "secondary browse-hair-mod";
      browseBtn.textContent = this._hairModLoading
        ? "Loading hair…"
        : (currentHairToken ? "Replace hair…" : "Use hair mod file…");
      browseBtn.disabled = this._hairModLoading;
      browseBtn.onclick = () => {
        const rig = s.preset
          ? s.preset.rig
          : (s.save.preview && s.save.preview.body_rig) || "pwa";
        this.loadHairMod("browse_for_hair_mod", rig);
      };
      hrow.appendChild(browseBtn);

      if (hairOverridden) {
        const rv = document.createElement("button");
        rv.className = "secondary revert"; rv.textContent = "↺";
        rv.title = "Revert to the save's value";
        rv.disabled = this._hairModLoading;
        rv.onclick = () => {
          delete this._overrides.hair_mod;
          this._hairModWarning = null;
          store.set({});
        };
        hrow.appendChild(rv);
      }
      rowsEl.appendChild(hrow);

      if (this._hairModLoading) {
        const note = document.createElement("div");
        note.className = "hair-mod-status";
        note.setAttribute("role", "status");
        note.setAttribute("aria-live", "polite");
        note.innerHTML = `<strong>Loading and validating the hair mod…</strong>` +
          `<span>Scanning installed archives can take several minutes. ` +
          `You can continue when this finishes.</span>`;
        rowsEl.appendChild(note);
      } else if (this._hairModWarning) {
        const note = document.createElement("div");
        note.className = "hair-mod-status loaded";
        note.innerHTML = `<strong>✓ Hair loaded and validated.</strong>` +
          `<span>${esc(this._hairModWarning)}</span>`;
        rowsEl.appendChild(note);
      } else if (savedHair && savedHair.state === "registered") {
        const note = document.createElement("div");
        note.className = "hair-mod-status loaded";
        note.innerHTML = `<strong>✓ Saved hair is installed and registered.</strong>` +
          `<span>${esc(savedHair.source)} · ${esc(savedHair.mesh_appearance || "default")}</span>` +
          `<span class="hair-depot">${esc(savedHair.depot)}</span>`;
        rowsEl.appendChild(note);
      } else if (savedHair) {
        const note = document.createElement("div");
        note.className = "hair-mod-status";
        note.innerHTML = `<strong>Saved modded hair requires its supplying mod.</strong>` +
          `<span>Registration was not verified yet. The build will stop if ` +
          `${esc(savedHair.selection_label)} cannot be resolved.</span>`;
        rowsEl.appendChild(note);
      } else {
        const note = document.createElement("div");
        note.className = "muted hair-mod-note";
        note.textContent = "Hair mods are loaded and validated before use. " +
          "Large mod folders may take several minutes to scan.";
        rowsEl.appendChild(note);
      }
    }

    const rig = s.preset
      ? s.preset.rig
      : (s.save.preview && s.save.preview.body_rig) || "pwa";
    for (const [slot, label] of GARMENT_SLOTS) {
      const slotId = `garment_${slot}`;
      const fallback = (this._data.garments || {})[slot] || "None";
      const selection = this._overrides[slotId];
      const legacySelection = typeof selection === "string";
      const current = selection && typeof selection === "object"
        ? selection.name
        : legacySelection
          ? String(selection).replaceAll("\\", "/").split("/").pop()
            .replace(/\.mesh$/i, "")
          : fallback;
      if (q && !(label + current + "clothing garment").toLowerCase().includes(q)) continue;
      const overridden = slotId in this._overrides;
      const grow = document.createElement("div");
      grow.className = "irow garment-row" + (overridden ? " overridden" : "")
        + (legacySelection ? " garment-legacy" : "");
      const variant = selection && typeof selection === "object"
        ? `<small>${esc(selection.appearance || "validated variant")}</small>`
        : legacySelection
          ? `<small class="garment-warning">Variant unknown — reselect this garment</small>`
          : "";
      grow.innerHTML = `<span>${esc(label)}</span>` +
        `<span class="garment-value">${esc(current)}${variant}</span>`;

      const browse = document.createElement("button");
      browse.className = "secondary browse-garment";
      browse.textContent = "Browse…";
      browse.onclick = () => this.openClothingPicker(slot, label, rig);
      grow.appendChild(browse);
      if (overridden) {
        const rv = document.createElement("button");
        rv.className = "secondary revert";
        rv.textContent = "↺";
        rv.title = "Revert to the current outfit";
        rv.onclick = () => {
          delete this._overrides[slotId];
          store.set({});
        };
        grow.appendChild(rv);
      }
      rowsEl.appendChild(grow);
    }

    right.appendChild(rowsEl);
    wrap.appendChild(right);
    el.appendChild(wrap);

    const thumbnail = document.createElement("div");
    thumbnail.className = "card photomode-thumbnail" +
      (s.photomodeThumbnail ? " loaded" : " required");
    const preview = s.photomodeThumbnail && s.photomodeThumbnail.preview
      ? `<img src="${s.photomodeThumbnail.preview}" alt="Photo Mode NPC picker preview">`
      : `<div class="photomode-placeholder">200 × 200</div>`;
    thumbnail.innerHTML = `
      <div>${preview}</div>
      <div class="photomode-thumbnail-copy">
        <strong>Photo Mode NPC thumbnail <span class="required-mark">Required</span></strong>
        <span class="muted">${s.photomodeThumbnail
          ? esc(`${s.photomodeThumbnail.name} · ${s.photomodeThumbnail.width}×${s.photomodeThumbnail.height}`)
          : "Choose the portrait shown in the in-game Photo Mode NPC picker."}</span>
        <span class="muted">PNG, JPEG, or WebP · minimum 200×200 · centered square crop</span>
      </div>`;
    const thumbBrowse = document.createElement("button");
    thumbBrowse.className = "secondary";
    thumbBrowse.textContent = this._thumbnailLoading
      ? "Loading…"
      : (s.photomodeThumbnail ? "Replace…" : "Choose image…");
    thumbBrowse.disabled = this._thumbnailLoading;
    thumbBrowse.onclick = () => this.loadThumbnail("browse_for_photomode_thumbnail");
    thumbnail.appendChild(thumbBrowse);
    el.appendChild(thumbnail);

    // A save screenshot is the best default; users can replace it before
    // continuing. From-scratch presets intentionally require an explicit pick.
    if (!s.photomodeThumbnail && s.save && s.save.thumbnail &&
        this._thumbnailSource !== sourceKey && !this._thumbnailLoading) {
      this._thumbnailSource = sourceKey;
      this.loadThumbnail("add_photomode_thumbnail", s.save.thumbnail);
    }

    // Drag & drop supports both appearance dependencies and the required
    // Photo Mode portrait. Full paths are exposed by the desktop shell.
    el.ondragover = (e) => e.preventDefault();
    el.ondrop = (e) => {
      e.preventDefault();
      if (this._hairModLoading) return;
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      const path = f && (f.pywebviewFullPath || f.path);
      if (!path) {
        showFormError("Drag & drop needs the desktop app — use the file browser instead.");
        return;
      }
      if (/\.(png|jpe?g|webp)$/i.test(path)) {
        this.loadThumbnail("add_photomode_thumbnail", path);
        return;
      }
      const rig = s.preset
        ? s.preset.rig
        : (s.save.preview && s.save.preview.body_rig) || "pwa";
      this.loadHairMod("add_hair_mod", path, rig);
    };

    const form = document.createElement("div");
    form.innerHTML = `
      <label>NPV name (AMM spawn label)</label>
      <input type="text" id="npv-name" value="${esc(s.npvName || "")}">
      <label>Output directory</label>
      <input type="text" id="output-dir" value="${esc(s.outputDir || "")}">`;
    el.appendChild(form);

    form.querySelector("#npv-name").addEventListener("input", (e) => {
      store.state.npvName = e.target.value;
    });
    form.querySelector("#output-dir").addEventListener("input", (e) => {
      store.state.outputDir = e.target.value;
    });

    el.appendChild(formError);

    const cont = document.createElement("button");
    const hasLegacyGarment = Object.entries(this._overrides).some(
      ([key, value]) => key.startsWith("garment_") && typeof value === "string"
    );
    cont.textContent = this._hairModLoading
      ? "Waiting for hair to load…"
      : hasLegacyGarment
        ? "Reselect garment to continue"
        : "Continue →";
    cont.disabled = this._hairModLoading || hasLegacyGarment;
    if (this._hairModLoading) {
      cont.title = "The hair mod must finish loading and validation first.";
    } else if (hasLegacyGarment) {
      cont.title = "A previous mesh-only choice has no exact material variant.";
    }
    cont.style.marginTop = "16px";
    cont.onclick = async () => {
      const npvName = document.getElementById("npv-name").value.trim();
      const outputDir = document.getElementById("output-dir").value.trim();
      const missing = [];
      if (!npvName) missing.push("NPV name");
      if (!outputDir) missing.push("Output directory");
      if (!store.state.photomodeThumbnail) missing.push("Photo Mode thumbnail");
      if (missing.length) {
        showFormError(missing.join(" and ") +
          (missing.length > 1 ? " are" : " is") + " required.");
        return;
      }
      if (s.preset) {
        store.state.preset = {
          ...s.preset,
          overrides: { ...this._overrides },
        };
      } else {
        const out = await Api.call("set_overrides", s.save.path, this._overrides);
        if (!out.ok) {
          showFormError(out.error);
          return;
        }
      }
      store.set({
        npvName, outputDir,
        stepsDone: { ...store.state.stepsDone, appearance: true },
        screen: "build",
      });
    };
    el.appendChild(cont);
  },
  closeClothingPicker() {
    if (!this._picker) return;
    document.removeEventListener("keydown", this._picker.onKey);
    this._picker.overlay.remove();
    this._picker = null;
  },
  _newPicker(title) {
    this.closeClothingPicker();
    const overlay = document.createElement("div");
    overlay.className = "picker";
    overlay.setAttribute("role", "presentation");
    const dialog = document.createElement("section");
    dialog.className = "picker-dialog";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-label", title);
    const head = document.createElement("div");
    head.className = "picker-head";
    head.innerHTML = `<div><strong>${esc(title)}</strong>` +
      `<div class="muted">Only archive-validated items can be selected.</div></div>`;
    const close = document.createElement("button");
    close.className = "secondary picker-close";
    close.textContent = "Close";
    close.onclick = () => this.closeClothingPicker();
    head.appendChild(close);
    dialog.appendChild(head);
    overlay.appendChild(dialog);
    overlay.onclick = (event) => {
      if (event.target === overlay) this.closeClothingPicker();
    };
    const onKey = (event) => {
      if (event.key === "Escape") this.closeClothingPicker();
    };
    document.addEventListener("keydown", onKey);
    document.body.appendChild(overlay);
    this._picker = { overlay, dialog, onKey };
    return dialog;
  },
  async openClothingPicker(slot, label, rig) {
    const dialog = this._newPicker(`${label} clothing`);
    const loading = document.createElement("p");
    loading.className = "muted picker-loading";
    loading.textContent = "Checking clothing catalog…";
    dialog.appendChild(loading);
    let status;
    try {
      status = await Api.call("clothing_catalog_status");
    } catch (error) {
      status = { ok: false, error: error.message || "Could not check the catalog." };
    }
    if (!this._picker || this._picker.dialog !== dialog) return;
    loading.remove();
    if (!status.ok) {
      this._renderCatalogError(dialog, status.error || "Could not check the catalog.");
      return;
    }
    if (!status.built) {
      this._renderCatalogBuildPrompt(dialog, slot, label, rig);
      return;
    }
    this._renderCatalogSearch(dialog, slot, rig);
  },
  _renderCatalogError(dialog, message) {
    const error = document.createElement("div");
    error.className = "card error-card picker-error";
    error.textContent = message;
    dialog.appendChild(error);
  },
  _renderCatalogBuildPrompt(dialog, slot, label, rig) {
    const prompt = document.createElement("div");
    prompt.className = "catalog-build-prompt";
    prompt.innerHTML = `<strong>Build the vanilla clothing catalog</strong>` +
      `<p class="muted">NPV Build needs to index your installed game once. ` +
      `The result is cached; no game assets are copied.</p>`;
    const progress = document.createElement("div");
    progress.className = "muted catalog-build-progress";
    const build = document.createElement("button");
    build.className = "build-clothing-catalog";
    build.textContent = "Build catalog";
    build.onclick = async () => {
      build.disabled = true;
      build.textContent = "Building…";
      const out = await Api.call("build_clothing_catalog");
      if (!out.ok) {
        build.disabled = false;
        build.textContent = "Retry";
        progress.className = "err catalog-build-progress";
        progress.textContent = out.error || "Catalog build failed.";
        return;
      }
      const poll = async () => {
        if (!this._picker || this._picker.dialog !== dialog) return;
        const events = await Api.call("poll_catalog_events");
        for (const event of events) {
          if (event.kind === "catalog_progress") {
            progress.textContent = event.message || "Indexing…";
          } else if (event.kind === "catalog_error") {
            build.disabled = false;
            build.textContent = "Retry";
            progress.className = "err catalog-build-progress";
            progress.textContent = event.message || "Catalog build failed.";
            return;
          } else if (event.kind === "catalog_done") {
            dialog.querySelector(".catalog-build-prompt").remove();
            this._renderCatalogSearch(dialog, slot, rig);
            return;
          }
        }
        setTimeout(poll, 200);
      };
      poll();
    };
    prompt.appendChild(build);
    prompt.appendChild(progress);
    dialog.appendChild(prompt);
  },
  _renderCatalogSearch(dialog, slot, rig) {
    const input = document.createElement("input");
    input.type = "text";
    input.id = "picker-search";
    input.placeholder = "Search vanilla clothing…";
    const grid = document.createElement("div");
    grid.className = "picker-grid";
    dialog.appendChild(input);
    dialog.appendChild(grid);
    let debounce = null;
    const search = async () => {
      const serial = ++this._pickerSearchSerial;
      grid.innerHTML = `<p class="muted">Searching…</p>`;
      const out = await Api.call("clothing_search", input.value, slot, rig, 100);
      if (!this._picker || this._picker.dialog !== dialog ||
          serial !== this._pickerSearchSerial) return;
      if (!out.ok) {
        grid.innerHTML = `<p class="err">${esc(out.error || "Search failed.")}</p>`;
        return;
      }
      grid.innerHTML = "";
      if (!out.items.length) {
        grid.innerHTML = `<p class="muted">No clothing matches this search.</p>`;
        return;
      }
      for (const item of out.items) {
        const cell = document.createElement("button");
        cell.className = "picker-item" + (item.buildable ? "" : " disabled");
        cell.type = "button";
        cell.disabled = !item.buildable;
        cell.title = item.buildable ? item.name : "not available for NPCs";
        const image = document.createElement("div");
        image.className = "picker-thumb";
        image.textContent = "No image";
        const name = document.createElement("span");
        name.textContent = item.name;
        cell.appendChild(image);
        cell.appendChild(name);
        if (!item.buildable) {
          const unavailable = document.createElement("small");
          unavailable.textContent = "Not available for NPCs";
          cell.appendChild(unavailable);
        } else {
          if (item.appearance) {
            const variant = document.createElement("small");
            variant.textContent = item.appearance;
            cell.appendChild(variant);
          }
          cell.onclick = () => {
            const slotId = `garment_${slot}`;
            this._overrides[slotId] = item.selection;
            this.closeClothingPicker();
            store.set({});
          };
        }
        grid.appendChild(cell);
        if (item.image) {
          Api.call("clothing_thumb", item.image).then((thumb) => {
            if (!thumb.ok || !thumb.b64 || !cell.isConnected) return;
            image.textContent = "";
            const img = document.createElement("img");
            img.src = `data:image/jpeg;base64,${thumb.b64}`;
            img.alt = "";
            image.appendChild(img);
          }).catch(() => {});
        }
      }
    };
    input.addEventListener("input", () => {
      clearTimeout(debounce);
      debounce = setTimeout(search, 150);
    });
    search();
    input.focus();
  },
  async loadThumbnail(method, ...args) {
    if (this._thumbnailLoading) return;
    this._thumbnailLoading = true;
    store.set({});
    try {
      const out = await Api.call(method, ...args);
      if (out.cancelled) return;
      if (!out.ok) {
        this._hairModError = out.error + (out.remediation ? ` ${out.remediation}` : "");
        return;
      }
      store.set({ photomodeThumbnail: out.thumbnail });
    } catch (error) {
      this._hairModError = error && error.message
        ? error.message
        : "Could not load the Photo Mode thumbnail.";
    } finally {
      this._thumbnailLoading = false;
      store.set({});
    }
  },
  async loadHairMod(method, ...args) {
    if (this._hairModLoading) return;
    this._hairModLoading = true;
    this._hairModError = null;
    store.set({ appearanceBusy: true });
    try {
      const out = await Api.call(method, ...args);
      if (!out.cancelled) this.applyHairMod(out);
    } catch (error) {
      this._hairModError = error && error.message
        ? error.message
        : "Could not load the hair mod.";
    } finally {
      this._hairModLoading = false;
      store.set({ appearanceBusy: false });
    }
  },
  applyHairMod(out) {
    if (!out.ok) {
      this._hairModError = out.error;
      return;
    }
    this._overrides.hair_mod = out.token;
    delete this._overrides.hair_style;
    this._hairModWarning = out.warning || null;
  },
};

"use strict";

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

window.screens = window.screens || {};
window.screens.appearance = {
  _data: null,
  _forPath: null,
  _overrides: {},
  _search: "",
  _hairModWarning: null,
  async load(savePath) {
    this._forPath = savePath;
    const out = await Api.call("appearance_data", savePath);
    if (this._forPath !== savePath) return; // superseded by a newer save pick
    this._data = out;
    this._overrides = out.ok ? { ...out.overrides } : {};
    store.set({});
  },
  render(el, s) {
    el.innerHTML = "<h1>Appearance</h1>" +
      "<p class='subtitle'>Adjust the decoded appearance. Overridden rows " +
      "are marked; everything else builds exactly as saved.</p>";
    if (!s.save) { el.innerHTML += "<p class='muted'>Pick a save first.</p>"; return; }

    if (this._forPath !== s.save.path) {
      // Selected save changed since we last loaded — reset and reload.
      this._data = null;
      this._overrides = {};
      this._hairModWarning = null;
    }

    if (this._data === null) {
      el.innerHTML += "<p class='muted'>Decoding…</p>";
      this.load(s.save.path);
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
    for (const cat of this._data.categories) {
      const rows = this._data.rows.filter((r) => r.category === cat);
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
        for (const opt of row.options) {
          const o = document.createElement("option");
          o.value = opt; o.textContent = opt;
          sel.appendChild(o);
        }
        if (!row.options.includes(row.value_raw)) {
          const o = document.createElement("option");
          o.value = row.value_raw; o.textContent = row.value_raw + " (current)";
          sel.appendChild(o);
        }
        sel.value = overridden ? this._overrides[row.slot_id] : row.value_raw;
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
    if (!q || "modded hair".includes(q) ||
        (this._overrides.hair_mod || "").toLowerCase().includes(q)) {
      const hairOverridden = "hair_mod" in this._overrides;
      const hrow = document.createElement("div");
      hrow.className = "irow hair-mod-row" + (hairOverridden ? " overridden" : "");
      const valueLabel = this._overrides.hair_mod || "—";
      hrow.innerHTML = `<span>Modded hair</span><span>${esc(valueLabel)}</span>`;

      const browseBtn = document.createElement("button");
      browseBtn.className = "secondary browse-hair-mod";
      browseBtn.textContent = "Use hair mod file…";
      browseBtn.onclick = async () => {
        const out = await Api.call("browse_for_hair_mod");
        this.applyHairMod(out);
        store.set({});
      };
      hrow.appendChild(browseBtn);

      if (hairOverridden) {
        const rv = document.createElement("button");
        rv.className = "secondary revert"; rv.textContent = "↺";
        rv.title = "Revert to the save's value";
        rv.onclick = () => {
          delete this._overrides.hair_mod;
          this._hairModWarning = null;
          store.set({});
        };
        hrow.appendChild(rv);
      }
      rowsEl.appendChild(hrow);

      if (this._hairModWarning) {
        const note = document.createElement("div");
        note.className = "muted hair-mod-note";
        note.textContent = this._hairModWarning;
        rowsEl.appendChild(note);
      }
    }

    right.appendChild(rowsEl);
    wrap.appendChild(right);
    el.appendChild(wrap);

    // Drag & drop a hair mod file anywhere on the screen (mirrors Source's
    // drop handler). Full paths are only exposed by the pywebview shell.
    el.ondragover = (e) => e.preventDefault();
    el.ondrop = async (e) => {
      e.preventDefault();
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      const path = f && (f.pywebviewFullPath || f.path);
      if (!path) {
        showFormError("Drag & drop needs the desktop app — use the file browser instead.");
        return;
      }
      const out = await Api.call("add_hair_mod", path, s.save.preview.body_rig);
      this.applyHairMod(out);
      store.set({});
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
    cont.textContent = "Continue →";
    cont.style.marginTop = "16px";
    cont.onclick = async () => {
      const npvName = document.getElementById("npv-name").value.trim();
      const outputDir = document.getElementById("output-dir").value.trim();
      const missing = [];
      if (!npvName) missing.push("NPV name");
      if (!outputDir) missing.push("Output directory");
      if (missing.length) {
        showFormError(missing.join(" and ") +
          (missing.length > 1 ? " are" : " is") + " required.");
        return;
      }
      const out = await Api.call("set_overrides", s.save.path, this._overrides);
      if (!out.ok) {
        showFormError(out.error);
        return;
      }
      store.set({
        npvName, outputDir,
        stepsDone: { ...store.state.stepsDone, appearance: true },
        screen: "build",
      });
    };
    el.appendChild(cont);
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

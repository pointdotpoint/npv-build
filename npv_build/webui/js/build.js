"use strict";

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

window.screens = window.screens || {};
const STAGE_DEFS = [
  ["parse_save", "Parse save"], ["resolve_assets", "Resolve assets"],
  ["assemble", "Assemble mod"], ["emit_amm_lua", "AMM script"],
  ["emit_photomode", "Photo Mode files"], ["package", "Package zip"],
];
window.screens.build = {
  timer: null,
  _polling: false,
  _ticks: 0,
  starts: {},
  async start(resume) {
    if (this.timer) clearInterval(this.timer);
    this._logPinned = true;
    const s = store.state;
    store.set({ build: { running: true, stages: {}, log: "", error: null,
                         outputDir: null, progress: 0 } });
    this.starts = {};
    const source = s.preset
      ? { preset_rig: s.preset.rig }
      : { save_path: s.save.path };
    const out = await Api.call("start_build", {
      ...source, npv_name: s.npvName, output_dir: s.outputDir,
      clear_cache: false, resume: !!resume,
    });
    if (!out.ok) {
      store.set({ build: { ...store.state.build, running: false,
                           error: out.error + "\n" + (out.remediation || "") } });
      return;
    }
    this.timer = setInterval(() => this.poll(), 200);
  },
  async poll() {
    if (this._polling) return;
    this._polling = true;
    try {
      const events = await Api.call("poll_events");
      if (!events.length) {
        // No pipeline events, but keep the elapsed-time display ticking
        // (~1s) for any stage that is still running.
        if (store.state.build.running && ++this._ticks >= 5) {
          this._ticks = 0;
          store.set({});
        }
        return;
      }
      this._ticks = 0;
      const b = { ...store.state.build };
      for (const ev of events) {
        if (ev.kind === "log") b.log += ev.text;
        else if (ev.kind === "progress") b.progress = Math.max(0, Math.min(1, ev.value));
        else if (ev.kind === "stage") {
          if (ev.status === "started") this.starts[ev.stage] = Date.now();
          const secs = this.starts[ev.stage]
            ? ((Date.now() - this.starts[ev.stage]) / 1000).toFixed(0) + "s" : "";
          b.stages = { ...b.stages,
            [ev.stage]: { status: ev.status, message: ev.message, time: secs } };
        } else if (ev.kind === "done") {
          b.running = false; b.outputDir = ev.output_dir;
          clearInterval(this.timer);
          store.set({ build: b,
            stepsDone: { ...store.state.stepsDone, build: true },
            screen: "install" });
          return;
        } else if (ev.kind === "error") {
          b.running = false; b.error = ev.message;
          clearInterval(this.timer);
        }
      }
      store.set({ build: b });
    } finally {
      this._polling = false;
    }
  },
  render(el, s) {
    const b = s.build;
    el.innerHTML = `<h1>Build</h1><p class="subtitle">Building "${esc(s.npvName)}"</p>`;
    const grid = document.createElement("div");
    grid.className = "build-grid";
    const left = document.createElement("div");
    for (const [key, label] of STAGE_DEFS) {
      const st = (b.stages || {})[key];
      if (st && st.status === "started" && this.starts[key])
        st.time = ((Date.now() - this.starts[key]) / 1000).toFixed(0) + "s";
      const cls = !st ? "pending"
        : st.status === "started" ? "running"
        : st.status === "failed" ? "failed"
        : st.status;  // completed | skipped
      const mark = { pending: "○", running: "●", completed: "✓",
                     skipped: "✓", failed: "✗" }[cls];
      const div = document.createElement("div");
      div.className = "stage " + cls;
      div.innerHTML = `${mark} ${label}<span class="time">${st ? st.time : ""}</span>` +
        (st && st.status === "started"
          ? `<div class="progress"><div style="width:${(b.progress * 100) | 0}%"></div></div>
             <div class="muted" style="font-size:12px">${esc(st.message || "")}</div>` : "") +
        (st && st.status === "failed"
          ? `<div class="err" style="font-size:12px">${esc(st.message || "")}</div>` : "");
      left.appendChild(div);
    }
    if (b.error) {
      const errCard = document.createElement("div");
      errCard.className = "card error-card";
      errCard.innerHTML = `<span class="err">${esc(b.error || "")}</span>`;
      left.appendChild(errCard);
      const retry = document.createElement("button");
      retry.textContent = "Retry from failed stage";
      retry.onclick = () => this.start(true);
      left.appendChild(retry);
    } else if (b.running) {
      const cancel = document.createElement("button");
      cancel.className = "secondary"; cancel.textContent = "Cancel";
      cancel.onclick = () => Api.call("cancel_build");
      left.appendChild(cancel);
    } else if (!b.outputDir) {
      const startBtn = document.createElement("button");
      startBtn.textContent = "Start build";
      startBtn.onclick = () => this.start(false);
      left.appendChild(startBtn);
    }
    const logWrap = document.createElement("div");
    logWrap.className = "log-wrap";
    const copy = document.createElement("button");
    copy.className = "secondary log-copy";
    copy.textContent = "Copy log";
    copy.onclick = async () => {
      try {
        await navigator.clipboard.writeText(store.state.build.log || "");
        copy.textContent = "Copied ✓";
        setTimeout(() => { copy.textContent = "Copy log"; }, 1500);
      } catch {
        copy.textContent = "Copy failed";
      }
    };
    const log = document.createElement("div");
    log.className = "log"; log.textContent = b.log || "";
    logWrap.appendChild(log); logWrap.appendChild(copy);
    grid.appendChild(left); grid.appendChild(logWrap);
    el.appendChild(grid);
    // Auto-scroll only while the user is pinned to the bottom; scrolling up
    // pauses it, scrolling back down resumes it.
    log.onscroll = () => {
      this._logPinned = log.scrollTop + log.clientHeight >= log.scrollHeight - 4;
      if (!this._logPinned) this._logScrollTop = log.scrollTop;
    };
    if (this._logPinned === false) log.scrollTop = this._logScrollTop || 0;
    else log.scrollTop = log.scrollHeight;
  },
};

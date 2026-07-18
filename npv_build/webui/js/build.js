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
  starts: {},
  async start(resume) {
    if (this.timer) clearInterval(this.timer);
    const s = store.state;
    store.set({ build: { running: true, stages: {}, log: "", error: null,
                         outputDir: null, progress: 0 } });
    this.starts = {};
    const out = await Api.call("start_build", {
      save_path: s.save.path, npv_name: s.npvName, output_dir: s.outputDir,
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
      if (!events.length) return;
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
    const log = document.createElement("div");
    log.className = "log"; log.textContent = b.log || "";
    grid.appendChild(left); grid.appendChild(log);
    el.appendChild(grid);
    log.scrollTop = log.scrollHeight;
  },
};

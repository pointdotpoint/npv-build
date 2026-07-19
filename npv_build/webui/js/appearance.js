"use strict";

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

window.screens = window.screens || {};
window.screens.appearance = {
  render(el, s) {
    const p = s.save ? s.save.preview : null;
    el.innerHTML = "<h1>Appearance</h1>" +
      "<p class='subtitle'>Full inspector with overrides arrives in the next milestone. " +
      "Review the decoded summary below.</p>";
    if (p) {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML =
        `<div class="row"><span>Body rig</span><strong>${esc(p.body_rig)}</strong></div>` +
        `<div class="row"><span>Skin tone</span><strong>${esc(p.skin_tone)}</strong></div>` +
        `<div class="row"><span>Hair</span><strong>${esc(p.hair_style)} (${esc(p.hair_color)})</strong></div>` +
        `<div class="row"><span>Decoded selections</span><strong>${esc(p.selections_count)}</strong></div>`;
      el.appendChild(card);
    }
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

    const formError = document.createElement("div");
    formError.className = "form-error err";
    formError.style.display = "none";
    formError.style.marginTop = "12px";
    el.appendChild(formError);

    const cont = document.createElement("button");
    cont.textContent = "Continue →";
    cont.style.marginTop = "16px";
    cont.onclick = () => {
      const npvName = document.getElementById("npv-name").value.trim();
      const outputDir = document.getElementById("output-dir").value.trim();
      const missing = [];
      if (!npvName) missing.push("NPV name");
      if (!outputDir) missing.push("Output directory");
      if (missing.length) {
        formError.textContent = missing.join(" and ") +
          (missing.length > 1 ? " are" : " is") + " required.";
        formError.style.display = "";
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
};

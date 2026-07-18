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
    const cont = document.createElement("button");
    cont.textContent = "Continue →";
    cont.onclick = () => store.set({
      stepsDone: { ...store.state.stepsDone, appearance: true },
      screen: "build",
    });
    el.appendChild(cont);
  },
};

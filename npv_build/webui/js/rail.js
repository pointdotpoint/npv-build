"use strict";
const STEPS = [
  ["source", "1 · Source"], ["appearance", "2 · Appearance"],
  ["build", "3 · Build"], ["install", "4 · Install"],
];
const PAGES = [["library", "My NPVs"], ["settings", "Settings"]];
const STEP_ORDER = ["source", "appearance", "build", "install"];

function stepUnlocked(name, s) {
  const idx = STEP_ORDER.indexOf(name);
  if (idx <= 0) return true;
  return STEP_ORDER.slice(0, idx).every((n) => s.stepsDone[n]);
}

function renderRail(s) {
  const el = document.getElementById("rail");
  el.innerHTML = "";
  const title = document.createElement("div");
  title.className = "rail-title"; title.textContent = "NPV BUILD";
  el.appendChild(title);
  for (const [name, label] of STEPS) {
    const item = document.createElement("div");
    const navigationLocked = s.appearanceBusy && name !== "appearance";
    const unlocked = !navigationLocked && stepUnlocked(name, s);
    item.className = "rail-item"
      + (s.screen === name ? " current" : "")
      + (s.stepsDone[name] ? " done" : "")
      + (unlocked ? "" : " locked");
    item.textContent = (s.stepsDone[name] ? "✓ " : "") + label;
    if (navigationLocked) item.title = "Wait for the hair mod to finish loading.";
    if (unlocked) item.onclick = () => store.set({ screen: name });
    el.appendChild(item);
  }
  const sep = document.createElement("div");
  sep.className = "rail-sep"; el.appendChild(sep);
  for (const [name, label] of PAGES) {
    const item = document.createElement("div");
    item.className = "rail-item" + (s.screen === name ? " current" : "")
      + (s.appearanceBusy ? " locked" : "");
    item.textContent = label;
    if (s.appearanceBusy) {
      item.title = "Wait for the hair mod to finish loading.";
    } else {
      item.onclick = () => store.set({ screen: name });
    }
    el.appendChild(item);
  }
  const v = document.createElement("div");
  v.className = "rail-version";
  v.textContent = s.appState ? `v${s.appState.version}` : "";
  el.appendChild(v);
}
window.renderRail = renderRail;

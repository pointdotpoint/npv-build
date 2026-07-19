"use strict";
window.screens = window.screens || {};
function renderApp(s) {
  renderRail(s);
  const el = document.getElementById("screen");
  const screen = window.screens[s.screen];
  el.innerHTML = "";
  if (screen) screen.render(el, s);
}
store.subscribe(renderApp);
(async function init() {
  const appState = await Api.call("get_state");
  const patch = { appState };
  if (appState.needs_onboarding) patch.screen = "onboarding";
  store.set(patch);
})();

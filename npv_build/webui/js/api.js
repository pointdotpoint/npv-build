"use strict";
const Api = {
  async call(method, ...args) {
    if (window.__mockApi) return window.__mockApi[method](...args);
    await Api._ready();
    return window.pywebview.api[method](...args);
  },
  _readyPromise: null,
  _ready() {
    if (window.pywebview) return Promise.resolve();
    if (!Api._readyPromise) {
      Api._readyPromise = new Promise((resolve) =>
        window.addEventListener("pywebviewready", resolve, { once: true }));
    }
    return Api._readyPromise;
  },
};
window.Api = Api;

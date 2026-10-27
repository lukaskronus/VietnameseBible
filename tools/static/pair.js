"use strict";
(function () {
  var VI_KEY = "kt-vi";
  var EN_KEY = "kt-en";
  // Defaults come from the server-rendered <option selected>; never hardcode
  // a translation code here, both pipelines use different ones.
  function rendered(id) {
    var el = document.getElementById(id);
    return el ? el.value : "";
  }
  var DEF_VI = rendered("pair-vi");
  var DEF_EN = rendered("pair-en");
  function store(k, v) {
    try {
      localStorage.setItem(k, v);
    } catch (e) {}
  }
  function recall(k, d) {
    try {
      return localStorage.getItem(k) || d;
    } catch (e) {
      return d;
    }
  }
  function get() {
    return { vi: recall(VI_KEY, DEF_VI), en: recall(EN_KEY, DEF_EN) };
  }
  function fire(p) {
    try {
      document.dispatchEvent(new CustomEvent("kt-pair-change", { detail: p }));
    } catch (e) {
      var ev = document.createEvent("Event");
      ev.initEvent("kt-pair-change", true, true);
      document.dispatchEvent(ev);
    }
  }
  function set(p) {
    store(VI_KEY, p.vi);
    store(EN_KEY, p.en);
    var vs = document.getElementById("pair-vi");
    var es = document.getElementById("pair-en");
    if (vs) vs.value = p.vi;
    if (es) es.value = p.en;
    fire(p);
  }
  function init() {
    var vs = document.getElementById("pair-vi");
    var es = document.getElementById("pair-en");
    var p = get();
    if (vs) {
      vs.value = p.vi;
      vs.addEventListener("change", function () {
        set({ vi: vs.value, en: es ? es.value : get().en });
      });
    }
    if (es) {
      es.value = p.en;
      es.addEventListener("change", function () {
        set({ vi: vs ? vs.value : get().vi, en: es.value });
      });
    }
  }
  window.ktPair = { get: get, set: set };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

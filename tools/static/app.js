"use strict";

function ktGet(id) {
  return document.getElementById(id);
}

/* Theme toggle */
var themeBtn = ktGet("theme-btn");
if (themeBtn) {
  themeBtn.onclick = function () {
    var h = document.documentElement;
    var next = h.dataset.theme === "dark" ? "light" : "dark";
    h.dataset.theme = next;
    try {
      localStorage.setItem("kt-theme", next);
    } catch (e) {}
  };
}

/* Font-size controls */
function ktFs(delta) {
  var h = document.documentElement;
  var cur = parseInt(getComputedStyle(h).getPropertyValue("--fs"), 10) || 18;
  var next = Math.min(26, Math.max(14, cur + delta));
  h.style.setProperty("--fs", next + "px");
  try {
    localStorage.setItem("kt-fs", String(next));
  } catch (e) {}
}

var fa = ktGet("fs-dec");
var fb = ktGet("fs-inc");
if (fa) fa.onclick = function () { ktFs(-1); };
if (fb) fb.onclick = function () { ktFs(1); };

/* Dropdown menus */
document.querySelectorAll(".dd").forEach(function (el) {
  el.addEventListener("click", function (e) {
    e.stopPropagation();
    var wasOpen = el.classList.contains("open");
    document.querySelectorAll(".dd").forEach(function (d) {
      d.classList.remove("open");
    });
    if (!wasOpen) el.classList.add("open");
  });
});

document.addEventListener("click", function () {
  document.querySelectorAll(".dd").forEach(function (d) {
    d.classList.remove("open");
  });
});

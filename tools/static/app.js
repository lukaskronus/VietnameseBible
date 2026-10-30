/*! Kinh Thánh Song Ngữ VI-EN | design & code by Hirose Kobayashi | github.com/lukaskronus/VietnameseBible */

"use strict";

function ktGet(id) {
  return document.getElementById(id);
}

/* Helpers shared by book.js, daily.js and search.js. app.js loads first on
   every page, so these globals exist before those scripts run. */
function ktEsc(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function ktEscAttr(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;");
}

function ktBase() {
  var b = document.querySelector('meta[name="kt-base"]');
  return b ? b.content : "";
}

function ktBiTitle(vi, en) {
  var t = vi.book + " " + vi.n;
  if (en.book) t += " · " + en.book + " " + en.n;
  return t;
}

/* Merge one VI chapter file with one EN chapter file. Verse numbers are
   unioned; a verse empty on both sides is skipped. */
function ktMergePair(viBlocks, enBlocks) {
  var mVi = {};
  var mEn = {};
  var seen = {};
  var keys = [];
  var i;
  function collect(blocks, map) {
    for (var j = 0; j < blocks.length; j++) {
      var n = blocks[j].n;
      map[n] = blocks[j].x || "";
      if (!seen[n]) {
        seen[n] = 1;
        keys.push(n);
      }
    }
  }
  collect(viBlocks, mVi);
  collect(enBlocks, mEn);
  keys.sort(function (a, b) {
    return a - b;
  });
  var h = "";
  for (i = 0; i < keys.length; i++) {
    var n = keys[i];
    var vv = mVi[n] || "";
    var ee = mEn[n] || "";
    if (!vv && !ee) continue;
    h += '<div class="verse-pair"><p class="reading vi"><sup>' + n +
      "</sup>" + ktEsc(vv) + "</p>";
    if (ee) h += '<p class="reading en" lang="en"><sup>' + n + "</sup>" +
      ktEsc(ee) + "</p>";
    h += "</div>";
  }
  return h;
}

/* Theme toggle */
var themeBtn = ktGet("theme-btn");
function ktUpdateThemeBtn() {
  if (!themeBtn) return;
  var dark = document.documentElement.dataset.theme === "dark";
  themeBtn.textContent = dark ? "☀" : "☾";
  themeBtn.setAttribute("aria-pressed", dark);
  themeBtn.title = dark ? "Chuyển sang nền sáng" : "Chuyển sang nền tối";
  var meta = document.querySelector('meta[name="theme-color"]');
  // --paper, not body background: the body background transitions, so reading
  // it right after a theme switch returns the old colour.
  if (meta) meta.content = getComputedStyle(
    document.documentElement).getPropertyValue("--paper").trim();
}
if (themeBtn) {
  themeBtn.onclick = function () {
    var h = document.documentElement;
    var next = h.dataset.theme === "dark" ? "light" : "dark";
    h.dataset.theme = next;
    try {
      localStorage.setItem("kt-theme", next);
    } catch (e) {}
    ktUpdateThemeBtn();
  };
}

/* Font-size controls */
function ktFs(delta) {
  var h = document.documentElement;
  var cur = parseInt(getComputedStyle(h).getPropertyValue("--fs"), 10) || 19;
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

/* English translation on/off */
var enBtn = ktGet("en-btn");
function ktUpdateEnBtn() {
  if (!enBtn) return;
  var off = document.documentElement.dataset.en === "off";
  enBtn.setAttribute("aria-pressed", off ? "false" : "true");
  enBtn.title = off ? "Hiện bản tiếng Anh" : "Ẩn bản tiếng Anh";
}
if (enBtn) {
  enBtn.onclick = function () {
    var h = document.documentElement;
    var off = h.dataset.en === "off";
    if (off) {
      h.removeAttribute("data-en");
    } else {
      h.dataset.en = "off";
    }
    try {
      localStorage.setItem("kt-en-show", off ? "1" : "0");
    } catch (e) {}
    ktUpdateEnBtn();
  };
}

/* Testament menus */
function ktCloseDd(except) {
  document.querySelectorAll(".dd").forEach(function (d) {
    if (d !== except) {
      d.classList.remove("open");
      var b = d.querySelector("button");
      if (b) b.setAttribute("aria-expanded", "false");
    }
  });
}
document.querySelectorAll(".dd").forEach(function (el) {
  el.addEventListener("click", function (e) {
    e.stopPropagation();
    var open = !el.classList.contains("open");
    ktCloseDd(el);
    el.classList.toggle("open", open);
    var b = el.querySelector("button");
    if (b) b.setAttribute("aria-expanded", open ? "true" : "false");
  });
  // Tab past the last book: the panel must not stay open over the page while
  // focus is somewhere else.
  el.addEventListener("focusout", function (e) {
    if (e.relatedTarget && el.contains(e.relatedTarget)) return;
    if (el.classList.contains("open")) ktCloseDd();
  });
});
document.addEventListener("click", function () {
  ktCloseDd();
});
document.addEventListener("keydown", function (e) {
  if (e.key !== "Escape") return;
  // Escape from inside the panel: hand focus back to the button first, or the
  // browser drops it on <body> and the reader is back at the top of the page.
  document.querySelectorAll(".dd.open").forEach(function (el) {
    var b = el.querySelector("button");
    if (b && el.contains(document.activeElement)) b.focus();
  });
  ktCloseDd();
});

/* Reading progress */
var prog = ktGet("progress");
function ktProgress() {
  if (!prog) return;
  var h = document.documentElement;
  var max = h.scrollHeight - h.clientHeight;
  prog.style.width = (max > 0 ? (h.scrollTop / max) * 100 : 0) + "%";
}
if (prog && (ktGet("bk-content") || document.querySelector(".verse-pair"))) {
  document.body.dataset.reader = "1";
  window.addEventListener("scroll", ktProgress, { passive: true });
  window.addEventListener("resize", ktProgress);
  ktProgress();
}

/* Arrow keys turn the page */
document.addEventListener("keydown", function (e) {
  if (e.altKey || e.ctrlKey || e.metaKey) return;
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  var t = e.target;
  if (t && (t.tagName === "INPUT" || t.tagName === "SELECT" ||
            t.tagName === "TEXTAREA" || t.isContentEditable)) return;

  var links = document.querySelectorAll("nav.pn a");
  if (links.length) {
    var link = e.key === "ArrowLeft" ? links[0] : links[links.length - 1];
    if (link && link.href) window.location.href = link.href;
    return;
  }
  var bar = document.querySelectorAll(".chap-bar a");
  for (var i = 0; i < bar.length; i++) {
    if (bar[i].classList.contains("active")) {
      var j = e.key === "ArrowLeft" ? i - 1 : i + 1;
      if (j >= 0 && j < bar.length) bar[j].click();
      return;
    }
  }
});

ktUpdateThemeBtn();
ktUpdateEnBtn();

/* Phone: the 66-book index starts collapsed; a tap on either testament opens it.
   Breakpoint must stay equal to the 720px media query in style.css. */
if (window.matchMedia && window.matchMedia("(max-width: 720px)").matches) {
  document.querySelectorAll(".index-col").forEach(function (el) {
    el.open = false;
  });
}

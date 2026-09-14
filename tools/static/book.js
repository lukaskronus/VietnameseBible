"use strict";
function esc(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
function base() {
  var b = document.querySelector('meta[name="kt-base"]');
  return b ? b.content : "";
}
function pairOf() {
  if (window.ktPair) return window.ktPair.get();
  return { vi: "vi1925", en: "ennasb" };
}
function biTitle(vi, en) {
  var t = vi.book + " " + vi.n;
  if (en.book) t += " · " + en.book + " " + en.n;
  return t;
}
function renderPair(viBlocks, enBlocks) {
  var mVi = {};
  var mEn = {};
  var i;
  for (i = 0; i < viBlocks.length; i++) mVi[viBlocks[i].n] = viBlocks[i].x || "";
  for (i = 0; i < enBlocks.length; i++) mEn[enBlocks[i].n] = enBlocks[i].x || "";
  var seen = {};
  var keys = [];
  function collect(blocks) {
    for (var j = 0; j < blocks.length; j++) {
      var n = blocks[j].n;
      if (!seen[n]) {
        seen[n] = 1;
        keys.push(n);
      }
    }
  }
  collect(viBlocks);
  collect(enBlocks);
  keys.sort(function (x, y) {
    return x - y;
  });
  var h = "";
  for (i = 0; i < keys.length; i++) {
    var n = keys[i];
    var vv = mVi[n] || "";
    var ee = mEn[n] || "";
    if (!vv && !ee) continue;
    h += '<div class="verse-pair"><p class="reading vi"><sup>' + n + "</sup>" + esc(vv) + "</p>";
    if (ee) h += '<p class="reading en" lang="en"><sup>' + n + "</sup>" + esc(ee) + "</p>";
    h += "</div>";
  }
  return h;
}
function markActive(n) {
  var ls = document.querySelectorAll(".chap-btns a");
  for (var i = 0; i < ls.length; i++) {
    if (ls[i].getAttribute("data-n") === String(n)) {
      ls[i].classList.add("active");
    } else {
      ls[i].classList.remove("active");
    }
  }
}
function currentCid() {
  var a = document.querySelector(".chap-btns a.active");
  return a ? a.getAttribute("data-cid") : null;
}
function loadChapter(cid, push) {
  var box = document.getElementById("bk-content");
  if (!box) return;
  var p = pairOf();
  var bp = base();
  box.innerHTML = "<p>Đang tải…</p>";
  Promise.all([
    fetch(bp + "/data/tr/" + p.vi + "/ch/" + cid + ".json").then(function (r) {
      if (!r.ok) throw 0;
      return r.json();
    }),
    fetch(bp + "/data/tr/" + p.en + "/ch/" + cid + ".json").then(function (r) {
      if (!r.ok) throw 0;
      return r.json();
    }),
  ])
    .then(function (pair) {
      var vi = pair[0];
      var en = pair[1];
      box.innerHTML = renderPair(vi.blocks, en.blocks);
      document.getElementById("bk-ch-title").textContent = biTitle(vi, en);
      var site = "";
      var lay = document.querySelector(".book-layout");
      if (lay) site = lay.getAttribute("data-site") || "";
      document.title = biTitle(vi, en) + (site ? " | " + site : "");
      markActive(vi.n);
      if (push !== false) {
        try {
          history.replaceState(null, "", "#c" + vi.n);
        } catch (e) {}
      }
      var top = box.getBoundingClientRect().top + window.scrollY - 80;
      try {
        window.scrollTo({ top: top, behavior: "smooth" });
      } catch (e) {
        window.scrollTo(0, top);
      }
    })
    .catch(function () {
      box.innerHTML = "<p>Không tải được chương này.</p>";
    });
}
var btns = document.querySelectorAll(".chap-btns a");
for (var i = 0; i < btns.length; i++) {
  (function (a) {
    a.addEventListener("click", function (e) {
      e.preventDefault();
      loadChapter(a.getAttribute("data-cid"), true);
    });
  })(btns[i]);
}
document.addEventListener("kt-pair-change", function () {
  var cid = currentCid();
  if (cid) loadChapter(cid, false);
});
(function () {
  var m = (location.hash || "").match(/^#c(\d+)$/);
  if (m) {
    var want = m[1];
    for (var i = 0; i < btns.length; i++) {
      if (btns[i].getAttribute("data-n") === want) {
        loadChapter(btns[i].getAttribute("data-cid"), false);
        break;
      }
    }
  }
})();

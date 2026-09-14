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
var CHS = null;
function pairOf() {
  if (window.ktPair) return window.ktPair.get();
  return { vi: "vi1925", en: "ennasb" };
}
function mergeBlocks(viBlocks, enBlocks) {
  var mVi = {};
  var mEn = {};
  var i;
  for (i = 0; i < viBlocks.length; i++) mVi[viBlocks[i].n] = viBlocks[i].x || "";
  for (i = 0; i < enBlocks.length; i++) mEn[enBlocks[i].n] = enBlocks[i].x || "";
  var seen = {};
  var keys = [];
  for (i = 0; i < viBlocks.length; i++) {
    var a = viBlocks[i].n;
    if (!seen[a]) {
      seen[a] = 1;
      keys.push(a);
    }
  }
  for (i = 0; i < enBlocks.length; i++) {
    var c = enBlocks[i].n;
    if (!seen[c]) {
      seen[c] = 1;
      keys.push(c);
    }
  }
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
function biTitle(vi, en) {
  var t = vi.book + " " + vi.n;
  if (en.book) t += " · " + en.book + " " + en.n;
  return t;
}
function loadDaily() {
  var p = pairOf();
  var bp = base();
  function chs() {
    if (CHS) return Promise.resolve(CHS);
    return fetch(bp + "/data/chapters.json")
      .then(function (r) {
        return r.json();
      })
      .then(function (c) {
        CHS = c;
        return c;
      });
  }
  chs()
    .then(function (list) {
      var id = (Math.floor(Date.now() / 864e5) % list.length) + 1;
      return Promise.all([
        fetch(bp + "/data/tr/" + p.vi + "/ch/" + id + ".json").then(function (r) {
          if (!r.ok) throw 0;
          return r.json();
        }),
        fetch(bp + "/data/tr/" + p.en + "/ch/" + id + ".json").then(function (r) {
          if (!r.ok) throw 0;
          return r.json();
        }),
      ]);
    })
    .then(function (pair) {
      var vi = pair[0];
      var en = pair[1];
      document.getElementById("daily-title").textContent = biTitle(vi, en);
      document.getElementById("daily-link").href = bp + "/" + vi.slug + "/" + vi.n + "/";
      document.getElementById("daily-text").innerHTML = mergeBlocks(vi.blocks, en.blocks);
    })
    .catch(function () {
      document.getElementById("daily-text").innerHTML =
        "<p>Không tải được đoạn Kinh Thánh hôm nay.</p>";
    });
}
document.addEventListener("kt-pair-change", loadDaily);
loadDaily();

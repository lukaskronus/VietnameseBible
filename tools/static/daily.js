"use strict";
var CHS = null;
function loadDaily() {
  var p = window.ktPair.get();
  var bp = ktBase();
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
      // Daily surprise: full-cycle shuffle over all chapters. 701 is coprime
      // to the chapter count (1189 = 29*41), so (701*day + 123) % N visits
      // every chapter exactly once per cycle, in unpredictable order.
      // UTC day number; build_site.py's docstring documents the same rule.
      var day = Math.floor(Date.now() / 864e5);
      var id = ((701 * day + 123) % list.length) + 1;
      return Promise.all([
        fetch(bp + "/data/tr/" + p.vi + "/ch/" + id + ".json").then(function (r) {
          if (!r.ok) throw 0;
          return r.json();
        }),
        fetch(bp + "/data/tr/" + p.en + "/ch/" + id + ".json").then(function (r) {
          if (!r.ok) throw 0;
          return r.json();
        }),
      ]).then(function (pair) {
        return { vi: pair[0], en: pair[1], list: list, id: id };
      });
    })
    .then(function (o) {
      var vi = o.vi;
      var en = o.en;
      var meta = document.getElementById("daily-meta");
      if (meta) {
        meta.textContent = "Chương " + o.id + " trong tổng số " + o.list.length;
      }
      document.getElementById("daily-title").textContent = ktBiTitle(vi, en);
      document.getElementById("daily-link").href = bp + "/" + vi.slug + "/" + vi.n + "/";
      document.getElementById("daily-text").innerHTML = ktMergePair(vi.blocks, en.blocks);
    })
    .catch(function () {
      // Otherwise "Đang tải…" sits there for ever under a heading that never
      // arrives.
      var meta = document.getElementById("daily-meta");
      if (meta) meta.textContent = "";
      document.getElementById("daily-text").innerHTML =
        "<p>Không tải được đoạn Kinh Thánh hôm nay.</p>";
    });
}
document.addEventListener("kt-pair-change", loadDaily);
loadDaily();

"use strict";
function markActive(n) {
  var ls = document.querySelectorAll(".chap-bar a");
  for (var i = 0; i < ls.length; i++) {
    if (ls[i].getAttribute("data-n") === String(n)) {
      ls[i].classList.add("active");
    } else {
      ls[i].classList.remove("active");
    }
  }
}
function currentCid() {
  var a = document.querySelector(".chap-bar a.active");
  return a ? a.getAttribute("data-cid") : null;
}
function loadChapter(cid, push) {
  var box = document.getElementById("bk-content");
  if (!box) return;
  var p = window.ktPair.get();
  var bp = ktBase();
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
      box.innerHTML = ktMergePair(vi.blocks, en.blocks);
      document.getElementById("bk-ch-title").textContent = ktBiTitle(vi, en);
      var site = "";
      var lay = document.querySelector(".book-layout");
      if (lay) site = lay.getAttribute("data-site") || "";
      document.title = ktBiTitle(vi, en) + (site ? " | " + site : "");
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
var btns = document.querySelectorAll(".chap-bar a");
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

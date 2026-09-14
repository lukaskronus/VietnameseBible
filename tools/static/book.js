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

function biTitle(d) {
  var t = d.book + " " + d.n;
  if (d.book_en) t += " · " + d.book_en + " " + d.n;
  return t;
}

function render(d) {
  var h = "";
  for (var i = 0; i < d.blocks.length; i++) {
    var b = d.blocks[i];
    if (b.t === "h") {
      h += '<h2 class="sec">' + esc(b.en || b.x || "") + "</h2>";
    } else {
      h += '<div class="verse-pair">';
      h += '<p class="reading vi"><sup>' + b.n + "</sup>" + esc(b.vi || b.x || "") + "</p>";
      if (b.en) {
        h += '<p class="reading en" lang="en"><sup>' + b.n + "</sup>" + esc(b.en) + "</p>";
      }
      h += "</div>";
    }
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

function loadChapter(cid, n, push) {
  var box = document.getElementById("bk-content");
  if (!box) return;

  box.innerHTML = "<p>Đang tải…</p>";

  fetch(base() + "/data/ch/" + cid + ".json")
    .then(function (r) {
      if (!r.ok) throw 0;
      return r.json();
    })
    .then(function (d) {
      box.innerHTML = render(d);
      document.getElementById("bk-ch-title").textContent = biTitle(d);

      var site = "";
      var lay = document.querySelector(".book-layout");
      if (lay) site = lay.getAttribute("data-site") || "";
      document.title = biTitle(d) + (site ? " | " + site : "");

      markActive(d.n);

      if (push !== false) {
        try {
          history.replaceState(null, "", "#c" + d.n);
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
      loadChapter(a.getAttribute("data-cid"), a.getAttribute("data-n"), true);
    });
  })(btns[i]);
}

(function () {
  var m = (location.hash || "").match(/^#c(\d+)$/);
  if (m) {
    var want = m[1];
    for (var i = 0; i < btns.length; i++) {
      if (btns[i].getAttribute("data-n") === want) {
        loadChapter(btns[i].getAttribute("data-cid"), want, false);
        break;
      }
    }
  }
})();

"use strict";

function fold(s) {
  return s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .replace(/ð/g, "d")
    .replace(/Ð/g, "D")
    .toLowerCase();
}

function toks(s) {
  var m = s.match(/[a-z0-9]+/g) || [];
  return m.filter(function (t) {
    return t.length >= 2;
  });
}

var IDX = null;
var CHS = null;

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

function run(e) {
  if (e) e.preventDefault();

  var box = document.getElementById("q");
  var out = document.getElementById("results");
  var q = toks(fold(box.value));

  if (!q.length) {
    out.innerHTML = "<p>Vui lòng nhập ít nhất 2 ký tự.</p>";
    return;
  }
  if (!IDX) {
    out.innerHTML = "<p>Đang tải dữ liệu tìm kiếm…</p>";
    return;
  }

  var hit = null;
  for (var i = 0; i < q.length; i++) {
    var ids = IDX.index[q[i]] || [];
    if (hit === null) {
      hit = {};
      for (var j = 0; j < ids.length; j++) hit[ids[j]] = 1;
    } else {
      var nx = {};
      for (var k = 0; k < ids.length; k++) {
        if (hit[ids[k]]) nx[ids[k]] = 1;
      }
      hit = nx;
    }
    if (!Object.keys(hit).length) break;
  }

  var keys = Object.keys(hit || {})
    .map(Number)
    .sort(function (a, b) {
      return a - b;
    });

  var bp = base();

  if (!keys.length) {
    out.innerHTML = "<p>Không tìm thấy kết quả.</p>";
    return;
  }

  var h = "<p>Tìm thấy " + keys.length + " đoạn.</p>";
  var lim = Math.min(keys.length, 100);

  for (var n = 0; n < lim; n++) {
    var c = CHS[keys[n] - 1];
    var label = c.book + " " + c.n;
    if (c.book_en) label += " · " + c.book_en + " " + c.n;
    h +=
      '<a href="' +
      bp +
      "/" +
      c.slug +
      "/" +
      c.n +
      '/">' +
      esc(label) +
      "</a>";
  }

  if (keys.length > lim) {
    h += "<p>…chỉ hiển thị 100 kết quả đầu.</p>";
  }

  out.innerHTML = h;
}

document.getElementById("search-form").addEventListener("submit", run);

Promise.all([
  fetch(base() + "/data/search_index.json").then(function (r) {
    return r.json();
  }),
  fetch(base() + "/data/chapters.json").then(function (r) {
    return r.json();
  }),
])
  .then(function (v) {
    IDX = v[0];
    CHS = v[1];
    var pre = document.getElementById("q").value;
    if (pre) run();
  })
  .catch(function () {
    document.getElementById("results").innerHTML =
      "<p>Không tải được dữ liệu tìm kiếm.</p>";
  });

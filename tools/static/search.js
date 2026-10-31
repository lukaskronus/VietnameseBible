"use strict";

/* fold()/toks()/shardId() live in fold.js, loaded after app.js and before
   this file. Escaping and base-path helpers come from app.js.

   A multi-word query matches any adjacent word pair from the query, in order:
   "tinh yeu thuong" looks up "tinh yeu" and "yeu thuong", never loose words.
   The index (data/search/) is built by tools/build_db.py; each shard maps a
   folded word or pair to base64 LEB128-delta verse codes. */

var MAN = null;
var CHS = null;
var SHARDS = {};
var LOADING = null;

function ktLoad() {
  if (!LOADING) {
    var bp = ktBase();
    LOADING = Promise.all([
      fetch(bp + "/data/search/manifest.json").then(function (r) {
        return r.json();
      }),
      fetch(bp + "/data/chapters.json").then(function (r) {
        return r.json();
      }),
    ]).then(function (v) {
      MAN = v[0];
      CHS = v[1];
    });
  }
  return LOADING;
}

function shardPath(sid) {
  var hex = ("0" + sid.toString(16)).slice(-2);
  return ktBase() + "/data/search/s" + hex + ".json";
}

function loadShard(sid) {
  if (SHARDS[sid]) return Promise.resolve(SHARDS[sid]);
  return fetch(shardPath(sid))
    .then(function (r) {
      if (r.status === 404) return {};
      if (!r.ok) throw new Error("shard " + sid);
      return r.json();
    })
    .then(function (m) {
      SHARDS[sid] = m;
      return m;
    });
}

function decodeCodes(b64) {
  var bin = atob(b64);
  var out = [];
  var acc = 0;
  var delta = 0;
  var shift = 0;
  for (var i = 0; i < bin.length; i++) {
    var b = bin.charCodeAt(i);
    delta += (b & 127) * Math.pow(2, shift);
    if (b & 128) {
      shift += 7;
      continue;
    }
    acc += delta;
    out.push(acc);
    delta = 0;
    shift = 0;
  }
  return out;
}

function queryKeys(q) {
  var t = toks(fold(q));
  var keys = [];
  var i;
  if (t.length === 1) return [t[0]];
  for (i = 0; i < t.length - 1; i++) keys.push(t[i] + " " + t[i + 1]);
  return keys;
}

function render(ids) {
  var out = document.getElementById("results");
  var codes = Object.keys(ids)
    .map(Number)
    .sort(function (a, b) {
      return a - b;
    });

  if (!codes.length) {
    out.innerHTML = "<p>Không tìm thấy kết quả.</p>";
    return;
  }

  var bp = ktBase();
  var h = "<p>Tìm thấy " + codes.length + " câu.</p>";
  var lim = Math.min(codes.length, 100);
  var currentBook = "";

  for (var i = 0; i < lim; i++) {
    var cid = Math.floor(codes[i] / MAN.code_base);
    var vn = codes[i] % MAN.code_base;
    var c = CHS[cid - 1];
    if (!c) continue;
    if (c.book !== currentBook) {
      currentBook = c.book;
      h += "<h3>" + ktEsc(currentBook) + "</h3>";
    }
    var label = c.book + " " + c.n + ":" + vn;
    if (c.book_en) label += " · " + c.book_en + " " + c.n + ":" + vn;
    var href = bp + "/" + c.slug + "/" + c.n + "/#c" + c.n + "v" + vn;
    h += '<a href="' + ktEscAttr(href) + '">' + ktEsc(label) + "</a>";
  }

  if (codes.length > lim) {
    h += "<p>…chỉ hiển thị 100 kết quả đầu.</p>";
  }

  out.innerHTML = h;
}

function run(e) {
  if (e) e.preventDefault();

  var out = document.getElementById("results");
  var keys = queryKeys(document.getElementById("q").value);

  if (!keys.length) {
    out.innerHTML = "<p>Vui lòng nhập ít nhất 2 ký tự.</p>";
    return;
  }

  out.innerHTML = "<p>Đang tìm…</p>";

  ktLoad()
    .then(function () {
      return Promise.all(
        keys.map(function (k) {
          return loadShard(shardId(k, MAN.shard_count)).then(function (m) {
            return m[k];
          });
        })
      );
    })
    .then(function (vals) {
      var ids = {};
      for (var i = 0; i < vals.length; i++) {
        if (!vals[i]) continue;
        var codes = decodeCodes(vals[i]);
        for (var j = 0; j < codes.length; j++) ids[codes[j]] = 1;
      }
      render(ids);
    })
    .catch(function () {
      out.innerHTML = "<p>Không tải được dữ liệu tìm kiếm.</p>";
    });
}

document.getElementById("search-form").addEventListener("submit", run);

if (document.getElementById("q").value) run();

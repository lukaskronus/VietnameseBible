"use strict";

/* Search folding. Must stay byte-for-byte equivalent to fold()/tokenize() in
   tools/build_db.py; tools/check_fold.py and tools/check_fold.js diff the two
   in CI. NFD, strip combining marks, d/D variants to d, lowercase, [a-z0-9]+
   runs of length >= 2. */

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

/* FNV-1a 32-bit of an ASCII key, modulo the manifest's shard_count. Must
   stay equal to shard_id() in tools/build_db.py; CI diffs both. */
function shardId(key, count) {
  var h = 2166136261;
  for (var i = 0; i < key.length; i++) {
    h ^= key.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h % count;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { fold: fold, toks: toks, shardId: shardId };
}

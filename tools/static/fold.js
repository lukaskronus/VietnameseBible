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

if (typeof module !== "undefined" && module.exports) {
  module.exports = { fold: fold, toks: toks };
}

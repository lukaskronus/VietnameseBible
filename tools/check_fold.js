#!/usr/bin/env node
/* Print fold/toks output for tools/fold_cases.json, matching check_fold.py.
   The CI step diffs both outputs. */

"use strict";

const fs = require("fs");
const path = require("path");
const foldjs = require(path.join(__dirname, "static", "fold.js"));

const cases = JSON.parse(
  fs.readFileSync(path.join(__dirname, "fold_cases.json"), "utf8")
);

for (const c of cases) {
  process.stdout.write(foldjs.toks(foldjs.fold(c)).join(" ") + "\n");
}

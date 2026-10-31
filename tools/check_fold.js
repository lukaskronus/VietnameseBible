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
  const toks = foldjs.toks(foldjs.fold(c));
  process.stdout.write(toks.join(" ") + "\n");
  // Shard routing must agree with tools/build_db.py too.
  process.stdout.write(
    toks.map((t) => foldjs.shardId(t, 256)).join(" ") + "\n");
  process.stdout.write(
    toks
      .slice(1)
      .map((t, i) => foldjs.shardId(toks[i] + " " + t, 256))
      .join(" ") + "\n");
}

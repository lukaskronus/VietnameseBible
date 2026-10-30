#!/usr/bin/env python3
"""Print fold/tokenize output for tools/fold_cases.json (one line per case).

tools/check_fold.js must print exactly the same lines. The CI step diffs the
two outputs, so a divergence between build_db.py and tools/static/fold.js
fails the build instead of shipping a search that finds nothing.

    python tools/check_fold.py > py.txt
    node tools/check_fold.js > js.txt
    diff -u py.txt js.txt
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build_db import fold, tokenize  # noqa: E402

CASES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "fold_cases.json")


def main():
    with open(CASES, encoding="utf-8") as f:
        cases = json.load(f)
    for case in cases:
        print(" ".join(tokenize(fold(case))))
    return 0


if __name__ == "__main__":
    sys.exit(main())

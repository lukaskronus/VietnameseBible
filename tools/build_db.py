#!/usr/bin/env python3
"""Build queryable artifacts from build/bible.json (Phase 1 output).

Phase 2 of the static-site pipeline. Stdlib only.

    python tools/build_db.py --json build/bible.json --out build

Outputs (under --out):
    bible.sqlite        normalized relational DB + FTS5 full-text index
    search_index.json   compact token -> chapter-id map for client search

Schema:
    books(id, code, position, testament, slug, title, subtitle, range)
    chapters(id, book_id, number)       -- ids run 1..N in canon order
    verses(id, chapter_id, number, text, text_norm)
    headings(id, chapter_id, position, text)
    verses_fts                          -- FTS5 over text_norm, trigger-kept
    meta(key, value)

Text folding (diacritic-insensitive search). The Phase 3 client MUST
implement exactly this:
    NFD normalize -> strip combining marks -> d/Ð to d -> lowercase,
    tokens = [a-z0-9]+ runs of length >= 2.

Verse-of-the-day rotation (implemented client-side in Phase 3):
    chapter_id = (days_since_unix_epoch % total_chapters) + 1
(total_chapters is stored in meta and in search_index.json.)

Exit 0 on success, 1 on any error.
NOTE: executed by GitHub Actions (cloud) only.
Local machines are code storage; do not run builds on them.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone

TOKEN = re.compile(r"[a-z0-9]+")
MIN_TOKEN_LEN = 2  # single letters stay out of the client index (see above)

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE books(
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL,
  position INTEGER NOT NULL UNIQUE,
  testament TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  subtitle TEXT,
  range TEXT
);
CREATE TABLE chapters(
  id INTEGER PRIMARY KEY,
  book_id INTEGER NOT NULL REFERENCES books(id),
  number INTEGER NOT NULL,
  UNIQUE(book_id, number)
);
CREATE TABLE verses(
  id INTEGER PRIMARY KEY,
  chapter_id INTEGER NOT NULL REFERENCES chapters(id),
  number INTEGER NOT NULL,
  text TEXT NOT NULL,
  text_norm TEXT NOT NULL
);
CREATE INDEX idx_verses_chapter ON verses(chapter_id);
CREATE TABLE headings(
  id INTEGER PRIMARY KEY,
  chapter_id INTEGER NOT NULL REFERENCES chapters(id),
  position INTEGER NOT NULL,
  text TEXT NOT NULL
);
CREATE INDEX idx_headings_chapter ON headings(chapter_id);
CREATE VIRTUAL TABLE verses_fts USING fts5(
  text_norm, content='verses', content_rowid='id', tokenize='unicode61'
);
CREATE TRIGGER verses_ai AFTER INSERT ON verses BEGIN
  INSERT INTO verses_fts(rowid, text_norm) VALUES (new.id, new.text_norm);
END;
CREATE TRIGGER verses_ad AFTER DELETE ON verses BEGIN
  INSERT INTO verses_fts(verses_fts, rowid, text_norm)
  VALUES ('delete', old.id, old.text_norm);
END;
CREATE TRIGGER verses_au AFTER UPDATE ON verses BEGIN
  INSERT INTO verses_fts(verses_fts, rowid, text_norm)
  VALUES ('delete', old.id, old.text_norm);
  INSERT INTO verses_fts(rowid, text_norm) VALUES (new.id, new.text_norm);
END;
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
"""


def fold(text):
    """Fold Vietnamese text for diacritic-insensitive matching."""
    norm = unicodedata.normalize("NFD", text)
    norm = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    return norm.replace("\u0111", "d").replace("\u0110", "D").lower()


def tokenize(folded):
    return [t for t in TOKEN.findall(folded) if len(t) >= MIN_TOKEN_LEN]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", required=True, help="Phase 1 bible.json")
    ap.add_argument("--out", default="build", help="output directory (CI only)")
    args = ap.parse_args()

    if not os.path.isfile(args.json):
        print("error: %s not found (run Phase 1 first)" % args.json,
              file=sys.stderr)
        return 1
    with open(args.json, encoding="utf-8") as f:
        payload = json.load(f)
    books = payload.get("books")
    if not books:
        print("error: no books in %s" % args.json, file=sys.stderr)
        return 1

    os.makedirs(args.out, exist_ok=True)
    db_path = os.path.join(args.out, "bible.sqlite")
    if os.path.exists(db_path):
        os.remove(db_path)

    try:
        con = sqlite3.connect(db_path)
    except sqlite3.Error as e:
        print("error: cannot create %s: %s" % (db_path, e), file=sys.stderr)
        return 1
    try:
        with con:
            con.executescript(SCHEMA)
    except sqlite3.Error as e:
        print("error: schema failed (is FTS5 available?): %s" % e,
              file=sys.stderr)
        return 1

    postings = {}  # token -> set of chapter ids
    n_chapters = n_verses = n_headings = 0
    try:
        with con:
            for book in sorted(books, key=lambda b: b["position"]):
                cur = con.execute(
                    "INSERT INTO books(code, position, testament, slug,"
                    " title, subtitle, range) VALUES (?,?,?,?,?,?,?)",
                    (book["code"], book["position"], book["testament"],
                     book["slug"], book["title"], book.get("subtitle"),
                     book.get("range")))
                book_id = cur.lastrowid
                for ch in book["chapters"]:
                    cur = con.execute(
                        "INSERT INTO chapters(book_id, number) VALUES (?,?)",
                        (book_id, ch["number"]))
                    chapter_id = cur.lastrowid
                    n_chapters += 1
                    hpos = 0
                    for block in ch["blocks"]:
                        if block["type"] == "verse":
                            norm = fold(block["text"])
                            con.execute(
                                "INSERT INTO verses(chapter_id, number,"
                                " text, text_norm) VALUES (?,?,?,?)",
                                (chapter_id, block["number"],
                                 block["text"], norm))
                            n_verses += 1
                            for tok in set(tokenize(norm)):
                                postings.setdefault(tok, set()).add(chapter_id)
                        else:
                            con.execute(
                                "INSERT INTO headings(chapter_id, position,"
                                " text) VALUES (?,?,?)",
                                (chapter_id, hpos, block["text"]))
                            hpos += 1
                            n_headings += 1
                            for tok in set(tokenize(fold(block["text"]))):
                                postings.setdefault(tok, set()).add(chapter_id)
            meta_rows = [
                ("generator", "tools/build_db.py (phase 2)"),
                ("generated_utc",
                 datetime.now(timezone.utc).isoformat()),
                ("total_books", str(len(books))),
                ("total_chapters", str(n_chapters)),
                ("total_verses", str(n_verses)),
                ("total_headings", str(n_headings)),
                ("verse_of_day_rule",
                 "(days_since_unix_epoch % total_chapters) + 1"
                 "  (result is a chapters.id)"),
            ]
            con.executemany("INSERT INTO meta(key, value) VALUES (?,?)",
                            meta_rows)
    except sqlite3.Error as e:
        print("error: insert failed: %s" % e, file=sys.stderr)
        return 1

    # Self-check: FTS index must mirror the verses table exactly.
    fts_count = con.execute("SELECT COUNT(*) FROM verses_fts").fetchone()[0]
    con.close()
    if fts_count != n_verses:
        print("error: FTS rows (%d) != verses (%d)"
              % (fts_count, n_verses), file=sys.stderr)
        return 1

    index = {
        "meta": {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "generator": "tools/build_db.py (phase 2)",
            "total_chapters": n_chapters,
            "tokens": len(postings),
            "min_token_len": MIN_TOKEN_LEN,
        },
        "index": {tok: sorted(ids) for tok, ids in postings.items()},
    }
    idx_path = os.path.join(args.out, "search_index.json")
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(index, f, separators=(",", ":"))
        f.write("\n")

    print("books=%d chapters=%d verses=%d headings=%d tokens=%d"
          % (len(books), n_chapters, n_verses, n_headings, len(postings)))
    print("sqlite=%d bytes index=%d bytes"
          % (os.path.getsize(db_path), os.path.getsize(idx_path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

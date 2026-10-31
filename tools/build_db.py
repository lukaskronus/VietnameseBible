#!/usr/bin/env python3
"""Build queryable artifacts from build/bible.json (Phase 1 output).

Phase 2 of the static-site pipeline. Stdlib only.

    python tools/build_db.py --json build/bible.json --out build

Outputs (under --out):
    bible.sqlite        normalized relational DB + FTS5 full-text index
    search/manifest.json  shard count + index metadata for the client
    search/sNN.json       256 shards: word / adjacent-pair -> verse codes

Schema:
    books(id, code, position, testament, slug, title, subtitle, range)
    chapters(id, book_id, number)       -- ids run 1..N in canon order
    verses(id, chapter_id, number, text, text_en, text_norm)
      text = Vietnamese (primary), text_en = English NASB (secondary),
      text_norm = folded "vi + en" for bilingual search
    verses_fts                          -- FTS5 over text_norm, trigger-kept
    meta(key, value)

Text folding (diacritic-insensitive search). The Phase 3 client MUST
implement exactly this:
    NFD normalize -> strip combining marks -> d/Ð to d -> lowercase,
    tokens = [a-z0-9]+ runs of length >= 2.

Verse-of-the-day shuffle (implemented client-side in Phase 3):
    chapter_id = ((701 * days_since_unix_epoch + 123) % total_chapters) + 1
(total_chapters is stored in meta and in search/manifest.json.)

Client search index. A multi-word query matches any ADJACENT word pair from
the query, in order ("tinh yeu thuong" -> "tinh yeu" OR "yeu thuong"), not
an intersection of loose words. The index therefore holds folded single
words and folded adjacent pairs, each mapping to verse codes:

    code = chapter_id * 1000 + verse_number      (verse_number < 1000)

Per-language tokenisation: Vietnamese and English bigrams never cross the
language boundary. Keys hash to shards with FNV-1a 32-bit modulo 256; the
same hash and the fold/tokenise rules live in tools/static/fold.js and the
two sides are diffed in CI.

Exit 0 on success, 1 on any error.
NOTE: executed by GitHub Actions (cloud) only.
Local machines are code storage; do not run builds on them.
"""

import argparse
import base64
import json
import os
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone

TOKEN = re.compile(r"[a-z0-9]+")
MIN_TOKEN_LEN = 2  # single letters stay out of the client index (see above)
SHARD_COUNT = 256
CODE_BASE = 1000  # verse code = chapter_id * CODE_BASE + verse_number

# Brute-force checks run against these after the shards are written.
SAMPLE_QUERIES = (
    "tinh yeu thuong",
    "su song doi doi",
    "duc tin",
    "love",
    "God so loved the world",
)

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
  text_en TEXT NOT NULL DEFAULT '',
  text_norm TEXT NOT NULL
);
CREATE INDEX idx_verses_chapter ON verses(chapter_id);
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
    # 1925 XML uses U+00D0/U+00F0 for Đ/đ in places; fold those too.
    for a, b in (("đ", "d"), ("Đ", "D"), ("ð", "d"), ("Ð", "D")):
        norm = norm.replace(a, b)
    return norm.lower()


def tokenize(folded):
    return [t for t in TOKEN.findall(folded) if len(t) >= MIN_TOKEN_LEN]


def shard_id(key):
    """FNV-1a 32-bit of the ASCII key, modulo SHARD_COUNT.

    tools/static/fold.js (shardId) must compute the same value; CI diffs the
    two through tools/check_fold.py and tools/check_fold.js.
    """
    h = 2166136261
    for ch in key:
        h = (h ^ ord(ch)) & 0xFFFFFFFF
        h = (h * 16777619) & 0xFFFFFFFF
    return h % SHARD_COUNT


def encode_codes(codes):
    """LEB128 delta encoding of a sorted verse-code list."""
    out = bytearray()
    prev = 0
    for code in codes:
        n = code - prev
        prev = code
        while True:
            b = n & 0x7F
            n >>= 7
            out.append(b | 0x80 if n else b)
            if not n:
                break
    return bytes(out)


def decode_codes(raw):
    codes = []
    acc = 0
    n = 0
    shift = 0
    for b in raw:
        n |= (b & 0x7F) << shift
        if b & 0x80:
            shift += 7
            continue
        acc += n
        codes.append(acc)
        n = 0
        shift = 0
    return codes


def query_keys(text):
    """Index keys a client query looks up (mirrors keys_for() in search.js)."""
    toks = tokenize(fold(text))
    if not toks:
        return []
    if len(toks) == 1:
        return [toks[0]]
    return [toks[i] + " " + toks[i + 1] for i in range(len(toks) - 1)]


def verse_matches(vi_toks, en_toks, keys):
    """Brute-force oracle for the pair rule, used by the build self-check."""
    if len(keys) == 1 and " " not in keys[0]:
        return keys[0] in vi_toks or keys[0] in en_toks
    pairs = set(zip(vi_toks, vi_toks[1:])) | set(zip(en_toks, en_toks[1:]))
    return any(tuple(k.split(" ")) in pairs for k in keys)


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

    postings = {}  # key (word or adjacent pair) -> verse codes, ascending
    sample_keys = {q: query_keys(q) for q in SAMPLE_QUERIES}
    sample_hits = {q: set() for q in SAMPLE_QUERIES}
    n_chapters = n_verses = 0
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
                    for block in ch["blocks"]:
                        if block["type"] != "verse":
                            # Only verse blocks exist since the headings
                            # plumbing was removed; fail cleanly, not with a
                            # KeyError traceback, if a parser starts emitting
                            # another kind.
                            raise ValueError(
                                "non-verse block %r in book %s chapter %d"
                                % (block.get("type"), book["slug"],
                                   ch["number"]))
                        vi = block.get("vi", block.get("text", ""))
                        en = block.get("en", "")
                        vi = vi or ""
                        en = en or ""
                        if not 0 < block["number"] < CODE_BASE:
                            raise ValueError(
                                "verse number %r out of range in %s %d"
                                % (block["number"], book["slug"], ch["number"]))
                        norm = fold(vi + "\n" + en)
                        con.execute(
                            "INSERT INTO verses(chapter_id, number,"
                            " text, text_en, text_norm)"
                            " VALUES (?,?,?,?,?)",
                            (chapter_id, block["number"],
                             vi, en, norm))
                        n_verses += 1
                        code = chapter_id * CODE_BASE + block["number"]
                        vi_toks = tokenize(fold(vi))
                        en_toks = tokenize(fold(en))
                        keys = set(vi_toks) | set(en_toks)
                        keys.update(a + " " + b
                                    for a, b in zip(vi_toks, vi_toks[1:]))
                        keys.update(a + " " + b
                                    for a, b in zip(en_toks, en_toks[1:]))
                        for key in keys:
                            postings.setdefault(key, []).append(code)
                        for q, qk in sample_keys.items():
                            if qk and verse_matches(vi_toks, en_toks, qk):
                                sample_hits[q].add(code)
            meta_rows = [
                ("generator", "tools/build_db.py (phase 2)"),
                ("generated_utc",
                 datetime.now(timezone.utc).isoformat()),
                ("total_books", str(len(books))),
                ("total_chapters", str(n_chapters)),
                ("total_verses", str(n_verses)),
                ("verse_of_day_rule",
                 "((701 * days_since_unix_epoch + 123) % total_chapters) + 1"
                 "  (result is a chapters.id)"),
            ]
            con.executemany("INSERT INTO meta(key, value) VALUES (?,?)",
                            meta_rows)
    except (sqlite3.Error, ValueError) as e:
        print("error: insert failed: %s" % e, file=sys.stderr)
        return 1

    # Self-check: FTS index must mirror the verses table exactly.
    fts_count = con.execute("SELECT COUNT(*) FROM verses_fts").fetchone()[0]
    con.close()
    if fts_count != n_verses:
        print("error: FTS rows (%d) != verses (%d)"
              % (fts_count, n_verses), file=sys.stderr)
        return 1

    # ---- client search shards ----------------------------------------------
    expect = {key: sorted(codes) for key, codes in postings.items()}
    search_dir = os.path.join(args.out, "search")
    os.makedirs(search_dir, exist_ok=True)
    shards = {}
    for key in sorted(expect):
        sid = shard_id(key)
        shards.setdefault(sid, {})[key] = (
            base64.b64encode(encode_codes(expect[key])).decode("ascii"))
    shard_bytes = 0
    for sid in sorted(shards):
        path = os.path.join(search_dir, "s%02x.json" % sid)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(shards[sid], f, separators=(",", ":"))
            f.write("\n")
        shard_bytes += os.path.getsize(path)
    manifest = {
        "version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "generator": "tools/build_db.py (phase 2)",
        "shard_count": SHARD_COUNT,
        "min_token_len": MIN_TOKEN_LEN,
        "code_base": CODE_BASE,
        "total_chapters": n_chapters,
        "total_verses": n_verses,
        "keys": len(expect),
    }
    with open(os.path.join(search_dir, "manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(manifest, f, separators=(",", ":"))
        f.write("\n")
    # Reused output directories: drop the old chapter-level index.
    stale = os.path.join(args.out, "search_index.json")
    if os.path.exists(stale):
        os.remove(stale)

    # Self-check 1: every shard must decode back to the postings we built.
    decoded = {}
    for sid in sorted(shards):
        path = os.path.join(search_dir, "s%02x.json" % sid)
        with open(path, encoding="utf-8") as f:
            for key, b64 in json.load(f).items():
                decoded[key] = decode_codes(base64.b64decode(b64))
    if decoded != expect:
        print("error: shard round-trip mismatch", file=sys.stderr)
        return 1

    # Self-check 2: pair-rule results must equal a brute-force scan.
    for q in SAMPLE_QUERIES:
        found = set()
        for key in sample_keys[q]:
            found.update(expect.get(key, ()))
        if found != sample_hits[q]:
            print("error: query %r shard lookup (%d) != brute force (%d)"
                  % (q, len(found), len(sample_hits[q])), file=sys.stderr)
            return 1

    print("books=%d chapters=%d verses=%d keys=%d shards=%d"
          % (len(books), n_chapters, n_verses, len(expect), len(shards)))
    print("sqlite=%d bytes search=%d bytes"
          % (os.path.getsize(db_path), shard_bytes))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Parse bilingual Bible sources data/viet.sqlite3 + data/nasb.sqlite3.

Phase 1 of the static-site pipeline. Stdlib only.

    python tools/parse_bible.py --data data --out build

Reads the two SQLite sources (same schema: books / chapters / verses /
metadata) and merges them into one bilingual canon:

    data/viet.sqlite3   Vietnamese (1934 Vietnamese Bible) -- primary
    data/nasb.sqlite3   English (NASB) -- secondary

Both DBs share 66 books, 1189 chapters, OSIS book codes and chapter ids
1..N in canon order. Verses are keyed by (book_osis, chapter, verse) where
the REAL `verse` column encodes chapter.verse (e.g. 1.001 = ch 1 v 1).

Outputs (under --out):
    bible.json              structured books -> chapters -> blocks
    validation_report.md    per-book counts plus every anomaly found

Block model (bilingual, backward compatible):
    {"type": "heading", "text": <en>, "vi": "", "en": <en>}
    {"type": "verse", "number": N, "text": <vi>, "vi": <vi>, "en": <en>}
`text` always mirrors the Vietnamese side so Phase 2/3 readers that only
look at `text` keep working.

Headings: viet.sqlite3 chapters carry no headings; NASB chapters.content
HTML carries <h3>/<h4> pericopes. They are extracted (tags stripped) and
attached before the verse whose `class="text BOOK-CH-V"` marker they wrap.
Vietnamese heading text is unavailable, so heading blocks carry en only.

Daily rotation is unchanged (client-side):
    chapter_id = (days_since_unix_epoch % total_chapters) + 1
The home page now renders that chapter bilingually (VI + EN).

Exit code: 0 = parsed (warnings, if any, are listed in the report),
           1 = hard errors (missing DBs, empty books, zero chapters).

NOTE: this script is executed by GitHub Actions (cloud) only.
Local machines are code storage; do not run builds on them.
"""

import argparse
import html as htmlmod
import json
import os
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone

# Legacy row count of data/bible.sql, used as an informational cross-check only.
LEGACY_CHAPTER_COUNT = 1189

TESTAMENT_LABELS = {"OT": "Cựu Ước", "NT": "Tân Ước"}

HEADING_RE = re.compile(r"<h[34][^>]*>(.*?)</h[34]>", re.S)
TAG_RE = re.compile(r"<[^>]+>")
VERSE_REF_RE = re.compile(r'class="text [A-Za-z0-9]+-(\d+)-(\d+)')
WS_RE = re.compile(r"\s+")


def slugify(text):
    """ASCII slug for URLs, e.g. 'I Cô-rinh-tô' -> '1-co-rinh-to'."""
    norm = unicodedata.normalize("NFD", text)
    norm = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    norm = norm.replace("đ", "d").replace("Đ", "D")
    slug = re.sub(r"[^a-z0-9]+", "-", norm.lower()).strip("-")
    for roman, digit in (("iii-", "3-"), ("ii-", "2-"), ("i-", "1-")):
        if slug.startswith(roman):
            slug = digit + slug[len(roman):]
            break
    return slug or "book"


def decode_verse(vfloat):
    """Split REAL chapter.verse (e.g. 1.001, 1.01, 119.176) -> (ch, v)."""
    ch = int(vfloat)
    v = int(round((float(vfloat) - ch) * 1000))
    return ch, v


def clean_verse_text(text):
    """Collapse newlines/whitespace; strip trailing newlines."""
    if text is None:
        return ""
    return WS_RE.sub(" ", text.replace("\r", " ").replace("\n", " ")).strip()


def strip_heading_prefix(en_text, headings_for_verse):
    """Remove a duplicated pericope heading ('The Creation\\nIn the...').

    NASB verses.unformatted repeats the <h3> heading as the first line.
    If the first line matches a heading attached to this verse, drop it and
    keep the real verse text; remaining newlines become spaces.
    """
    if not en_text:
        return ""
    parts = en_text.split("\n")
    if len(parts) > 1:
        first = WS_RE.sub(" ", parts[0]).strip()
        for h in headings_for_verse:
            if first == h or first.lower() == h.lower():
                return clean_verse_text("\n".join(parts[1:]))
        # Fallback heuristic: a short first line with no sentence-ending
        # punctuation that exactly matches a heading elsewhere in the
        # chapter is also a heading repeat. (Poetry lines end with
        # punctuation or are long, so they survive this check.)
        if len(first) <= 80 and not re.search(r"[.!?;:\"”’]$", first):
            for h in headings_for_verse:
                if first == h:
                    return clean_verse_text("\n".join(parts[1:]))
    return clean_verse_text(en_text)


def extract_headings(nasb_content):
    """Return {verse_number: [heading, ...]} for one NASB chapter HTML.

    Each <h3>/<h4> wraps a <span class="text BOOK-CH-V"> marker that tells
    which verse it precedes. Tags are stripped, entities unescaped.
    """
    out = {}
    if not nasb_content:
        return out
    for m in HEADING_RE.finditer(nasb_content):
        inner = m.group(1)
        text = htmlmod.unescape(TAG_RE.sub("", inner))
        text = WS_RE.sub(" ", text).strip()
        if not text:
            continue
        vm = VERSE_REF_RE.search(m.group(0))
        vnum = int(vm.group(2)) if vm else None
        out.setdefault(vnum, []).append(text)
    return out


def load_db(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    books = [dict(r) for r in
             con.execute("SELECT number, osis, human, chapters FROM books "
                         "ORDER BY number")]
    chapters = [dict(r) for r in
                con.execute("SELECT id, reference_osis, reference_human, "
                            "content FROM chapters ORDER BY id")]
    verses = {}
    for r in con.execute("SELECT book, verse, unformatted FROM verses"):
        ch, v = decode_verse(r["verse"])
        verses[(r["book"], ch, v)] = r["unformatted"] or ""
    meta = {r["name"]: r["value"] for r in
            con.execute("SELECT name, value FROM metadata")}
    con.close()
    return books, chapters, verses, meta


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default="data", help="source data directory")
    ap.add_argument("--viet", default=None, help="path to viet.sqlite3 "
                    "(default: <data>/viet.sqlite3)")
    ap.add_argument("--nasb", default=None, help="path to nasb.sqlite3 "
                    "(default: <data>/nasb.sqlite3)")
    ap.add_argument("--out", default="build", help="output directory (CI only)")
    args = ap.parse_args()

    viet_path = args.viet or os.path.join(args.data, "viet.sqlite3")
    nasb_path = args.nasb or os.path.join(args.data, "nasb.sqlite3")
    errors, warnings = [], []
    for label, p in (("viet", viet_path), ("nasb", nasb_path)):
        if not os.path.isfile(p):
            errors.append("%s source not found: %s" % (label, p))

    if errors:
        for e in errors:
            print("error: %s" % e, file=sys.stderr)
        return 1

    vb, vch, vverses, vmeta = load_db(viet_path)
    nb, nch, nverses, nmeta = load_db(nasb_path)

    # ---- canon consistency checks -------------------------------------
    if len(vb) != 66 or len(nb) != 66:
        errors.append("expected 66 books, got viet=%d nasb=%d"
                      % (len(vb), len(nb)))
    v_osis = [b["osis"] for b in vb]
    n_osis = [b["osis"] for b in nb]
    if v_osis != n_osis:
        errors.append("book order mismatch between viet and nasb sources")
        warnings.append("viet order: %s" % ",".join(v_osis))
        warnings.append("nasb order: %s" % ",".join(n_osis))
    for v, n in zip(vb, nb):
        if v["chapters"] != n["chapters"]:
            warnings.append(
                "%s: chapter count differs (viet=%d nasb=%d)"
                % (v["osis"], v["chapters"], n["chapters"]))
    if len(vch) != len(nch):
        errors.append("chapter count differs (viet=%d nasb=%d)"
                      % (len(vch), len(nch)))

    n_map = {(b["osis"]): b for b in nb}
    nasb_ch_content = {r["reference_osis"]: r["content"] for r in nch}

    books, report_rows = [], []
    total_chapters = total_verses = total_headings = 0
    missing_vi = missing_en = 0
    seen_slugs = {}

    for pos, v in enumerate(vb, start=1):
        osis = v["osis"]
        n = n_map.get(osis, {})
        title_vi = v["human"]
        title_en = n.get("human", osis)
        slug = slugify(title_vi or osis)
        if slug in seen_slugs:
            warnings.append("%s: duplicate slug %r (also %s); suffixing"
                            % (osis, slug, seen_slugs[slug]))
            slug = "%s-%d" % (slug, pos)
        seen_slugs[slug] = osis

        book = {
            "code": osis,
            "position": pos,
            "testament": "OT" if pos <= 39 else "NT",
            "slug": slug,
            "title": title_vi,          # backward compat: VI primary
            "title_vi": title_vi,
            "title_en": title_en,
            "subtitle": None,
            "range": None,
            "chapters": [],
        }
        n_chapters = int(v["chapters"])
        for ch_no in range(1, n_chapters + 1):
            ref = "%s.%d" % (osis, ch_no)
            headings = extract_headings(nasb_ch_content.get(ref, ""))
            # Headings keyed None (no verse marker) attach to chapter start.
            pending_start = headings.pop(None, [])
            blocks = []
            for h in pending_start:
                blocks.append({"type": "heading", "text": h,
                               "vi": "", "en": h})
                total_headings += 1
            # Verse numbers present in either source for this chapter.
            vnums = sorted({vv for (b, c, vv) in vverses if b == osis
                            and c == ch_no} |
                           {vv for (b, c, vv) in nverses if b == osis
                            and c == ch_no})
            if not vnums:
                errors.append("%s ch %d: no verses in either source" % (osis,
                                                                        ch_no))
                continue
            for vnum in vnums:
                vi_raw = vverses.get((osis, ch_no, vnum))
                en_raw = nverses.get((osis, ch_no, vnum))
                if vi_raw is None:
                    missing_vi += 1
                    warnings.append(
                        "%s %d:%d: missing in viet.sqlite3 "
                        "(EN only)" % (osis, ch_no, vnum))
                if en_raw is None:
                    missing_en += 1
                    warnings.append(
                        "%s %d:%d: missing in nasb.sqlite3 "
                        "(VI only)" % (osis, ch_no, vnum))
                for h in headings.get(vnum, []):
                    blocks.append({"type": "heading", "text": h,
                                   "vi": "", "en": h})
                    total_headings += 1
                vi = clean_verse_text(vi_raw or "")
                en = strip_heading_prefix(en_raw or "",
                                          headings.get(vnum, []))
                blocks.append({"type": "verse", "number": vnum,
                               "text": vi, "vi": vi, "en": en})
                total_verses += 1
            book["chapters"].append({"number": ch_no, "blocks": blocks})
            total_chapters += 1

        books.append(book)
        n_v = sum(1 for c in book["chapters"] for b in c["blocks"]
                  if b["type"] == "verse")
        n_h = sum(1 for c in book["chapters"] for b in c["blocks"]
                  if b["type"] == "heading")
        report_rows.append((pos, osis, title_vi, title_en,
                            book["testament"], len(book["chapters"]),
                            n_v, n_h, "ok"))

    if not books or total_chapters == 0 or total_verses == 0:
        errors.append("no books/chapters/verses parsed")

    os.makedirs(args.out, exist_ok=True)
    payload = {
        "meta": {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "generator": "tools/parse_bible.py (phase 1, bilingual sqlite)",
            "books": len(books),
            "total_chapters": total_chapters,
            "total_verses": total_verses,
            "total_headings": total_headings,
            "testaments": TESTAMENT_LABELS,
            "sources": {
                "vi": "%s (%s)" % (vmeta.get("fullname", "?"),
                                   vmeta.get("name", "?")),
                "en": "%s (%s)" % (nmeta.get("fullname", "?"),
                                   nmeta.get("name", "?")),
            },
            "missing_vi": missing_vi,
            "missing_en": missing_en,
        },
        "books": books,
    }
    json_path = os.path.join(args.out, "bible.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # ---- legacy txt note ------------------------------------------------
    legacy_txt = sorted(f for f in os.listdir(args.data)
                        if f.endswith(".txt")) if os.path.isdir(args.data) \
        else []
    legacy_note = ("Legacy data/*.txt + list.txt are no longer read; "
                   "sources are viet.sqlite3 + nasb.sqlite3.")

    # ---- validation report ----------------------------------------------
    rep_path = os.path.join(args.out, "validation_report.md")
    with open(rep_path, "w", encoding="utf-8") as f:
        f.write("# Validation report (Phase 1 parser, bilingual)\n\n")
        f.write("Generated: %s UTC\n\n"
                % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))
        f.write("## Summary\n\n")
        f.write("- Books parsed: %d\n" % len(books))
        f.write("- Chapters: %d (legacy bible.sql: %d) %s\n" % (
            total_chapters, LEGACY_CHAPTER_COUNT,
            "MATCH" if total_chapters == LEGACY_CHAPTER_COUNT
            else "**DIFFERS - investigate**"))
        f.write("- Verses: %d, Headings: %d\n"
                % (total_verses, total_headings))
        f.write("- Missing VI: %d, Missing EN: %d\n"
                % (missing_vi, missing_en))
        f.write("- Warnings: %d, Errors: %d\n\n"
                % (len(warnings), len(errors)))
        f.write("Sources: VI `%s`, EN `%s`.\n\n"
                % (vmeta.get("fullname", "?"), nmeta.get("fullname", "?")))
        f.write("%s\n\n" % legacy_note)
        if legacy_txt:
            f.write("Legacy txt files present but ignored: %d "
                    "(e.g. %s).\n\n"
                    % (len(legacy_txt), ", ".join(legacy_txt[:5])))
        if errors:
            f.write("## Errors\n\n")
            for e in errors:
                f.write("- %s\n" % e)
            f.write("\n")
        if warnings:
            f.write("## Warnings\n\n")
            for w in warnings[:200]:
                f.write("- %s\n" % w)
            if len(warnings) > 200:
                f.write("- ... and %d more\n" % (len(warnings) - 200))
            f.write("\n")
        f.write("## Books\n\n")
        f.write("| # | osis | title_vi | title_en | test. | ch | verses |"
                " headings | status |\n")
        f.write("|---|------|----------|----------|-------|----|--------|"
                "----------|--------|\n")
        for row in report_rows:
            f.write("| %s | %s | %s | %s | %s | %s | %s | %s | %s |\n" % row)

    print("books=%d chapters=%d verses=%d headings=%d "
          "missing_vi=%d missing_en=%d warnings=%d errors=%d"
          % (len(books), total_chapters, total_verses, total_headings,
             missing_vi, missing_en, len(warnings), len(errors)))
    print("wrote %s and %s" % (json_path, rep_path))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

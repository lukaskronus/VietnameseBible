#!/usr/bin/env python3
"""Parse the Vietnamese Bible sources in data/*.txt into structured JSON.

Phase 1 of the static-site pipeline. Stdlib only.

    python tools/parse_bible.py --data data --out build

Reads data/list.txt for canonical book order, then parses each book file:

    line 1:            book title
    following lines:   optional subtitle, optional "(range)" line
                       (single-chapter books omit both; some books
                       have a blank line instead of a subtitle)
    then per chapter:  bare chapter-number line, blank line,
                       section headings, and verse lines ("N text").

Outputs (under --out):
    bible.json              structured books -> chapters -> blocks
    validation_report.md    per-book counts plus every anomaly found

Exit code: 0 = parsed (warnings, if any, are listed in the report),
           1 = hard errors (missing files, empty books, zero chapters).

NOTE: this script is executed by GitHub Actions (cloud) only.
Local machines are code storage; do not run builds on them.
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

BARE_NUMBER = re.compile(r"^(\d+)$")
VERSE_LINE = re.compile(r"^(\d+)\s+(.+)$")

# Legacy row count of data/bible.sql, used as an informational cross-check only.
LEGACY_CHAPTER_COUNT = 1189

TESTAMENT_LABELS = {"OT": "C\u1ef1u \u01af\u1edbc", "NT": "T\u00e2n \u01af\u1edbc"}


def slugify(text):
    """ASCII slug for URLs, e.g. 'I C\u00f4-rinh-t\u00f4' -> '1-co-rinh-to'."""
    norm = unicodedata.normalize("NFD", text)
    norm = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    norm = norm.replace("\u0111", "d").replace("\u0110", "D")
    slug = re.sub(r"[^a-z0-9]+", "-", norm.lower()).strip("-")
    for roman, digit in (("iii-", "3-"), ("ii-", "2-"), ("i-", "1-")):
        if slug.startswith(roman):
            slug = digit + slug[len(roman):]
            break
    return slug or "book"


def last_verse_number(blocks):
    for b in reversed(blocks):
        if b["type"] == "verse":
            return b["number"]
    return 0


def parse_book(path, code, position):
    """Parse one book file. Returns (book_dict, warnings, errors)."""
    warnings, errors = [], []
    with open(path, encoding="utf-8-sig") as f:
        lines = [ln.rstrip() for ln in f.read().splitlines()]

    if not lines or all(ln.strip() == "" for ln in lines):
        errors.append("file is empty")
        return None, warnings, errors

    title = lines[0].strip()
    if not title:
        errors.append("line 1: missing book title")

    # ---- header scan: subtitle / (range), both optional -----------------
    subtitle, range_text = None, None
    i = 1
    n = len(lines)
    while i < n:
        s = lines[i].strip()
        if s == "":
            i += 1
            continue
        if BARE_NUMBER.match(s) or VERSE_LINE.match(s):
            break  # chapter content starts; header is over
        if s.startswith("("):
            if range_text is None:
                range_text = s
            else:
                warnings.append("line %d: duplicate range line: %r" % (i + 1, s))
            i += 1
            continue
        if subtitle is None:
            subtitle = s
            i += 1
            continue
        warnings.append("line %d: unexpected header line: %r" % (i + 1, s))
        i += 1

    # ---- chapter / verse scan -------------------------------------------
    chapters = []

    def new_chapter(num, line_no, reason):
        if reason:
            warnings.append("line %d: %s" % (line_no, reason))
        chapters.append({"number": num, "blocks": []})

    while i < n:
        s = lines[i].strip()
        line_no = i + 1
        if s == "":
            i += 1
            continue
        m_bare = BARE_NUMBER.match(s)
        if m_bare:
            num = int(m_bare.group(1))
            expected = chapters[-1]["number"] + 1 if chapters else 1
            reason = None
            if num != expected:
                reason = "chapter marker %d, expected %d" % (num, expected)
            new_chapter(num, line_no, reason)
            i += 1
            continue
        m_verse = VERSE_LINE.match(s)
        if m_verse and not chapters:
            # Content before any chapter marker: assume chapter 1 follows.
            new_chapter(1, line_no,
                        "content before first chapter marker; assuming chapter 1")
        if not chapters:
            warnings.append("line %d: orphan line before first chapter: %r"
                            % (line_no, s))
            i += 1
            continue
        if m_verse:
            vnum = int(m_verse.group(1))
            vtext = m_verse.group(2)
            prev = last_verse_number(chapters[-1]["blocks"])
            if vnum == 1 and prev >= 1:
                # Verse numbers restart: chapter marker must be missing.
                new_chapter(chapters[-1]["number"] + 1, line_no,
                            "verse 1 after verse %d; assuming missing "
                            "chapter marker" % prev)
                prev = 0
            if vnum != prev + 1:
                warnings.append(
                    "line %d: ch %d verse %d follows verse %d"
                    % (line_no, chapters[-1]["number"], vnum, prev))
            chapters[-1]["blocks"].append(
                {"type": "verse", "number": vnum, "text": vtext})
            i += 1
            continue
        chapters[-1]["blocks"].append({"type": "heading", "text": s})
        i += 1

    if not chapters:
        errors.append("no chapters found")
        return None, warnings, errors

    verse_count = sum(1 for c in chapters for b in c["blocks"]
                      if b["type"] == "verse")
    if verse_count == 0:
        errors.append("chapters found but zero verses parsed")

    book = {
        "code": code,
        "position": position,
        "testament": "OT" if position <= 39 else "NT",
        "slug": slugify(title or code),
        "title": title,
        "subtitle": subtitle,
        "range": range_text,
        "chapters": chapters,
    }
    return book, warnings, errors


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default="data", help="source data directory")
    ap.add_argument("--out", default="build", help="output directory (CI only)")
    args = ap.parse_args()

    list_path = os.path.join(args.data, "list.txt")
    if not os.path.isfile(list_path):
        print("error: %s not found" % list_path, file=sys.stderr)
        return 1
    with open(list_path, encoding="utf-8-sig") as f:
        codes = [ln.strip() for ln in f.read().splitlines() if ln.strip()]

    books, report_rows = [], []
    total_chapters = total_verses = total_headings = 0
    total_warnings, total_errors = 0, []
    seen_slugs = {}

    for pos, code in enumerate(codes, start=1):
        path = os.path.join(args.data, code + ".txt")
        if not os.path.isfile(path):
            total_errors.append("%s.txt: file listed but missing" % code)
            report_rows.append((pos, code, "-", "-", 0, 0, 0, "MISSING FILE"))
            continue
        book, warnings, errors = parse_book(path, code, pos)
        if book is None:
            total_errors.extend("%s.txt: %s" % (code, e) for e in errors)
            report_rows.append((pos, code, "-", "-", 0, 0, 0,
                                "; ".join(errors)))
            continue
        if book["slug"] in seen_slugs:
            errors.append("duplicate slug %r (also %s)" % (
                book["slug"], seen_slugs[book["slug"]]))
        else:
            seen_slugs[book["slug"]] = code
        total_errors.extend("%s.txt: %s" % (code, e) for e in errors)
        issues = warnings + errors
        total_warnings += len(warnings)
        n_ch = len(book["chapters"])
        n_v = sum(1 for c in book["chapters"] for b in c["blocks"]
                  if b["type"] == "verse")
        n_h = sum(1 for c in book["chapters"] for b in c["blocks"]
                  if b["type"] == "heading")
        total_chapters += n_ch
        total_verses += n_v
        total_headings += n_h
        books.append(book)
        report_rows.append((pos, code, book["title"], book["testament"],
                            n_ch, n_v, n_h,
                            "%d issue(s)" % len(issues) if issues else "ok"))
        for msg in issues:
            report_rows.append(("", "", code + ".txt", msg,
                                "", "", "", ""))

    # Files present on disk but absent from list.txt.
    for name in sorted(os.listdir(args.data)):
        if name.endswith(".txt") and name != "list.txt":
            stem = name[:-4]
            if stem not in codes:
                total_errors.append("%s: present but not in list.txt" % name)

    os.makedirs(args.out, exist_ok=True)
    payload = {
        "meta": {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "generator": "tools/parse_bible.py (phase 1)",
            "books": len(books),
            "total_chapters": total_chapters,
            "total_verses": total_verses,
            "total_headings": total_headings,
            "testaments": TESTAMENT_LABELS,
        },
        "books": books,
    }
    json_path = os.path.join(args.out, "bible.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # ---- validation report ----------------------------------------------
    rep_path = os.path.join(args.out, "validation_report.md")
    with open(rep_path, "w", encoding="utf-8") as f:
        f.write("# Validation report (Phase 1 parser)\n\n")
        f.write("Generated: %s UTC\n\n"
                % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))
        f.write("## Summary\n\n")
        f.write("- Books parsed: %d / %d listed\n" % (len(books), len(codes)))
        f.write("- Chapters: %d (legacy bible.sql: %d) %s\n" % (
            total_chapters, LEGACY_CHAPTER_COUNT,
            "MATCH" if total_chapters == LEGACY_CHAPTER_COUNT
            else "**DIFFERS - investigate**"))
        f.write("- Verses: %d, Headings: %d\n"
                % (total_verses, total_headings))
        f.write("- Warnings: %d, Errors: %d\n\n"
                % (total_warnings, len(total_errors)))
        if total_errors:
            f.write("## Errors\n\n")
            for e in total_errors:
                f.write("- %s\n" % e)
            f.write("\n")
        f.write("## Books\n\n")
        f.write("| # | file | title | test. | ch | verses | headings | status |\n")
        f.write("|---|------|-------|-------|----|--------|----------|--------|\n")
        for row in report_rows:
            if row[0] == "" and row[1] == "":
                continue  # issue detail rows go to the next section
            f.write("| %s | %s | %s | %s | %s | %s | %s | %s |\n" % row)
        f.write("\n## Issue details\n\n")
        any_issue = False
        for row in report_rows:  # detail rows collected per book above
            if row[0] == "" and row[1] == "":
                f.write("- `%s`: %s\n" % (row[2], row[3]))
                any_issue = True
        if not any_issue:
            f.write("None. All files parsed cleanly.\n")

    print("books=%d chapters=%d verses=%d headings=%d warnings=%d errors=%d"
          % (len(books), total_chapters, total_verses, total_headings,
             total_warnings, len(total_errors)))
    print("wrote %s and %s" % (json_path, rep_path))
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())

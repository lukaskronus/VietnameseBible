#!/usr/bin/env python3
"""Parse bilingual Bible sources in data/xml/*.xml into structured JSON.

Phase 1 of the static-site pipeline. Stdlib only.

    python tools/parse_bible.py --data data/xml --out build
    (``--data`` may also point at ``data/``; the xml/ subdirectory is
    searched automatically.)

Reads the six XML translations (same schema everywhere)::

    <bible> -> <testament name> -> <book number=1..66>
        -> <chapter number> -> <verse number>text</verse>

and merges them into one canon keyed by (book, chapter, verse). Verse
numbers are unioned across translations; a version missing a verse
(e.g. 3 John 15 in some editions) yields an empty string on that side.

Book titles are canonical lists in this file (the XML carries numbers
only): Vietnamese titles as approved by the maintainer, standard English
titles for the secondary side. Slugs derive from the Vietnamese titles.

Outputs (under --out):
    bible.json              structured books -> chapters -> blocks
    validation_report.md    per-translation counts plus every anomaly found

Block model (backward compatible with Phase 2/3):
    {"type": "verse", "number": N,
     "text": <vi default>, "vi": <vi default>, "en": <en default>,
     "texts": {<code>: <text or ""> for all six translations}}

Default pair: vi1925 (1925-VI) + ennasb (NASB 1995). The pairing switcher
(daily widget + book reader) serves the other four from data/tr/ sets
built in Phase 3.

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
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# Legacy row count of data/bible.sql, used as an informational cross-check only.
LEGACY_CHAPTER_COUNT = 1189

TESTAMENT_LABELS = {"OT": "Cựu Ước", "NT": "Tân Ước"}

DEFAULT_VI = "vi1925"
DEFAULT_EN = "ennasb"

# code -> (filename, short UI label, language). Copyright lines are harvested
# from each file's <bible> header at parse time (see meta.translations).
TRANSLATIONS = {
    "vi1925": ("VietnameseBible.xml", "Tiếng Việt 1925", "vi"),
    "vinvb": ("VietnameseNVBBible.xml", "Bản Dịch Mới 2002", "vi"),
    "vivie": ("VietnameseVIEBible.xml", "Hiệu Đính 2010", "vi"),
    "enesv": ("EnglishESVBible.xml", "ESV 2016", "en"),
    "ennasb": ("EnglishNASBBible.xml", "NASB 1995", "en"),
    "ennet": ("EnglishNETBible.xml", "NET 2005", "en"),
}

OSIS = ("Gen Exod Lev Num Deut Josh Judg Ruth 1Sam 2Sam 1Kgs 2Kgs 1Chr "
        "2Chr Ezra Neh Esth Job Ps Prov Eccl Song Isa Jer Lam Ezek Dan Hos "
        "Joel Amos Obad Jonah Mic Nah Hab Zeph Hag Zech Mal Matt Mark Luke "
        "John Acts Rom 1Cor 2Cor Gal Eph Phil Col 1Thess 2Thess 1Tim 2Tim "
        "Titus Phlm Heb Jas 1Pet 2Pet 1John 2John 3John Jude Rev").split()

VI_TITLES = (
    "Sáng thế Ký", "Xuất Ê-díp-tô Ký", "Lê-vi Ký", "Dân-số Ký",
    "Phục truyền Luật lệ Ký", "Giô-suê", "Các Quan Xét", "Ru-tơ",
    "I Sa-mu-ên", "II Sa-mu-ên", "I Các Vua", "II Các Vua", "I Sử ký",
    "II Sử ký", "E-xơ-ra", "Nê-hê-mi", "Ê-xơ-tê", "Gióp", "Thi thiên",
    "Châm ngôn", "Truyền đạo", "Nhã ca", "Ê-sai", "Giê-rê-mi", "Ca-thương",
    "Ê-xê-chi-ên", "Đa-ni-ên", "Ô-sê", "Giô-ên", "A-mốt", "Áp-đia",
    "Giô-na", "Mi-chê", "Na-hum", "Ha-ba-cúc", "Sô-phô-ni", "A-ghê",
    "Xa-cha-ri", "Ma-la-chi", "Ma-thi-ơ", "Mác", "Lu-ca", "Giăng",
    "Công-vụ các Sứ-đồ", "Rô-ma", "I Cô-rinh-tô", "II Cô-rinh-tô",
    "Ga-la-ti", "Ê-phê-sô", "Phi-líp", "Cô-lô-se", "I Tê-sa-lô-ni-ca",
    "II Tê-sa-lô-ni-ca", "I Ti-mô-thê", "II Ti-mô-thê", "Tít",
    "Phi-lê-môn", "Hê-bơ-rơ", "Gia-cơ", "I Phi-e-rơ", "II Phi-e-rơ",
    "I Giăng", "II Giăng", "III Giăng", "Giu-đe", "Khải-huyền",
)

EN_TITLES = (
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua",
    "Judges", "Ruth", "1 Samuel", "2 Samuel", "1 Kings", "2 Kings",
    "1 Chronicles", "2 Chronicles", "Ezra", "Nehemiah", "Esther", "Job",
    "Psalm", "Proverbs", "Ecclesiastes", "Song of Solomon", "Isaiah",
    "Jeremiah", "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel",
    "Amos", "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah",
    "Haggai", "Zechariah", "Malachi", "Matthew", "Mark", "Luke", "John",
    "Acts", "Romans", "1 Corinthians", "2 Corinthians", "Galatians",
    "Ephesians", "Philippians", "Colossians", "1 Thessalonians",
    "2 Thessalonians", "1 Timothy", "2 Timothy", "Titus", "Philemon",
    "Hebrews", "James", "1 Peter", "2 Peter", "1 John", "2 John", "3 John",
    "Jude", "Revelation",
)

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


def clean(text):
    return WS_RE.sub(" ", text or "").strip()


def resolve(path, filename):
    """Find filename under path or path/xml (lets --data be data/ or xml/)."""
    for cand in (os.path.join(path, filename),
                 os.path.join(path, "xml", filename)):
        if os.path.isfile(cand):
            return cand
    return os.path.join(path, filename)


def parse_xml(path, warnings):
    """Return ({(book, ch): {vnum: text}}, header_dict)."""
    verses = {}
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        warnings.append("%s: XML parse error: %s"
                        % (os.path.basename(path), e))
        return {}, {}
    header = dict(root.attrib)
    for t in root.findall("testament"):
        for b in t.findall("book"):
            try:
                bn = int(b.get("number"))
            except (TypeError, ValueError):
                warnings.append("%s: book with bad number %r"
                                % (os.path.basename(path), b.get("number")))
                continue
            for c in b.findall("chapter"):
                try:
                    cn = int(c.get("number"))
                except (TypeError, ValueError):
                    warnings.append("%s: book %d chapter with bad number %r"
                                    % (os.path.basename(path), bn,
                                       c.get("number")))
                    continue
                slot = verses.setdefault((bn, cn), {})
                for v in c.findall("verse"):
                    try:
                        vn = int(v.get("number"))
                    except (TypeError, ValueError):
                        warnings.append(
                            "%s: book %d ch %d verse with bad number %r"
                            % (os.path.basename(path), bn, cn,
                               v.get("number")))
                        continue
                    text = clean("".join(v.itertext()))
                    if vn in slot:
                        warnings.append(
                            "%s: book %d ch %d duplicate verse %d"
                            % (os.path.basename(path), bn, cn, vn))
                    slot[vn] = text
    return verses, header


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default="data/xml",
                    help="source data directory (data/xml or data)")
    ap.add_argument("--out", default="build", help="output directory (CI only)")
    args = ap.parse_args()

    errors, warnings = [], []
    if len(VI_TITLES) != 66 or len(EN_TITLES) != 66 or len(OSIS) != 66:
        errors.append("canonical title tables must each hold 66 entries")
        print("error: %s" % errors[0], file=sys.stderr)
        return 1

    per_tr, headers = {}, {}
    for code, (fn, _label, _lang) in TRANSLATIONS.items():
        path = resolve(args.data, fn)
        if not os.path.isfile(path):
            errors.append("source not found: %s" % path)
            continue
        verses, header = parse_xml(path, warnings)
        per_tr[code] = verses
        headers[code] = header

    if errors:
        for e in errors:
            print("error: %s" % e, file=sys.stderr)
        return 1

    counts = {c: sum(len(v) for v in verses.values())
              for c, verses in per_tr.items()}

    # ---- canon consistency: union of (book, ch) across translations ------
    all_chapters = set()
    for verses in per_tr.values():
        all_chapters.update(verses.keys())
    n_chapters = len(all_chapters)
    for code, verses in per_tr.items():
        missing = sorted(all_chapters - set(verses.keys()))
        for bn, cn in missing[:10]:
            warnings.append("%s: missing whole chapter %d.%d"
                            % (code, bn, cn))
        if len(missing) > 10:
            warnings.append("%s: ... and %d more missing chapters"
                            % (code, len(missing) - 10))

    books, report_rows = [], []
    total_verses = 0
    missing_cells = 0  # translation-chapter-verse slots empty somewhere
    seen_slugs = {}
    tr_meta = {}
    for code, (fn, label, lang) in TRANSLATIONS.items():
        h = headers.get(code, {})
        credit = " ".join(clean(h.get(k, ""))
                          for k in ("translation", "status", "info")).strip()
        tr_meta[code] = {"file": fn, "label": label, "lang": lang,
                         "copyright": credit or label}

    for pos in range(1, 67):
        osis = OSIS[pos - 1]
        title_vi, title_en = VI_TITLES[pos - 1], EN_TITLES[pos - 1]
        slug = slugify(title_vi)
        if slug in seen_slugs:
            warnings.append("%s: duplicate slug %r (also %s); suffixing"
                            % (osis, slug, seen_slugs[slug]))
            slug = "%s-%d" % (slug, pos)
        seen_slugs[slug] = osis

        ch_numbers = sorted(c for (b, c) in all_chapters if b == pos)
        if not ch_numbers:
            errors.append("%s: no chapters in any translation" % osis)
            continue
        # Warn on gaps (1..max expected contiguous).
        if ch_numbers != list(range(1, max(ch_numbers) + 1)):
            warnings.append("%s: non-contiguous chapters: %s..."
                            % (osis, ch_numbers[:8]))
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
        n_v = 0
        for cn in ch_numbers:
            vnums = sorted({vn for code in TRANSLATIONS
                            for vn in per_tr[code].get((pos, cn), {})})
            if not vnums:
                errors.append("%s ch %d: no verses in any translation"
                              % (osis, cn))
                continue
            blocks = []
            for vn in vnums:
                texts = {code: per_tr[code].get((pos, cn), {}).get(vn, "")
                         for code in TRANSLATIONS}
                if any(t == "" for t in texts.values()):
                    missing_cells += 1
                vi = texts[DEFAULT_VI]
                en = texts[DEFAULT_EN]
                if vi == "" or en == "":
                    missing = [c for c, t in texts.items() if t == ""]
                    warnings.append(
                        "%s %d:%d: missing in %s"
                        % (osis, cn, vn, ",".join(missing)))
                blocks.append({"type": "verse", "number": vn,
                               "text": vi, "vi": vi, "en": en,
                               "texts": texts})
                n_v += 1
                total_verses += 1
            book["chapters"].append({"number": cn, "blocks": blocks})
        books.append(book)
        report_rows.append((pos, osis, title_vi, title_en,
                            book["testament"], len(book["chapters"]), n_v,
                            "ok"))

    if not books or n_chapters == 0 or total_verses == 0:
        errors.append("no books/chapters/verses parsed")
    if errors:
        for e in errors:
            print("error: %s" % e, file=sys.stderr)
        return 1

    os.makedirs(args.out, exist_ok=True)
    payload = {
        "meta": {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "generator": "tools/parse_bible.py (phase 1, xml)",
            "books": len(books),
            "total_chapters": n_chapters,
            "total_verses": total_verses,
            "total_headings": 0,
            "testaments": TESTAMENT_LABELS,
            "translations": tr_meta,
            "default_vi": DEFAULT_VI,
            "default_en": DEFAULT_EN,
            "counts": counts,
        },
        "books": books,
    }
    json_path = os.path.join(args.out, "bible.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    # ---- validation report ----------------------------------------------
    rep_path = os.path.join(args.out, "validation_report.md")
    with open(rep_path, "w", encoding="utf-8") as f:
        f.write("# Validation report (Phase 1 parser, xml)\n\n")
        f.write("Generated: %s UTC\n\n"
                % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))
        f.write("## Summary\n\n")
        f.write("- Books parsed: %d\n" % len(books))
        f.write("- Chapters: %d (legacy bible.sql: %d) %s\n" % (
            n_chapters, LEGACY_CHAPTER_COUNT,
            "MATCH" if n_chapters == LEGACY_CHAPTER_COUNT
            else "**DIFFERS - investigate**"))
        f.write("- Verses (union): %d\n" % total_verses)
        for code in TRANSLATIONS:
            f.write("- %s verses: %d\n" % (code, counts.get(code, 0)))
        f.write("- Missing translation slots: %d\n" % missing_cells)
        f.write("- Warnings: %d, Errors: %d\n\n"
                % (len(warnings), len(errors)))
        f.write("Default pair: %s + %s.\n\n" % (DEFAULT_VI, DEFAULT_EN))
        f.write("Sources: `data/xml/` (6 files). "
                "Legacy `data/txt/` and `data/sqlite/` are not read.\n\n")
        if warnings:
            f.write("## Warnings\n\n")
            for w in warnings[:200]:
                f.write("- %s\n" % w)
            if len(warnings) > 200:
                f.write("- ... and %d more\n" % (len(warnings) - 200))
            f.write("\n")
        f.write("## Books\n\n")
        f.write("| # | osis | title_vi | title_en | test. | ch | verses |"
                " status |\n")
        f.write("|---|------|----------|----------|-------|----|--------|"
                "--------|\n")
        for row in report_rows:
            f.write("| %s | %s | %s | %s | %s | %s | %s | %s |\n" % row)

    print("books=%d chapters=%d verses=%d missing_slots=%d "
          "warnings=%d errors=%d"
          % (len(books), n_chapters, total_verses, missing_cells,
             len(warnings), len(errors)))
    print("wrote %s and %s" % (json_path, rep_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())

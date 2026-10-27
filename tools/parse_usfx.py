#!/usr/bin/env python3
"""Parse USFX Bible sources in data/web_version/ into structured JSON.

Phase 1 for public domain web version (Wasmer). Stdlib only.

    python tools/parse_usfx.py --data data/web_version --out build

Reads USFX format from:
    data/web_version/engbsb_usfx/engbsb_usfx.xml (Berean Standard Bible, English)
    data/web_version/vie1934_usfx/vie1934_usfx.xml (Vietnamese 1934)

Outputs same format as parse_bible.py:
    bible.json              structured books -> chapters -> blocks
    validation_report.md

Block model:
    {"type": "verse", "number": N,
     "text": <vi default>, "vi": <vi default>, "en": <en default>,
     "texts": {<code>: <text or ""> for all translations}}

Default pair: vie1934 (Vietnamese 1934) + engbsb (BSB). Both public domain.

Exit code: 0 = parsed, 1 = errors.
NOTE: executed by GitHub Actions (cloud) only.
"""
import argparse
import json
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

LEGACY_CHAPTER_COUNT = 1189

DEFAULT_VI = "vie1934"
DEFAULT_EN = "engbsb"

TRANSLATIONS = {
    "vie1934": ("vie1934_usfx", "Kinh Thanh 1934", "vi"),
    "engbsb": ("engbsb_usfx", "Berean Standard Bible", "en"),
}

OSIS = ("Gen Exod Lev Num Deut Josh Judg Ruth 1Sam 2Sam 1Kgs 2Kgs 1Chr "
        "2Chr Ezra Neh Esth Job Ps Prov Eccl Song Isa Jer Lam Ezek Dan Hos "
        "Joel Amos Obad Jonah Mic Nah Hab Zeph Hag Zech Mal Matt Mark Luke "
        "John Acts Rom 1Cor 2Cor Gal Eph Phil Col 1Thess 2Thess 1Tim 2Tim "
        "Titus Phlm Heb Jas 1Pet 2Pet 1John 2John 3John Jude Rev").split()

# Book titles live only in parse_bible.py (AGENTS.md).  Import them so the
# web_version parser uses the same canonical names as the portable-site parser.
from parse_bible import VI_TITLES, EN_TITLES, TESTAMENT_LABELS

WS_RE = re.compile(r"\s+")

# Elements whose text/interaction is not verse text -- skipped entirely.
SKIP_TAGS = frozenset({
    'id', 'h', 'toc', 'ide', 's', 'b', 'd', 'languageCode', 'it',
    'f', 'fr', 'ft', 'fe', 'note', 'x',
})

USFX_TO_OSIS = {
    "GEN": "Gen", "EXO": "Exod", "LEV": "Lev", "NUM": "Num", "DEU": "Deut",
    "JOS": "Josh", "JDG": "Judg", "RUT": "Ruth", "1SA": "1Sam", "2SA": "2Sam",
    "1KI": "1Kgs", "2KI": "2Kgs", "1CH": "1Chr", "2CH": "2Chr", "EZR": "Ezra",
    "NEH": "Neh", "EST": "Esth", "JOB": "Job", "PSA": "Ps", "PRO": "Prov",
    "ECC": "Eccl", "SNG": "Song", "ISA": "Isa", "JER": "Jer", "LAM": "Lam",
    "EZK": "Ezek", "DAN": "Dan", "HOS": "Hos", "JOL": "Joel", "AMO": "Amos",
    "OBA": "Obad", "JON": "Jonah", "MIC": "Mic", "NAM": "Nah", "HAB": "Hab",
    "ZEP": "Zeph", "HAG": "Hag", "ZEC": "Zech", "MAL": "Mal", "MAT": "Matt",
    "MRK": "Mark", "LUK": "Luke", "JHN": "John", "ACT": "Acts", "ROM": "Rom",
    "1CO": "1Cor", "2CO": "2Cor", "GAL": "Gal", "EPH": "Eph", "PHP": "Phil",
    "COL": "Col", "1TH": "1Thess", "2TH": "2Thess", "1TI": "1Tim", "2TI": "2Tim",
    "TIT": "Titus", "PHM": "Phlm", "HEB": "Heb", "JAS": "Jas", "1PE": "1Pet",
    "2PE": "2Pet", "1JN": "1John", "2JN": "2John", "3JN": "3John", "JUD": "Jude",
    "REV": "Rev",
}


def slugify(text):
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


def parse_usfx_file(path, warnings, code):
    """Parse a USFX file via recursive document-order walk.

    USFX marks verses with self-closing <v> elements; verse text lives
    in sibling elements after <v> (e.g. <w> word tags in engbsb, or
    raw text in vie1934), up to the next <v> or <ve>.  A flat
    book.iter() loses sibling relationships, so we walk the tree
    manually, tracking the current chapter/verse and accumulating
    every text node into the active verse.
    """
    verses = {}
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except ET.ParseError as e:
        warnings.append("%s: XML parse error: %s" % (os.path.basename(path), e))
        return {}

    for book in root.findall('book'):
        usfx_id = book.get('id')
        if usfx_id not in USFX_TO_OSIS:
            warnings.append("%s: unknown book %s" % (os.path.basename(path), usfx_id))
            continue
        osis = USFX_TO_OSIS[usfx_id]
        try:
            bn = OSIS.index(osis) + 1
        except ValueError:
            continue

        state = {'ch': None, 'vn': None, 'buf': []}

        def flush():
            if state['ch'] is not None and state['vn'] is not None:
                text = clean(''.join(state['buf']))
                slot = verses.setdefault((bn, state['ch']), {})
                if state['vn'] in slot:
                    warnings.append("%s: book %d ch %d duplicate verse %d"
                                    % (os.path.basename(path), bn,
                                       state['ch'], state['vn']))
                slot[state['vn']] = text
            state['buf'] = []
            state['vn'] = None

        def walk(elem):
            tag = elem.tag
            if tag == 'c':
                flush()
                try:
                    state['ch'] = int(elem.get('id'))
                except (TypeError, ValueError):
                    state['ch'] = None
                return
            if tag == 'v':
                flush()
                try:
                    state['vn'] = int(elem.get('id'))
                except (TypeError, ValueError):
                    state['vn'] = None
                if elem.text:
                    state['buf'].append(elem.text)
                return
            if tag == 've':
                flush()
                return
            if tag in SKIP_TAGS:
                return  # skip footnotes, headings, metadata -- recurse no further

            if elem.text:
                state['buf'].append(elem.text)
            for child in elem:
                walk(child)
                if child.tail:
                    state['buf'].append(child.tail)

        walk(book)
        flush()

    return verses


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default="data/web_version",
                    help="source data directory (web_version)")
    ap.add_argument("--out", default="build", help="output directory (CI only)")
    args = ap.parse_args()

    errors, warnings = [], []
    if len(OSIS) != 66:
        errors.append("canonical OSIS table must hold 66 entries")
        print("error: %s" % errors[0], file=sys.stderr)
        return 1

    per_tr = {}
    tr_meta = {}

    for code, (dir_name, label, lang) in TRANSLATIONS.items():
        xml_path = os.path.join(args.data, dir_name, f"{code}_usfx.xml")
        if not os.path.isfile(xml_path):
            errors.append("source not found: %s" % xml_path)
            continue

        copyright = label
        vernacular_path = os.path.join(args.data, dir_name,
                                       f"{code}-VernacularAdditional.xml")
        if os.path.isfile(vernacular_path):
            try:
                tree = ET.parse(vernacular_path)
                root = tree.getroot()
                cp = root.find('copyright')
                if cp is not None and cp.text:
                    copyright = clean(cp.text)
            except Exception:
                pass

        verses = parse_usfx_file(xml_path, warnings, code)
        per_tr[code] = verses
        tr_meta[code] = {"file": os.path.basename(xml_path), "label": label,
                         "lang": lang, "copyright": copyright}

    if errors:
        for e in errors:
            print("error: %s" % e, file=sys.stderr)
        return 1

    counts = {c: sum(len(v) for v in verses.values())
              for c, verses in per_tr.items()}

    all_chapters = set()
    for verses in per_tr.values():
        all_chapters.update(verses.keys())
    n_chapters = len(all_chapters)

    books = []
    total_verses = 0
    missing_cells = 0
    seen_slugs = {}

    for pos in range(1, 67):
        osis = OSIS[pos - 1]
        title_vi = VI_TITLES[pos - 1]
        title_en = EN_TITLES[pos - 1]

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

        book = {
            "code": osis,
            "position": pos,
            "testament": "OT" if pos <= 39 else "NT",
            "slug": slug,
            "title": title_vi,
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
                errors.append("%s ch %d: no verses in any translation" % (osis, cn))
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
                    if missing:
                        warnings.append("%s %d:%d: missing in %s"
                                        % (osis, cn, vn, ",".join(missing)))
                blocks.append({"type": "verse", "number": vn,
                               "text": vi, "vi": vi, "en": en,
                               "texts": texts})
                n_v += 1
                total_verses += 1
            book["chapters"].append({"number": cn, "blocks": blocks})
        books.append(book)

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
            "generator": "tools/parse_usfx.py (phase 1, usfx)",
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

    rep_path = os.path.join(args.out, "validation_report.md")
    with open(rep_path, "w", encoding="utf-8") as f:
        f.write("# Validation report (Phase 1 parser, usfx)\n\n")
        f.write("Generated: %s UTC\n\n"
                % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))
        f.write("## Summary\n\n")
        f.write("- Books parsed: %d\n" % len(books))
        f.write("- Chapters: %d\n" % n_chapters)
        f.write("- Verses (union): %d\n" % total_verses)
        for code in TRANSLATIONS:
            f.write("- %s verses: %d\n" % (code, counts.get(code, 0)))
        f.write("- Missing translation slots: %d\n" % missing_cells)
        f.write("- Warnings: %d, Errors: %d\n\n"
                % (len(warnings), len(errors)))
        f.write("Default pair: %s + %s (public domain).\n\n"
                % (DEFAULT_VI, DEFAULT_EN))
        f.write("Sources: `data/web_version/` (USFX format).\n\n")
        if warnings:
            f.write("## Warnings\n\n")
            for w in warnings[:200]:
                f.write("- %s\n" % w)
            if len(warnings) > 200:
                f.write("- ... and %d more\n" % (len(warnings) - 200))
            f.write("\n")

    print("books=%d chapters=%d verses=%d missing_slots=%d warnings=%d errors=%d"
          % (len(books), n_chapters, total_verses, missing_cells,
             len(warnings), len(errors)))
    print("wrote %s and %s" % (json_path, rep_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())

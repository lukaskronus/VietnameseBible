#!/usr/bin/env python3
"""Parse public-domain Bible sources in data/web_version/ into structured JSON.

Phase 1 for the Wasmer web version. Stdlib only.

    python tools/parse_web.py --data data/web_version --out build

Inputs are flat files in data/web_version/, one format each:

    vie-cadman.osis.xml   OSIS 2.1.1   Vietnamese 1934     (vie1934)
    eng-bsb.usfx.xml      USFX         Berean Standard Bible (engbsb)
    eng-web.usfx.xml      USFX         World English Bible   (engweb)
    eng-asv.zefania.xml   Zefania XML  American Standard Version (engasv)

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
    # code: (filename, short UI label, language, parser format, copyright line)
    "vie1934": ("vie-cadman.osis.xml", "Kinh Thanh 1934", "vi", "osis",
                "Vietnamese Bible (1934) is in the Public Domain."),
    "engbsb": ("eng-bsb.usfx.xml", "Berean Standard Bible", "en", "usfx",
               "Berean Standard Bible is in the Public Domain."),
    "engweb": ("eng-web.usfx.xml", "World English Bible", "en", "usfx",
               "World English Bible is in the Public Domain."),
    "engasv": ("eng-asv.zefania.xml", "American Standard Version", "en", "zefania",
               "American Standard Version (1901) is in the Public Domain."),
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
    'id', 'h', 'toc', 'ide', 's', 'b', 'languageCode', 'it',
    'f', 'fr', 'ft', 'fe', 'note', 'x',
})

# WEB ships front/back matter and apocrypha outside the 66-book canon;
# skip them silently (they are intentional, not parsing errors).
USFX_IGNORE = frozenset({
    "FRT", "GLO", "TOB", "JDT", "ESG", "WIS", "SIR", "BAR", "LJE", "S3Y",
    "SUS", "BEL", "1MA", "2MA", "1ES", "MAN", "PS2", "3MA", "2ES", "4MA",
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

# OSIS 2.1.1 core namespace (vie-cadman.osis.xml is namespaced).
OSIS_NS = "{http://www.bibletechnologies.net/2003/OSIS/namespace}"


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


def parse_usfx_file(path, warnings):
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
        if usfx_id in USFX_IGNORE:
            continue
        if usfx_id not in USFX_TO_OSIS:
            warnings.append("%s: unknown book %s" % (os.path.basename(path), usfx_id))
            continue
        osis = USFX_TO_OSIS[usfx_id]
        bn = OSIS.index(osis) + 1

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

            # 'd' (speaker-label paragraph) is NOT skipped: engbsb puts
            # real verse text inside <d> (e.g. Zech 12:1). Text outside
            # an open verse (<v> seen) is a label/preamble and is dropped
            # so labels never bleed into the previous verse.
            if elem.text and state['vn'] is not None:
                state['buf'].append(elem.text)
            for child in elem:
                try:
                    walk(child)
                    if child.tail and state['vn'] is not None:
                        state['buf'].append(child.tail)
                except Exception:
                    # Skip problematic child elements but continue parsing
                    pass

        walk(book)
        flush()

    return verses


def parse_osis_file(path, warnings):
    """Parse an OSIS 2.1.1 file (namespaced): div/chapter/verse tree.

    Structure: <div osisID='Gen' type='book'> -> <chapter osisID='Gen.1'>
    -> <verse osisID='Gen.1.1'>text</verse>.  Book position comes from
    the canon OSIS tuple; chapter/verse numbers from the osisID suffixes.
    """
    verses = {}
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        warnings.append("%s: XML parse error: %s" % (os.path.basename(path), e))
        return {}
    root = tree.getroot()

    for div in root.iter(OSIS_NS + 'div'):
        if div.get('type') != 'book':
            continue
        book_id = div.get('osisID')
        if book_id not in OSIS:
            warnings.append("%s: unknown book %s" % (os.path.basename(path), book_id))
            continue
        bn = OSIS.index(book_id) + 1

        for chapter in div.findall(OSIS_NS + 'chapter'):
            try:
                ch = int(chapter.get('osisID', '').rsplit('.', 1)[-1])
            except ValueError:
                warnings.append("%s: bad chapter osisID %r"
                                % (os.path.basename(path), chapter.get('osisID')))
                continue
            slot = verses.setdefault((bn, ch), {})
            for verse in chapter.iter(OSIS_NS + 'verse'):
                try:
                    vn = int(verse.get('osisID', '').rsplit('.', 1)[-1])
                except ValueError:
                    warnings.append("%s: bad verse osisID %r (book %d ch %d)"
                                    % (os.path.basename(path), verse.get('osisID'),
                                       bn, ch))
                    continue
                text = clean(''.join(verse.itertext()))
                if vn in slot:
                    warnings.append("%s: book %d ch %d duplicate verse %d"
                                    % (os.path.basename(path), bn, ch, vn))
                slot[vn] = text

    return verses


def parse_zefania_file(path, warnings):
    """Parse a Zefania XML file: BIBLEBOOK bnumber / CHAPTER cnumber / VERS vnumber.

    bnumber 1..66 is the canon position, matching the OSIS tuple order.
    """
    verses = {}
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        warnings.append("%s: XML parse error: %s" % (os.path.basename(path), e))
        return {}
    root = tree.getroot()

    for book in root.iter('BIBLEBOOK'):
        try:
            bn = int(book.get('bnumber'))
        except (TypeError, ValueError):
            warnings.append("%s: missing bnumber at %s"
                            % (os.path.basename(path), book.get('bname')))
            continue
        if not 1 <= bn <= 66:
            warnings.append("%s: book %d out of canon (skipped)"
                            % (os.path.basename(path), bn))
            continue

        for chapter in book.findall('CHAPTER'):
            try:
                ch = int(chapter.get('cnumber'))
            except (TypeError, ValueError):
                warnings.append("%s: book %d bad cnumber %r"
                                % (os.path.basename(path), bn, chapter.get('cnumber')))
                continue
            slot = verses.setdefault((bn, ch), {})
            for verse in chapter.findall('VERS'):
                try:
                    vn = int(verse.get('vnumber'))
                except (TypeError, ValueError):
                    warnings.append("%s: book %d ch %d bad vnumber %r"
                                    % (os.path.basename(path), bn, ch,
                                       verse.get('vnumber')))
                    continue
                text = clean(''.join(verse.itertext()))
                if vn in slot:
                    warnings.append("%s: book %d ch %d duplicate verse %d"
                                    % (os.path.basename(path), bn, ch, vn))
                slot[vn] = text

    return verses


PARSERS = {
    "usfx": parse_usfx_file,
    "osis": parse_osis_file,
    "zefania": parse_zefania_file,
}


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

    for code, (fname, label, lang, fmt, copyright_) in TRANSLATIONS.items():
        xml_path = os.path.join(args.data, fname)
        if not os.path.isfile(xml_path):
            errors.append("source not found: %s" % xml_path)
            continue

        verses = PARSERS[fmt](xml_path, warnings)
        per_tr[code] = verses
        tr_meta[code] = {"file": fname, "label": label,
                         "lang": lang, "copyright": copyright_}

    if errors:
        for e in errors:
            print("error: %s" % e, file=sys.stderr)
        return 1

    counts = {c: sum(len(v) for v in verses.values())
              for c, verses in per_tr.items()}

    # A source file that fails to parse (truncated download) returns {} --
    # hard-fail instead of publishing a site with blank verses for one edition.
    for code, n in counts.items():
        if not n:
            errors.append("%s: parsed 0 verses" % code)
    if errors:
        for e in errors:
            print("error: %s" % e, file=sys.stderr)
        return 1

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
            "generator": "tools/parse_web.py (phase 1, web_version)",
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
        f.write("# Validation report (Phase 1 parser, web_version)\n\n")
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
        f.write("Sources: `data/web_version/` (OSIS / USFX / Zefania, "
                "public domain).\n\n")
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

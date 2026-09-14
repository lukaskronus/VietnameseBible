#!/usr/bin/env python3
"""Generate the static bilingual (VI+EN) Bible website (Phase 3).

Stdlib only.
    python tools/build_site.py --json build/bible.json \
        --index build/search_index.json --out site \
        --base-url https://example.com/ [--base-path ""]

Inputs: Phase 1 bible.json (bilingual text + order), Phase 2 search_index.json.
Output: complete static site/ and site.zip -- upload to any static host.

URL scheme: / = home (bilingual verse of the day + book grid),
/<slug>/ = book, /<slug>/<n>/ = chapter, /tim-kiem/ = search.
Chapter ids 1..N follow canon order; the client verse-of-the-day is:
    chapter_id = (days_since_unix_epoch % total_chapters) + 1
per-chapter JSON under data/ch/<id>.json feeds it (each verse carries
both "vi" and "en"; the home widget renders both).

NOTE: executed by GitHub Actions (cloud) only.
Local machines are code storage; do not run builds on them.
"""

import argparse
import html
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from string import Template

SITE_NAME = "Kinh Thánh Song Ngữ Việt–Anh"
SITE_DESC = "Kinh Thánh song ngữ Việt–Anh (1934 Vietnamese Bible + NASB)"

TOOLS_DIR = Path(__file__).resolve().parent
STATIC_DIR = TOOLS_DIR / "static"
TEMPLATE_DIR = TOOLS_DIR / "templates"

PAGE_TPL = Template((TEMPLATE_DIR / "page.html").read_text("utf-8"))
CSS_SRC = (STATIC_DIR / "style.css").read_text("utf-8")
APP_JS_SRC = (STATIC_DIR / "app.js").read_text("utf-8")
SEARCH_JS_SRC = (STATIC_DIR / "search.js").read_text("utf-8")
DAILY_JS_SRC = (STATIC_DIR / "daily.js").read_text("utf-8")


def minify_css(s):
    s = re.sub(r'/\*.*?\*/', '', s, flags=re.S)
    s = re.sub(r'\s*\n\s*', '\n', s)
    s = re.sub(r'\n+', '\n', s)
    return s.strip()


def minify_js(s):
    s = re.sub(r'//.*$', '', s, flags=re.M)
    s = re.sub(r'\s*\n\s*', ' ', s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def esc(text):
    return html.escape(text or "", quote=True)


def page(bp, title, desc, body, scripts=(), nav_extra=""):
    head_extra = "".join(
        '<script src="%s/assets/%s" defer></script>' % (bp, s)
        for s in scripts)
    return PAGE_TPL.substitute(
        bp=bp, title=esc(title), desc=esc(desc),
        body=body, head_extra=head_extra,
        site_name=esc(SITE_NAME), nav_extra=nav_extra)


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", required=True, help="Phase 1 bible.json")
    ap.add_argument("--index", required=True, help="Phase 2 search_index.json")
    ap.add_argument("--out", default="site", help="output directory (CI only)")
    ap.add_argument("--base-url", default="https://example.com/",
                    help="absolute site URL, used for sitemap.xml")
    ap.add_argument("--base-path", default="",
                    help="subpath prefix if not served from domain root")
    args = ap.parse_args()

    for p in (args.json, args.index):
        if not os.path.isfile(p):
            print("error: %s not found" % p, file=sys.stderr)
            return 1
    with open(args.json, encoding="utf-8") as f:
        payload = json.load(f)
    books = payload.get("books")
    if not books:
        print("error: no books in %s" % args.json, file=sys.stderr)
        return 1

    bp = "/" + args.base_path.strip("/")
    if bp == "/":
        bp = ""
    out = args.out
    base_url = (args.base_url or "https://example.com/").rstrip("/") + "/"
    root = (base_url + bp.strip("/")).rstrip("/") + "/"
    if "example.com" in base_url:
        print("notice: --base-url is a placeholder; sitemap.xml URLs "
              "need the real domain", file=sys.stderr)

    # ---- canon-ordered chapter map: id -> {slug, n, book} -----------------
    def btitle(b):
        return b.get("title_vi") or b.get("title", "")
    def btitle_en(b):
        return b.get("title_en") or ""
    idmap = []  # index i == chapter id i+1
    for book in sorted(books, key=lambda b: b["position"]):
        for ch in book["chapters"]:
            idmap.append({"slug": book["slug"], "n": ch["number"],
                          "book": btitle(book),
                          "book_en": btitle_en(book)})
    total = len(idmap)

    # ---- nav dropdown HTML ------------------------------------------------
    def dd_menu(items):
        links = "".join(
            "<a href=\"%s/%s/\">%s</a>" % (bp, b["slug"], esc(btitle(b)))
            for b in sorted(items, key=lambda b: b["position"]))
        return '<div class="dd-menu">%s</div>' % links

    ot_books = [b for b in books if b["testament"] == "OT"]
    nt_books = [b for b in books if b["testament"] != "OT"]
    nav_dd = ("<div class=\"dd\">C\u1ef1u \u01af\u1edbc%s</div>"
              "<div class=\"dd\">T\u00e2n \u01af\u1edbc%s</div>"
              % (dd_menu(ot_books), dd_menu(nt_books)))

    def url_of(cid):
        c = idmap[cid - 1]
        return "%s/%s/%d/" % (bp, c["slug"], c["n"])

    def label_of(cid):
        c = idmap[cid - 1]
        return "%s %d" % (c["book"], c["n"])

    def label_bi(c):
        if c.get("book_en"):
            return "%s %d · %s %d" % (c["book"], c["n"],
                                      c["book_en"], c["n"])
        return "%s %d" % (c["book"], c["n"])

    # ---- shared assets (minified for output) --------------------------------
    write(os.path.join(out, "assets", "style.css"), minify_css(CSS_SRC))
    write(os.path.join(out, "assets", "app.js"), minify_js(APP_JS_SRC))
    write(os.path.join(out, "assets", "search.js"), minify_js(SEARCH_JS_SRC))
    write(os.path.join(out, "assets", "daily.js"), minify_js(DAILY_JS_SRC))
    with open(args.index, encoding="utf-8") as f:
        write(os.path.join(out, "data", "search_index.json"), f.read())
    write(os.path.join(out, "data", "chapters.json"),
          json.dumps([{"id": i + 1, "slug": c["slug"], "n": c["n"],
                       "book": c["book"], "book_en": c.get("book_en", "")}
                      for i, c in enumerate(idmap)],
                     ensure_ascii=False, separators=(",", ":")) + "\n")

    # ---- chapter + book pages ---------------------------------------------
    sitemap_urls = [root, root + "tim-kiem/"]
    cid = 0
    for book in sorted(books, key=lambda b: b["position"]):
        title_vi = btitle(book)
        title_en = btitle_en(book)
        for ch in book["chapters"]:
            cid += 1
            blocks_html, blocks_json = [], []

            for b in ch["blocks"]:
                if b["type"] == "heading":
                    h = b.get("en") or b.get("text", "")
                    blocks_html.append("<h2 class=\"sec\">%s</h2>"
                                       % esc(h))
                    blocks_json.append({"t": "h", "x": h,
                                        "vi": b.get("vi", ""),
                                        "en": h})
                else:
                    vi = b.get("vi", b.get("text", ""))
                    en = b.get("en", "")
                    pair = (
                        '<div class="verse-pair">'
                        '<p class="reading vi">'
                        "<sup id=\"c%dv%d\">%d</sup>%s</p>"
                        % (ch["number"], b["number"], b["number"],
                           esc(vi)))
                    if en:
                        pair += (
                            '<p class="reading en" lang="en">'
                            "<sup>%d</sup>%s</p>"
                            % (b["number"], esc(en)))
                    pair += "</div>"
                    blocks_html.append(pair)
                    blocks_json.append({"t": "v", "n": b["number"],
                                        "x": vi, "vi": vi, "en": en})
            pn = "<nav class=\"pn\">"
            if cid > 1:
                pn += "<a href=\"%s\">&#8249; %s</a>" % (url_of(cid - 1),
                                                         esc(label_of(cid - 1)))
            else:
                pn += "<span class=\"empty\"></span>"
            if cid < total:
                pn += "<a href=\"%s\">%s &#8250;</a>" % (url_of(cid + 1),
                                                         esc(label_of(cid + 1)))
            else:
                pn += "<span class=\"empty\"></span>"
            pn += "</nav>"
            sub = ""
            if book.get("subtitle"):
                sub += "<p>%s</p>" % esc(book["subtitle"])
            if book.get("range"):
                sub += "<p class=\"crumb\">%s</p>" % esc(book["range"])
            if title_en:
                sub += ("<p class=\"crumb\" lang=\"en\">%s</p>"
                        % esc(title_en))
            h1 = "%s %d" % (title_vi, ch["number"])
            h1_bi = h1 if not title_en else "%s · %s %d" % (
                h1, title_en, ch["number"])
            body = ("<p class=\"crumb\"><a href=\"%s/\">%s</a> / "
                    "<a href=\"%s/%s/\">%s</a></p>\n"
                    "<div class=\"chapter-meta\"><h1>%s</h1>\n%s</div>\n%s\n%s"
                    % (bp, esc(SITE_NAME), bp, book["slug"],
                       esc(title_vi), esc(h1_bi),
                       sub, "\n".join(blocks_html), pn))
            write(os.path.join(out, book["slug"], str(ch["number"]),
                               "index.html"),
                  page(bp, "%s | %s" % (h1_bi, SITE_NAME),
                       h1_bi, body, ("app.js",), nav_dd))
            sitemap_urls.append(root + "%s/%d/" % (book["slug"],
                                                      ch["number"]))
            write(os.path.join(out, "data", "ch", str(cid) + ".json"),
                  json.dumps({"id": cid, "book": title_vi,
                              "book_en": title_en,
                              "slug": book["slug"], "n": ch["number"],
                              "blocks": blocks_json},
                             ensure_ascii=False, separators=(",", ":")) + "\n")

        # book page (after its chapters so counts are known)
        lis = "".join(
            "<li><a href=\"%s/%s/%d/\">%d</a></li>"
            % (bp, book["slug"], c["number"], c["number"])
            for c in book["chapters"])
        sub = ""
        if book.get("subtitle"):
            sub += "<p>%s</p>" % esc(book["subtitle"])
        if book.get("range"):
            sub += "<p class=\"crumb\">%s</p>" % esc(book["range"])
        if title_en:
            sub += ("<p class=\"crumb\" lang=\"en\">%s</p>"
                    % esc(title_en))
        h1_book = title_vi if not title_en else "%s · %s" % (
            title_vi, title_en)
        body = ("<p class=\"crumb\"><a href=\"%s/\">%s</a></p>\n"
                "<div class=\"chapter-meta\"><h1>%s</h1>\n%s</div>\n"
                "<ol class=\"chaps\">%s</ol>"
                % (bp, esc(SITE_NAME), esc(h1_book), sub, lis))
        write(os.path.join(out, book["slug"], "index.html"),
              page(bp, "%s | %s" % (h1_book, SITE_NAME),
                   h1_book, body, ("app.js",), nav_dd))
        sitemap_urls.append(root + book["slug"] + "/")

    # ---- home -------------------------------------------------------------
    # Daily = deterministic rotation over 1189 chapters, rendered bilingually.
    first_book = sorted(books, key=lambda b: b["position"])[0]
    home = ("<section id=\"daily\"><p class=\"kicker\">"
            "Song ngữ Việt–Anh · Mỗi ngày một đoạn</p>\n"
            "<h2 id=\"daily-title\">\u2026</h2>\n"
            "<div id=\"daily-text\"><p>\u0110ang t\u1ea3i\u2026</p></div>\n"
            "<p><a id=\"daily-link\" href=\"#\">"
            "\u0110\u1ecdc c\u1ea3 \u0111o\u1ea1n &#8594;</a></p>\n"
            "<noscript><p><a href=\"%s/%s/1/\">"
            "%s 1</a></p></noscript></section>"
            % (bp, first_book["slug"], esc(btitle(first_book))))
    write(os.path.join(out, "index.html"),
          page(bp, SITE_NAME, SITE_DESC,
               home, ("app.js", "daily.js"), nav_dd))

    # ---- search -----------------------------------------------------------
    search_body = ("<div class=\"chapter-meta\"><h1>T&igrave;m ki&#7871;m</h1></div>\n"
                   "<form id=\"search-form\" class=\"search\">"
                   "<input id=\"q\" name=\"q\" autocomplete=\"off\" "
                   "placeholder=\"V&iacute; d&#7909;: Gi&ecirc;-h&ocirc;-va\">"
                   "<button type=\"submit\">T&igrave;m</button></form>\n"
                   "<div id=\"results\"></div>")
    write(os.path.join(out, "tim-kiem", "index.html"),
          page(bp, "T\u00ecm ki\u1ebfm | %s" % SITE_NAME,
               "T\u00ecm ki\u1ebfm Kinh Th\u00e1nh", search_body,
               ("app.js", "search.js"), nav_dd))

    # ---- sitemap / robots / 404 -------------------------------------------
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sm = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
          "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n")
    for u in sitemap_urls:
        sm += ("<url><loc>%s</loc><lastmod>%s</lastmod></url>\n"
               % (esc(u), today))
    sm += "</urlset>\n"
    write(os.path.join(out, "sitemap.xml"), sm)
    write(os.path.join(out, "robots.txt"),
          "User-agent: *\nAllow: /\nSitemap: %ssitemap.xml\n" % root)
    write(os.path.join(out, "404.html"),
          page(bp, "Kh\u00f4ng t\u00ecm th\u1ea5y | %s" % SITE_NAME, "",
               "<h1>404</h1><p>Trang b\u1ea1n t\u00ecm kh\u00f4ng t\u1ed3n "
               "t\u1ea1i. <a href=\"%s/\">V\u1ec1 trang ch\u1ee7</a>.</p>" % bp,
               ("app.js",), nav_dd))

    # ---- zip ---------------------------------------------------------------
    zip_path = out + ".zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root_dir, dirs, files in os.walk(out):
            for f in files:
                fp = os.path.join(root_dir, f)
                arcname = os.path.relpath(fp, out)
                zf.write(fp, arcname)

    n_files = sum(len(fs) for _, _, fs in os.walk(out))
    print("books=%d chapters=%d files=%d zip=%s" % (len(books), total,
                                                     n_files, zip_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())

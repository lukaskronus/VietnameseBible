#!/usr/bin/env python3
"""Generate the static bilingual (VI+EN) Bible website (Phase 3).

Stdlib only.
    python tools/build_site.py --json build/bible.json \
        --index build/search_index.json --out site \
        --base-url https://example.com/ [--base-path ""]

Inputs: Phase 1 bible.json (bilingual text + order), Phase 2 search_index.json.
Output: complete static site/ and site.zip -- upload to any static host.

URL scheme: / = home (pair-switchable verse of the day + book grid),
/<slug>/ = book split reader (default-pair chapter 1 embedded, chapters
and translations load via book.js + pair.js),
/<slug>/<n>/ = chapter (default pair, baked), /tim-kiem/ = search.
Chapter ids 1..N follow canon order; the client verse-of-the-day is:
    chapter_id = (days_since_unix_epoch % total_chapters) + 1
per-translation chapter JSON under data/tr/<code>/ch/<id>.json feeds the
switchable views (each verse carries its number and text; the client
merges one VI file with one EN file).

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

SITE_NAME = "Kinh Thánh Song Ngữ Việt - Anh"
SITE_DESC = ("Kinh Thánh song ngữ Việt - Anh "
             "(1925, Bản Dịch Mới, Hiệu Đính 2010, ESV, NASB, NET)")

TOOLS_DIR = Path(__file__).resolve().parent
STATIC_DIR = TOOLS_DIR / "static"
TEMPLATE_DIR = TOOLS_DIR / "templates"

PAGE_TPL = Template((TEMPLATE_DIR / "page.html").read_text("utf-8"))
CSS_SRC = (STATIC_DIR / "style.css").read_text("utf-8")
APP_JS_SRC = (STATIC_DIR / "app.js").read_text("utf-8")
SEARCH_JS_SRC = (STATIC_DIR / "search.js").read_text("utf-8")
DAILY_JS_SRC = (STATIC_DIR / "daily.js").read_text("utf-8")
BOOK_JS_SRC = (STATIC_DIR / "book.js").read_text("utf-8")
PAIR_JS_SRC = (STATIC_DIR / "pair.js").read_text("utf-8")


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
    meta = payload.get("meta", {})
    translations = meta.get("translations", {})
    default_vi = meta.get("default_vi", "vi1925")
    default_en = meta.get("default_en", "ennasb")
    if default_vi not in translations or default_en not in translations:
        print("error: default pair missing from translations meta",
              file=sys.stderr)
        return 1

    def pair_picker():
        """VI/EN translation switcher (daily widget + book reader)."""
        def opts(lang, default):
            return "".join(
                "<option value=\"%s\"%s>%s</option>"
                % (code, " selected" if code == default else "",
                   esc(translations[code].get("label", code)))
                for code in translations
                if translations[code].get("lang") == lang)
        return (
            "<div class=\"pair-picker\">\n"
            "<label>Bản tiếng Việt\n"
            "<select id=\"pair-vi\">%s</select></label>\n"
            "<label>Bản tiếng Anh\n"
            "<select id=\"pair-en\">%s</select></label>\n"
            "</div>" % (opts("vi", default_vi), opts("en", default_en)))

    def license_section():
        items = "".join(
            "<li><strong>%s</strong> — %s</li>"
            % (esc(translations[code].get("label", code)),
               esc(translations[code].get("copyright", "")))
            for code in translations)
        return (
            "<section class=\"license\">\n"
            "<p class=\"kicker\">Bản quyền bản dịch</p>\n"
            "<ul>%s</ul>\n"
            "<p>Trang web phi thương mại, không quảng cáo. "
            "Mọi bản dịch thuộc về chủ sở hữu bản quyền tương ứng; "
            "xin tôn trọng điều khoản sử dụng của từng bản dịch.</p>\n"
            "</section>" % items)

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
    nav_dd = ("<div class=\"dd\">Cựu Ước%s</div>"
              "<div class=\"dd\">Tân Ước%s</div>"
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
    write(os.path.join(out, "assets", "book.js"), minify_js(BOOK_JS_SRC))
    write(os.path.join(out, "assets", "pair.js"), minify_js(PAIR_JS_SRC))
    with open(args.index, encoding="utf-8") as f:
        write(os.path.join(out, "data", "search_index.json"), f.read())
    write(os.path.join(out, "data", "chapters.json"),
          json.dumps([{"id": i + 1, "slug": c["slug"], "n": c["n"],
                       "book": c["book"], "book_en": c.get("book_en", "")}
                      for i, c in enumerate(idmap)],
                     ensure_ascii=False, separators=(",", ":")) + "\n")

    def render_blocks(ch_number, blocks):
        """Render bilingual verse-pair HTML for one chapter (default pair).

        Verses empty in BOTH default sides (e.g. 3 John 15, absent from
        1925-VI and NASB-XML) are skipped in the baked default view; they
        remain in the per-translation sets for other pairings.
        """
        html_parts = []
        for b in blocks:
            if b.get("type") == "heading":
                h = b.get("en") or b.get("text", "")
                html_parts.append("<h2 class=\"sec\">%s</h2>" % esc(h))
            else:
                vi = b.get("vi", b.get("text", ""))
                en = b.get("en", "")
                if vi == "" and en == "":
                    continue
                pair = (
                    '<div class="verse-pair">'
                    '<p class="reading vi">'
                    "<sup id=\"c%dv%d\">%d</sup>%s</p>"
                    % (ch_number, b["number"], b["number"], esc(vi)))
                if en:
                    pair += (
                        '<p class="reading en" lang="en">'
                        "<sup>%d</sup>%s</p>"
                        % (b["number"], esc(en)))
                pair += "</div>"
                html_parts.append(pair)
        return html_parts

    # ---- chapter + book pages ---------------------------------------------
    sitemap_urls = [root, root + "tim-kiem/"]
    cid = 0
    for book in sorted(books, key=lambda b: b["position"]):
        title_vi = btitle(book)
        title_en = btitle_en(book)
        book_cids = []  # (chapter number, chapter id) for the side pane
        for ch in book["chapters"]:
            cid += 1
            book_cids.append((ch["number"], cid))
            blocks_html = render_blocks(ch["number"], ch["blocks"])
            pn = "<nav class=\"pn\">"
            if cid > 1:
                pn += "<a href=\"%s\">‹ %s</a>" % (url_of(cid - 1),
                                                  esc(label_of(cid - 1)))
            else:
                pn += "<span class=\"empty\"></span>"
            if cid < total:
                pn += "<a href=\"%s\">%s ›</a>" % (url_of(cid + 1),
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
            # Per-translation chapter JSON: data/tr/<code>/ch/<id>.json.
            # The pairing switcher (daily + book reader) fetches one VI
            # file and one EN file and merges them client-side.
            for code, tr in translations.items():
                lang = tr.get("lang")
                tblocks = [{"t": "v", "n": b["number"],
                            "x": (b.get("texts", {}).get(code, "")
                                  if b.get("type") != "heading"
                                  else (b.get("en") or b.get("text", "")))}
                           for b in ch["blocks"]]
                write(os.path.join(out, "data", "tr", code, "ch",
                                   str(cid) + ".json"),
                      json.dumps({"id": cid,
                                  "book": (title_vi if lang == "vi"
                                           else title_en),
                                  "slug": book["slug"], "n": ch["number"],
                                  "blocks": tblocks},
                                 ensure_ascii=False,
                                 separators=(",", ":")) + "\n")

        # book page: split reader -- chapter content left, chapter buttons
        # right. Default-pair chapter 1 is embedded statically; switching
        # chapters or translations loads data/tr/<code>/ch/<id>.json via
        # book.js (no page reload). Buttons are plain links, so the page
        # works without JavaScript too.
        first_html = render_blocks(book["chapters"][0]["number"],
                                   book["chapters"][0]["blocks"])
        first_n = book["chapters"][0]["number"]
        h1_book = title_vi if not title_en else "%s · %s" % (
            title_vi, title_en)
        btns = "".join(
            "<li><a href=\"%s/%s/%d/\" data-cid=\"%d\" data-n=\"%d\"%s>%d</a></li>"
            % (bp, book["slug"], n, c, n,
               " class=\"active\"" if n == first_n else "", n)
            for n, c in book_cids)
        ch1_bi = ("%s %d" % (title_vi, first_n) if not title_en
                  else "%s %d · %s %d" % (title_vi, first_n,
                                          title_en, first_n))
        body = (
            "<div class=\"book-layout\" data-site=\"%s\">\n"
            "<section class=\"book-main\">\n"
            "<p class=\"crumb\"><a href=\"%s/\">%s</a></p>\n"
            "<div class=\"chapter-meta\"><h1>%s</h1>\n%s</div>\n"
            "%s\n"
            "<h2 class=\"bk-ch\" id=\"bk-ch-title\">%s</h2>\n"
            "<div id=\"bk-content\">\n%s\n</div>\n"
            "</section>\n"
            "<aside class=\"book-side\">\n"
            "<p class=\"side-kicker\">%s · Chương</p>\n"
            "<ol class=\"chap-btns\">%s</ol>\n"
            "</aside>\n</div>"
            % (esc(SITE_NAME), bp, esc(SITE_NAME), esc(h1_book), sub,
               pair_picker(),
               esc(ch1_bi), "\n".join(first_html), esc(title_vi), btns))
        write(os.path.join(out, book["slug"], "index.html"),
              page(bp, "%s | %s" % (h1_book, SITE_NAME),
                   h1_book, body, ("app.js", "pair.js", "book.js"), nav_dd))
        sitemap_urls.append(root + book["slug"] + "/")

    # ---- home -------------------------------------------------------------
    # Daily = deterministic full-cycle shuffle over 1189 chapters, rendered
    # in the chosen pair (default 1925-VI + NASB 1995) via daily.js + pair.js.
    first_book = sorted(books, key=lambda b: b["position"])[0]
    home = (pair_picker()
            + "<section id=\"daily\"><p class=\"kicker\">"
            "Song ngữ Việt - Anh · Mỗi ngày một đoạn</p>\n"
            "<h2 id=\"daily-title\">…</h2>\n"
            "<div id=\"daily-text\"><p>Đang tải…</p></div>\n"
            "<p><a id=\"daily-link\" href=\"#\">"
            "Đọc cả đoạn →</a></p>\n"
            "<noscript><p><a href=\"%s/%s/1/\">"
            "%s 1</a></p></noscript></section>\n"
            % (bp, first_book["slug"], esc(btitle(first_book)))
            + license_section())
    write(os.path.join(out, "index.html"),
          page(bp, SITE_NAME, SITE_DESC,
               home, ("app.js", "pair.js", "daily.js"), nav_dd))

    # ---- search -----------------------------------------------------------
    search_body = ("<div class=\"chapter-meta\"><h1>Tìm kiếm</h1></div>\n"
                   "<form id=\"search-form\" class=\"search\">"
                   "<input id=\"q\" name=\"q\" autocomplete=\"off\" "
                   "placeholder=\"Ví dụ: Giê-hô-va\">"
                   "<button type=\"submit\">Tìm</button></form>\n"
                   "<div id=\"results\"></div>")
    write(os.path.join(out, "tim-kiem", "index.html"),
          page(bp, "Tìm kiếm | %s" % SITE_NAME,
               "Tìm kiếm Kinh Thánh", search_body,
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
          page(bp, "Không tìm thấy | %s" % SITE_NAME, "",
               "<h1>404</h1><p>Trang bạn tìm không tồn "
               "tại. <a href=\"%s/\">Về trang chủ</a>.</p>" % bp,
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

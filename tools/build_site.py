#!/usr/bin/env python3
"""Generate the static Vietnamese Bible website (Phase 3).

Stdlib only.
    python tools/build_site.py --json build/bible.json \
        --index build/search_index.json --out site \
        --base-url https://example.com/ [--base-path ""]

Inputs: Phase 1 bible.json (text + order), Phase 2 search_index.json.
Output: complete static site/ -- upload it to any static host as-is.

URL scheme: / = home (verse of the day + book grid),
/<slug>/ = book, /<slug>/<n>/ = chapter, /tim-kiem/ = search.
Chapter ids 1..N follow canon order; the client verse-of-the-day is:
    chapter_id = (days_since_unix_epoch % total_chapters) + 1
per-chapter JSON under data/ch/<id>.json feeds it.

NOTE: executed by GitHub Actions (cloud) only.
Local machines are code storage; do not run builds on them.
"""

import argparse
import html
import json
import os
import sys
from datetime import datetime, timezone

SITE_NAME = "Kinh Th\xe1nh Ti\xeang Vi\xeat"

CSS = """\
:root{--bg:#ffffff;--fg:#1a1a1a;--mut:#666666;--acc:#1d4ed8;--line:#e5e5e5;--fs:17px}
html[data-theme="dark"]{--bg:#121212;--fg:#e8e8e8;--mut:#aaaaaa;--acc:#8ab4ff;--line:#333333}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:var(--fs)/1.75 Georgia,"Times New Roman",serif}
.wrap{max-width:44rem;margin:0 auto;padding:0 1rem 3rem}
header.top{border-bottom:1px solid var(--line);margin-bottom:1.5rem}
header.top .bar{max-width:44rem;margin:0 auto;padding:.6rem 1rem;display:flex;gap:1rem;align-items:center;justify-content:space-between;flex-wrap:wrap}
.brand{font-weight:bold;text-decoration:none;color:var(--fg);font-size:1.1rem}
nav.main a{margin-right:1rem}
a{color:var(--acc)}
.controls{display:flex;gap:.4rem;align-items:center}
.controls button{background:none;border:1px solid var(--line);color:var(--fg);border-radius:.4rem;padding:.15rem .55rem;cursor:pointer;font-size:.9rem}
h1{font-size:1.6rem;line-height:1.3}
h2.sec{font-size:1.15rem;margin:1.6em 0 .4em}
p.verse{margin:.5em 0}
.vnum{font-size:.75em;vertical-align:super;color:var(--mut);margin-right:.35em;font-family:system-ui,sans-serif}
.crumb{font-size:.85rem;color:var(--mut);font-family:system-ui,sans-serif}
.crumb a{color:var(--mut)}
ul.books{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(12rem,1fr));gap:.4rem}
ul.books a{display:block;border:1px solid var(--line);border-radius:.5rem;padding:.5rem .7rem;text-decoration:none;color:var(--fg)}
ul.books a:hover{border-color:var(--acc)}
ul.books span{color:var(--mut);font-size:.8rem;font-family:system-ui,sans-serif}
ol.chaps{columns:6;list-style:none;margin:0;padding:0}
ol.chaps a{display:block;padding:.3rem 0;text-decoration:none}
nav.pn{display:flex;justify-content:space-between;gap:1rem;margin:2.5rem 0 0;padding-top:1rem;border-top:1px solid var(--line);font-family:system-ui,sans-serif}
#daily{border:1px solid var(--line);border-radius:.6rem;padding:1rem 1.2rem;margin-bottom:2rem}
#daily .kicker{font-family:system-ui,sans-serif;color:var(--mut);font-size:.85rem;margin:0}
form.search{display:flex;gap:.5rem;margin:1rem 0}
form.search input{flex:1;padding:.5rem;font-size:1rem;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:.4rem}
form.search button{padding:.5rem 1rem;font-size:1rem}
#results a{display:block;padding:.3rem 0}
footer.site{border-top:1px solid var(--line);margin-top:3rem;padding:1rem;color:var(--mut);font-size:.8rem;font-family:system-ui,sans-serif}
@media print{header.top,.controls,nav.pn,form.search{display:none}.wrap{max-width:none}}
"""

# Runs before render to avoid a theme flash. Braces doubled: plain string.
EARLY_SCRIPT = """\
<script>try{var t=localStorage.getItem("kt-theme");if(t){document.documentElement.dataset.theme=t}var f=localStorage.getItem("kt-fs");if(f){document.documentElement.style.setProperty("--fs",f+"px")}}catch(e){}</script>"""

APP_JS = """\
"use strict";
function ktGet(id){return document.getElementById(id)}
var themeBtn=ktGet("theme-btn");
if(themeBtn){themeBtn.onclick=function(){var h=document.documentElement;var next=h.dataset.theme==="dark"?"light":"dark";h.dataset.theme=next;try{localStorage.setItem("kt-theme",next)}catch(e){}};}
function ktFs(delta){var h=document.documentElement;var cur=parseInt(getComputedStyle(h).getPropertyValue("--fs"))||17;var next=Math.min(24,Math.max(13,cur+delta));h.style.setProperty("--fs",next+"px");try{localStorage.setItem("kt-fs",String(next))}catch(e){}}
var fa=ktGet("fs-dec"),fb=ktGet("fs-inc");
if(fa){fa.onclick=function(){ktFs(-1)}}
if(fb){fb.onclick=function(){ktFs(1)}}
"""

# Must mirror tools/build_db.py fold()/tokenize() exactly.
SEARCH_JS = """\
"use strict";
function fold(s){return s.normalize("NFD").replace(/[\\u0300-\\u036f]/g,"").replace(/\\u0111/g,"d").replace(/\\u0110/g,"D").toLowerCase()}
function toks(s){var m=s.match(/[a-z0-9]+/g)||[];return m.filter(function(t){return t.length>=2})}
var IDX=null,CHS=null;
function esc(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}
function base(){var b=document.querySelector('meta[name="kt-base"]');return b?b.content:""}
function run(e){if(e){e.preventDefault()}var box=document.getElementById("q");var out=document.getElementById("results");var q=toks(fold(box.value));if(!q.length){out.innerHTML="<p>Vui l\u00f2ng nh\u1eadp \u00edt nh\u1ea5t 2 k\u00fd t\u1ef1.</p>";return}if(!IDX){out.innerHTML="<p>\u0110ang t\u1ea3i d\u1eef li\u1ec7u t\u00ecm ki\u1ebfm\u2026</p>";return}
var hit=null;for(var i=0;i<q.length;i++){var ids=IDX.index[q[i]]||[];if(hit===null){hit={};for(var j=0;j<ids.length;j++){hit[ids[j]]=1}}else{var nx={};for(var k=0;k<ids.length;k++){if(hit[ids[k]]){nx[ids[k]]=1}}hit=nx}if(!Object.keys(hit).length){break}}
var keys=Object.keys(hit||{}).map(Number).sort(function(a,b){return a-b});var bp=base();
if(!keys.length){out.innerHTML="<p>Kh\u00f4ng t\u00ecm th\u1ea5y k\u1ebft qu\u1ea3.</p>";return}
var h="<p>T\u00ecm th\u1ea5y "+keys.length+" \u0111o\u1ea1n.</p>";var lim=Math.min(keys.length,100);
for(var n=0;n<lim;n++){var c=CHS[keys[n]-1];h+='<a href="'+bp+"/"+c.slug+"/"+c.n+'/">'+esc(c.book)+" "+c.n+"</a>"}
if(keys.length>lim){h+="<p>\u2026ch\u1ec9 hi\u1ec3n th\u1ecb 100 k\u1ebft qu\u1ea3 \u0111\u1ea7u.</p>"}
out.innerHTML=h}
document.getElementById("search-form").addEventListener("submit",run);
Promise.all([fetch(base()+"/data/search_index.json").then(function(r){return r.json()}),fetch(base()+"/data/chapters.json").then(function(r){return r.json()})]).then(function(v){IDX=v[0];CHS=v[1];var pre=document.getElementById("q").value;if(pre){run()}}).catch(function(){document.getElementById("results").innerHTML="<p>Kh\u00f4ng t\u1ea3i \u0111\u01b0\u1ee3c d\u1eef li\u1ec7u t\u00ecm ki\u1ebfm.</p>"});
"""

DAILY_JS = """\
"use strict";
function esc(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}
function base(){var b=document.querySelector('meta[name="kt-base"]');return b?b.content:""}
fetch(base()+"/data/chapters.json").then(function(r){return r.json()}).then(function(chs){
var id=(Math.floor(Date.now()/864e5)%chs.length)+1;
return fetch(base()+"/data/ch/"+id+".json").then(function(r){return r.json()})}).then(function(d){
var bp=base();document.getElementById("daily-title").textContent=d.book+" "+d.n;
document.getElementById("daily-link").href=bp+"/"+d.slug+"/"+d.n+"/";
var h="";for(var i=0;i<d.blocks.length;i++){var b=d.blocks[i];
if(b.t==="h"){h+="<h2 class=\\"sec\\">"+esc(b.x)+"</h2>"}else{h+='<p class="verse"><span class="vnum">'+b.n+"</span>"+esc(b.x)+"</p>"}}
document.getElementById("daily-text").innerHTML=h}).catch(function(){
document.getElementById("daily-text").innerHTML="<p>Kh\u00f4ng t\u1ea3i \u0111\u01b0\u1ee3c \u0111o\u1ea1n Kinh Th\u00e1nh h\u00f4m nay.</p>"});
"""


def esc(text):
    return html.escape(text or "", quote=True)


def page(bp, title, desc, body, scripts=()):
    head_extra = "".join(
        ['<script src="%s/assets/%s" defer></script>' % (bp, s)
         for s in scripts])
    return ("<!DOCTYPE html>\n<html lang=\"vi\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            "<meta name=\"kt-base\" content=\"%s\">\n"
            "<meta name=\"description\" content=\"%s\">\n<title>%s</title>\n"
            "<link rel=\"stylesheet\" href=\"%s/assets/style.css\">\n%s%s\n</head>\n"
            "<body>\n<header class=\"top\"><div class=\"bar\">"
            "<a class=\"brand\" href=\"%s/\">%s</a>"
            "<nav class=\"main\"><a href=\"%s/\">Trang ch&#7911;</a>"
            "<a href=\"%s/tim-kiem/\">T&igrave;m ki&#7871;m</a></nav>"
            "<span class=\"controls\">"
            "<button id=\"fs-dec\" title=\"Ch&#7919; nh&#7887;\">A-</button>"
            "<button id=\"fs-inc\" title=\"Ch&#7919; l&#7899;n\">A+</button>"
            "<button id=\"theme-btn\" title=\"Ng&#7875;/ng&agrave;y\">&#9681;</button>"
            "</span></div></header>\n"
            "<main class=\"wrap\">\n%s\n</main>\n"
            "<footer class=\"site\"><div class=\"wrap\">%s</div></footer>\n"
            "</body>\n</html>\n"
            % (bp, esc(desc), esc(title), bp, EARLY_SCRIPT, head_extra,
               bp, esc(SITE_NAME), bp, bp, body, esc(SITE_NAME)))


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
    idmap = []  # index i == chapter id i+1
    for book in sorted(books, key=lambda b: b["position"]):
        for ch in book["chapters"]:
            idmap.append({"slug": book["slug"], "n": ch["number"],
                          "book": book["title"]})
    total = len(idmap)

    def url_of(cid):
        c = idmap[cid - 1]
        return "%s/%s/%d/" % (bp, c["slug"], c["n"])

    def label_of(cid):
        c = idmap[cid - 1]
        return "%s %d" % (c["book"], c["n"])

    # ---- shared assets ----------------------------------------------------
    write(os.path.join(out, "assets", "style.css"), CSS)
    write(os.path.join(out, "assets", "app.js"), APP_JS)
    write(os.path.join(out, "assets", "search.js"), SEARCH_JS)
    write(os.path.join(out, "assets", "daily.js"), DAILY_JS)
    with open(args.index, encoding="utf-8") as f:
        write(os.path.join(out, "data", "search_index.json"), f.read())
    write(os.path.join(out, "data", "chapters.json"),
          json.dumps([{"id": i + 1, "slug": c["slug"], "n": c["n"],
                       "book": c["book"]} for i, c in enumerate(idmap)],
                     ensure_ascii=False, separators=(",", ":")) + "\n")

    # ---- chapter + book pages ---------------------------------------------
    sitemap_urls = [root, root + "tim-kiem/"]
    cid = 0
    for book in sorted(books, key=lambda b: b["position"]):
        for ch in book["chapters"]:
            cid += 1
            blocks_html, blocks_json = [], []
            for b in ch["blocks"]:
                if b["type"] == "heading":
                    blocks_html.append("<h2 class=\"sec\">%s</h2>"
                                       % esc(b["text"]))
                    blocks_json.append({"t": "h", "x": b["text"]})
                else:
                    blocks_html.append(
                        "<p class=\"verse\" id=\"c%dv%d\">"
                        "<span class=\"vnum\">%d</span>%s</p>"
                        % (ch["number"], b["number"], b["number"],
                           esc(b["text"])))
                    blocks_json.append({"t": "v", "n": b["number"],
                                        "x": b["text"]})
            pn = "<nav class=\"pn\">"
            if cid > 1:
                pn += "<a href=\"%s\">&#8249; %s</a>" % (url_of(cid - 1),
                                                         esc(label_of(cid - 1)))
            else:
                pn += "<span></span>"
            if cid < total:
                pn += "<a href=\"%s\">%s &#8250;</a>" % (url_of(cid + 1),
                                                         esc(label_of(cid + 1)))
            else:
                pn += "<span></span>"
            pn += "</nav>"
            sub = ""
            if book.get("subtitle"):
                sub += "<p>%s</p>" % esc(book["subtitle"])
            if book.get("range"):
                sub += "<p class=\"crumb\">%s</p>" % esc(book["range"])
            body = ("<p class=\"crumb\"><a href=\"%s/\">%s</a> / "
                    "<a href=\"%s/%s/\">%s</a></p>\n<h1>%s %d</h1>\n%s\n%s\n%s"
                    % (bp, esc(SITE_NAME), bp, book["slug"],
                       esc(book["title"]), esc(book["title"]), ch["number"],
                       sub, "\n".join(blocks_html), pn))
            write(os.path.join(out, book["slug"], str(ch["number"]),
                               "index.html"),
                  page(bp, "%s %d | %s" % (book["title"], ch["number"],
                                           SITE_NAME),
                       "%s %d" % (book["title"], ch["number"]),
                       body, ("app.js",)))
            sitemap_urls.append(root + "%s/%d/" % (book["slug"],
                                                      ch["number"]))
            write(os.path.join(out, "data", "ch", str(cid) + ".json"),
                  json.dumps({"id": cid, "book": book["title"],
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
        body = ("<p class=\"crumb\"><a href=\"%s/\">%s</a></p>\n<h1>%s</h1>\n"
                "%s\n<ol class=\"chaps\">%s</ol>"
                % (bp, esc(SITE_NAME), esc(book["title"]), sub, lis))
        write(os.path.join(out, book["slug"], "index.html"),
              page(bp, "%s | %s" % (book["title"], SITE_NAME),
                   book["title"], body, ("app.js",)))
        sitemap_urls.append(root + book["slug"] + "/")

    # ---- home -------------------------------------------------------------
    ot = [b for b in books if b["testament"] == "OT"]
    nt = [b for b in books if b["testament"] != "OT"]

    def grid(items):
        return ("<ul class=\"books\">" + "".join(
            "<li><a href=\"%s/%s/\">%s <span>%d \u0111o\u1ea1n</span></a></li>"
            % (bp, b["slug"], esc(b["title"]), len(b["chapters"]))
            for b in sorted(items, key=lambda b: b["position"])) + "</ul>")

    home = ("<section id=\"daily\"><p class=\"kicker\">"
            "\u0110o\u1ea1n Kinh Th\u00e1nh h\u00f4m nay</p>\n"
            "<h2 id=\"daily-title\">\u2026</h2>\n"
            "<div id=\"daily-text\"><p>\u0110ang t\u1ea3i\u2026</p></div>\n"
            "<p><a id=\"daily-link\" href=\"#\">"
            "\u0110\u1ecdc c\u1ea3 \u0111o\u1ea1n &#8594;</a></p>\n"
            "<noscript><p><a href=\"%s/sang-the-ky/1/\">"
            "S\u00e1ng Th\u1ebf k\u00fd 1</a></p></noscript></section>\n"
            "<h2 id=\"sach\">C\u1ef1u \u01af\u1edbc</h2>\n%s\n"
            "<h2>T\u00e2n \u01af\u1edbc</h2>\n%s"
            % (bp, grid(ot), grid(nt)))
    write(os.path.join(out, "index.html"),
          page(bp, SITE_NAME, "Kinh Th\xe1nh Ti\xeang Vi\xeat online",
               home, ("app.js", "daily.js")))

    # ---- search -----------------------------------------------------------
    search_body = ("<h1>T&igrave;m ki&#7871;m</h1>\n"
                   "<form id=\"search-form\" class=\"search\">"
                   "<input id=\"q\" name=\"q\" autocomplete=\"off\" "
                   "placeholder=\"V&iacute; d&#7909;: Gi&ecirc;-h&ocirc;-va\">"
                   "<button type=\"submit\">T&igrave;m</button></form>\n"
                   "<div id=\"results\"></div>")
    write(os.path.join(out, "tim-kiem", "index.html"),
          page(bp, "T\u00ecm ki\u1ebfm | %s" % SITE_NAME,
               "T\u00ecm ki\u1ebfm Kinh Th\u00e1nh", search_body,
               ("app.js", "search.js")))

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
               ("app.js",)))

    n_files = sum(len(fs) for _, _, fs in os.walk(out))
    print("books=%d chapters=%d files=%d" % (len(books), total, n_files))
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
:root{
  --bg:#fcfcfb;--bg2:#f3f2ee;--fg:#1c1917;--fg2:#44403c;--mut:#a8a29e;
  --acc:#92400e;--acc2:#78350f;--acc-hover:#b45309;--acc-bg:rgba(146,64,14,.06);
  --line:#e7e5e4;--card:#ffffff;--shadow:0 1px 3px rgba(0,0,0,.06);
  --serif:"Noto Serif",Georgia,"Times New Roman",serif;
  --sans:system-ui,-apple-system,"Segoe UI",sans-serif;
  --fs:18px;
}
html[data-theme="dark"]{
  --bg:#1a1918;--bg2:#252321;--fg:#f5f0eb;--fg2:#d6cec5;--mut:#78716c;
  --acc:#fbbf24;--acc2:#f59e0b;--acc-hover:#fcd34d;--acc-bg:rgba(251,191,36,.1);
  --line:#3a3633;--card:#211f1d;--shadow:0 1px 3px rgba(0,0,0,.2);
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{
  background:var(--bg);color:var(--fg);
  font:var(--fs)/1.9 var(--serif);
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
  transition:background .3s,color .3s
}
a{color:var(--acc);text-decoration:none;transition:color .2s}
a:hover{color:var(--acc-hover);text-decoration:underline}
.wrap{max-width:42rem;margin:0 auto;padding:0 1.5rem 5rem}

/* ---- header ---- */
header.top{
  border-bottom:1px solid var(--line);background:var(--bg);
  position:sticky;top:0;z-index:100;
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
}
header.top .bar{
  max-width:42rem;margin:0 auto;padding:.65rem 1.5rem;
  display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.5rem
}
.brand{font-weight:700;text-decoration:none;color:var(--fg);font-size:1.05rem;letter-spacing:-.02em;font-family:var(--sans)}
.brand span{color:var(--acc)}
nav.main{display:flex;gap:.25rem;align-items:center}
nav.main>a,nav.main>.dd{color:var(--mut);font-size:.85rem;font-family:var(--sans);font-weight:500;text-decoration:none;transition:color .2s;padding:.3rem .6rem;border-radius:6px}
nav.main>a:hover,nav.main>.dd:hover{color:var(--acc);text-decoration:none}
/* dropdown */
.dd{position:relative;cursor:pointer}
.dd::after{content:" \\25BE";font-size:.7em;opacity:.5}
.dd-menu{
  display:none;position:absolute;top:calc(100% + .35rem);right:0;
  background:var(--card);border:1px solid var(--line);border-radius:10px;
  box-shadow:0 8px 30px rgba(0,0,0,.12);padding:.4rem 0;
  min-width:20rem;max-height:70vh;overflow-y:auto;z-index:200;
}
.dd-menu a{
  display:block;padding:.4rem 1rem;font-family:var(--sans);font-size:.82rem;
  color:var(--fg2);text-decoration:none;transition:background .12s,color .12s;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis
}
.dd-menu a:hover{background:var(--acc-bg);color:var(--acc);text-decoration:none}
.dd.open .dd-menu{display:block}
@media(max-width:640px){
  .dd-menu{position:fixed;left:.5rem;right:.5rem;top:auto;max-height:60vh;width:auto}
}
.controls{display:flex;gap:.3rem;align-items:center}
.controls button{
  background:none;border:1px solid var(--line);color:var(--mut);
  border-radius:6px;padding:.25rem .55rem;cursor:pointer;
  font-size:.8rem;font-family:var(--sans);transition:all .2s
}
.controls button:hover{border-color:var(--acc);color:var(--acc)}
.controls button:active{transform:scale(.95)}

/* ---- crumbs ---- */
.crumb{font-size:.8rem;color:var(--mut);font-family:var(--sans);margin-bottom:.5rem}
.crumb a{color:var(--mut)}
.crumb a:hover{color:var(--acc)}

/* ---- verse of the day ---- */
#daily{
  border:1px solid var(--line);border-radius:12px;
  padding:2.25rem 2.5rem;margin-bottom:3rem;
  background:var(--card);box-shadow:var(--shadow)
}
#daily .kicker{
  font-family:var(--sans);font-size:.7rem;font-weight:700;
  color:var(--acc);letter-spacing:.1em;text-transform:uppercase;margin:0 0 .5rem
}
#daily h2#daily-title{
  font-size:1.4rem;font-weight:700;font-family:var(--sans);
  color:var(--fg);margin:0 0 1.25rem;letter-spacing:-.01em
}
#daily-text{color:var(--fg2);line-height:2}
#daily-text sup{font-size:.65em;color:var(--acc);font-family:var(--sans);font-weight:600;margin-right:.15em;opacity:.7}
#daily-link{
  display:inline-block;margin-top:1.25rem;
  font-family:var(--sans);font-size:.85rem;font-weight:600;color:var(--acc)
}
#daily-link:hover{text-decoration:none}

/* ---- chapter index ---- */
.chaps{columns:3;list-style:none;margin:0;padding:0;column-gap:1.5rem}
.chaps li a{
  display:block;padding:.5rem 0;color:var(--fg);
  font-family:var(--sans);font-size:.9rem;text-decoration:none;
  border-bottom:1px solid var(--line);transition:color .15s
}
.chaps li:last-child a{border-bottom:none}
.chaps li a:hover{color:var(--acc);text-decoration:none}

/* ---- chapter content: flowing paragraphs ---- */
.chapter-meta{margin-bottom:2rem}
.chapter-meta h1{
  font-size:2rem;font-weight:700;font-family:var(--sans);
  color:var(--fg);letter-spacing:-.02em;line-height:1.2;margin:0 0 .25rem
}
.chapter-meta .sub{color:var(--mut);font-size:.8rem;font-family:var(--sans)}
h2.sec{
  font-size:1rem;font-weight:700;font-family:var(--sans);
  color:var(--acc);letter-spacing:.02em;
  margin:2.5em 0 .75em;text-transform:uppercase
}
p.reading{
  text-indent:0;margin:0 0 1.25em;line-height:2;
  text-align:justify;hyphens:auto
}
p.reading sup{
  font-size:.6em;color:var(--acc);font-family:var(--sans);
  font-weight:600;margin-right:.1em;opacity:.7
}
p.reading sup[id]{
  cursor:pointer;transition:color .15s
}
p.reading sup[id]:hover{opacity:1}

/* ---- prev / next navigation ---- */
nav.pn{
  display:flex;justify-content:space-between;gap:1rem;
  margin:3.5rem 0 0;padding-top:1.5rem;border-top:1px solid var(--line);
  font-family:var(--sans);font-size:.85rem
}
nav.pn a{
  display:inline-flex;align-items:center;gap:.3rem;
  color:var(--fg2);padding:.4rem .8rem;border:1px solid var(--line);
  border-radius:8px;transition:all .2s;font-weight:500;text-decoration:none
}
nav.pn a:hover{border-color:var(--acc);color:var(--acc);text-decoration:none}
nav.pn span.empty{visibility:hidden}

/* ---- search ---- */
form.search{display:flex;gap:.5rem;margin:2rem 0}
form.search input{
  flex:1;padding:.75rem 1rem;font-size:1rem;font-family:var(--sans);
  background:var(--card);color:var(--fg);
  border:2px solid var(--line);border-radius:10px;
  transition:border-color .2s;outline:none
}
form.search input:focus{border-color:var(--acc)}
form.search button{
  padding:.75rem 1.5rem;font-size:.9rem;font-family:var(--sans);font-weight:600;
  background:var(--acc);color:#fff;border:none;border-radius:10px;
  cursor:pointer;transition:background .2s
}
form.search button:hover{background:var(--acc-hover)}
#results{margin-top:1.5rem}
#results p{color:var(--fg2);font-family:var(--sans);font-size:.9rem}
#results a{
  display:block;padding:.5rem .75rem;border-radius:6px;
  transition:background .15s;font-family:var(--sans);font-size:.9rem;
  color:var(--fg);text-decoration:none
}
#results a:hover{background:var(--acc-bg);text-decoration:none}

/* ---- footer ---- */
footer.site{
  border-top:1px solid var(--line);margin-top:4rem;
  padding:1.5rem 0;color:var(--mut);
  font-size:.75rem;font-family:var(--sans);text-align:center
}

/* ---- print ---- */
@media print{
  header.top,.controls,nav.pn,form.search,.crumb{display:none}
  .wrap{max-width:none;padding:0}
  body{font-size:12pt;line-height:1.6}
  #daily{border:none;box-shadow:none;background:none}
  p.reading sup{color:var(--fg);opacity:.5}
}

/* ---- responsive ---- */
@media (max-width:640px){
  .wrap{padding:0 1rem 3rem}
  header.top .bar{padding:.5rem 1rem}
  #daily{padding:1.5rem}
  .chaps{columns:2}
  .chapter-meta h1{font-size:1.5rem}
  nav.pn{font-size:.8rem}
}
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
document.querySelectorAll(".dd").forEach(function(el){
el.addEventListener("click",function(e){e.stopPropagation();var wasOpen=el.classList.contains("open");
document.querySelectorAll(".dd").forEach(function(d){d.classList.remove("open")});
if(!wasOpen){el.classList.add("open")}})});
document.addEventListener("click",function(){document.querySelectorAll(".dd").forEach(function(d){d.classList.remove("open")})});
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
var h="",p=[];for(var i=0;i<d.blocks.length;i++){var b=d.blocks[i];
if(b.t==="h"){if(p.length){h+='<p class="reading">'+p.join("")+"</p>";p=[]}
h+="<h2>"+esc(b.x)+"</h2>"}else{p.push("<sup>"+b.n+"</sup>"+esc(b.x)+" ")}}
if(p.length){h+='<p class="reading">'+p.join("")+"</p>"}
document.getElementById("daily-text").innerHTML=h}).catch(function(){
document.getElementById("daily-text").innerHTML="<p>Kh\u00f4ng t\u1ea3i \u0111\u01b0\u1ee3c \u0111o\u1ea1n Kinh Th\u00e1nh h\u00f4m nay.</p>"});
"""


def esc(text):
    return html.escape(text or "", quote=True)


def page(bp, title, desc, body, scripts=(), nav_extra=""):
    head_extra = "".join(
        ['<script src="%s/assets/%s" defer></script>' % (bp, s)
         for s in scripts])
    return ("<!DOCTYPE html>\n<html lang=\"vi\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            "<meta name=\"kt-base\" content=\"%s\">\n"
            "<meta name=\"description\" content=\"%s\">\n<title>%s</title>\n"
            "<link rel=\"stylesheet\" href=\"%s/assets/style.css\">\n%s%s\n</head>\n"
            "<body>\n<header class=\"top\"><div class=\"bar\">"
            "<a class=\"brand\" href=\"%s/\">Kinh Th<span>e</span>nh Ti\u00eang Vi\u00eat</a>"
            "<nav class=\"main\"><a href=\"%s/\">Trang ch&#7911;</a>"
            "%s"
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
               bp, esc(SITE_NAME), nav_extra, bp, body, esc(SITE_NAME)))


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

    # ---- nav dropdown HTML ------------------------------------------------
    def dd_menu(items):
        links = "".join(
            "<a href=\"%s/%s/\">%s</a>" % (bp, b["slug"], esc(b["title"]))
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
            para = []
            for b in ch["blocks"]:
                if b["type"] == "heading":
                    if para:
                        blocks_html.append('<p class="reading">%s</p>' % "".join(para))
                        para = []
                    blocks_html.append("<h2 class=\"sec\">%s</h2>"
                                       % esc(b["text"]))
                    blocks_json.append({"t": "h", "x": b["text"]})
                else:
                    para.append(
                        "<sup id=\"c%dv%d\">%d</sup>%s "
                        % (ch["number"], b["number"], b["number"],
                           esc(b["text"])))
                    blocks_json.append({"t": "v", "n": b["number"],
                                        "x": b["text"]})
            if para:
                blocks_html.append('<p class="reading">%s</p>' % "".join(para))
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
            body = ("<p class=\"crumb\"><a href=\"%s/\">%s</a> / "
                    "<a href=\"%s/%s/\">%s</a></p>\n"
                    "<div class=\"chapter-meta\"><h1>%s %d</h1>\n%s</div>\n%s\n%s"
                    % (bp, esc(SITE_NAME), bp, book["slug"],
                       esc(book["title"]), esc(book["title"]), ch["number"],
                       sub, "\n".join(blocks_html), pn))
            write(os.path.join(out, book["slug"], str(ch["number"]),
                               "index.html"),
                  page(bp, "%s %d | %s" % (book["title"], ch["number"],
                                           SITE_NAME),
                       "%s %d" % (book["title"], ch["number"]),
                       body, ("app.js",), nav_dd))
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
        body = ("<p class=\"crumb\"><a href=\"%s/\">%s</a></p>\n"
                "<div class=\"chapter-meta\"><h1>%s</h1>\n%s</div>\n"
                "<ol class=\"chaps\">%s</ol>"
                % (bp, esc(SITE_NAME), esc(book["title"]), sub, lis))
        write(os.path.join(out, book["slug"], "index.html"),
              page(bp, "%s | %s" % (book["title"], SITE_NAME),
                   book["title"], body, ("app.js",), nav_dd))
        sitemap_urls.append(root + book["slug"] + "/")

    # ---- home -------------------------------------------------------------
    home = ("<section id=\"daily\"><p class=\"kicker\">"
            "\u0110o\u1ea1n Kinh Th\u00e1nh h\u00f4m nay</p>\n"
            "<h2 id=\"daily-title\">\u2026</h2>\n"
            "<div id=\"daily-text\"><p>\u0110ang t\u1ea3i\u2026</p></div>\n"
            "<p><a id=\"daily-link\" href=\"#\">"
            "\u0110\u1ecdc c\u1ea3 \u0111o\u1ea1n &#8594;</a></p>\n"
            "<noscript><p><a href=\"%s/sang-the-ky/1/\">"
            "S\u00e1ng Th\u1ebf k\u00fd 1</a></p></noscript></section>"
            % bp)
    write(os.path.join(out, "index.html"),
          page(bp, SITE_NAME, "Kinh Th\xe1nh Ti\xeang Vi\xeat online",
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

    n_files = sum(len(fs) for _, _, fs in os.walk(out))
    print("books=%d chapters=%d files=%d" % (len(books), total, n_files))
    return 0


if __name__ == "__main__":
    sys.exit(main())

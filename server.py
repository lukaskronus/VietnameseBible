#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnamese Bible Local Server
Zero dependencies required (pure Python standard library)
"""

import http.server
import socketserver
import sqlite3
import json
import os
import re
import sys
import time
import urllib.parse
import webbrowser

# Force UTF-8 on Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

PORT = int(os.environ.get('PORT', 8765))
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bible.db')

def ensure_database():
    if os.path.exists(DB_FILE) and os.path.getsize(DB_FILE) > 1000000:
        return
    print("Initializing database from data files...")
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS books (
        id INTEGER PRIMARY KEY,
        code TEXT UNIQUE,
        name TEXT,
        testament TEXT,
        total_chapters INTEGER
    )''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS bible (
        id INTEGER PRIMARY KEY,
        book_id INTEGER,
        book_code TEXT,
        book_name TEXT,
        chapter INTEGER,
        title TEXT,
        data TEXT,
        FOREIGN KEY(book_id) REFERENCES books(id)
    )''')
    cur.execute('CREATE VIRTUAL TABLE IF NOT EXISTS bible_fts USING fts5(id UNINDEXED, title, data)')
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    list_path = os.path.join(base_dir, 'data', 'list.txt')
    if not os.path.exists(list_path):
        conn.close()
        return

    with open(list_path, 'r', encoding='utf-8') as f:
        book_codes = [line.strip() for line in f if line.strip()]

    old_testament_codes = set(book_codes[:39])
    sql_id = 1
    for b_idx, code in enumerate(book_codes, 1):
        fname = os.path.join(base_dir, 'data', f'{code}.txt')
        if not os.path.exists(fname):
            continue
        with open(fname, 'r', encoding='utf-8', errors='ignore') as bf:
            lines = [l.rstrip('\r\n') for l in bf]
        if not lines:
            continue
        b_name = lines[0].strip().lstrip('\ufeff')
        testament = 'OT' if code in old_testament_codes else 'NT'
        
        n_doan = 1
        chapter_lines = {1: []}
        for l in lines[1:]:
            l_str = l.strip()
            if l_str == str(n_doan + 1):
                n_doan += 1
                chapter_lines[n_doan] = []
            else:
                chapter_lines[n_doan].append(l)
                
        cur.execute('INSERT OR REPLACE INTO books (id, code, name, testament, total_chapters) VALUES (?, ?, ?, ?, ?)',
                    (b_idx, code, b_name, testament, n_doan))
                    
        for c in range(1, n_doan + 1):
            content = '\n'.join(chapter_lines[c])
            ch_title = f'{b_name} {c}'
            cur.execute('INSERT OR REPLACE INTO bible (id, book_id, book_code, book_name, chapter, title, data) VALUES (?, ?, ?, ?, ?, ?, ?)',
                        (sql_id, b_idx, code, b_name, c, ch_title, content))
            cur.execute('INSERT INTO bible_fts (id, title, data) VALUES (?, ?, ?)',
                        (sql_id, ch_title, content))
            sql_id += 1

    conn.commit()
    conn.close()
    print("Database initialization complete.")

def get_db():
    ensure_database()
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def calculate_daily_id(timestamp=None):
    if timestamp is None:
        timestamp = time.time()
    # Original formula: 178 + round((time() - 1440194290) / 86400 - 0.5)
    raw_id = 178 + int(round((timestamp - 1440194290) / 86400.0 - 0.5))
    # Map to 1..1189 range
    return ((raw_id - 1) % 1189) + 1

def is_real_heading(line, prev_line=None, next_line=None, is_start_of_chapter=False, is_poetry_book=False):
    line = line.strip()
    if not line or line.isdigit():
        return False
    if re.search(r"(?:^|\s)\d+\s+[A-ZÀ-Ỹa-zà-ỹ]", line):
        return False
    if "[†]" in line or "[*]" in line or "(Từ " in line or line.startswith("(") or line.startswith("["):
        return False
    if line.endswith(",") or line.endswith(";") or line.endswith(":") or line.endswith("?") or line.endswith("!"):
        return False
    if line.startswith("-") or line.startswith("–") or line.startswith("—"):
        return False
    if line[0].islower():
        return False
    if is_poetry_book and not is_start_of_chapter:
        return False
    if len(line) > 85:
        return False
    if is_start_of_chapter:
        return True
    if next_line:
        nxt_clean = next_line.strip()
        if re.match(r"^\d+\s+[A-ZÀ-Ỹ]", nxt_clean):
            return True
    return False

def format_chapter_text(raw_text, book_code=""):
    poetry_codes = {"thi", "ch", "nha", "ca", "giop"}
    is_poetry = book_code.lower() in poetry_codes
    
    raw_lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    structured = []
    seen_first_verse = False
    
    for i, line in enumerate(raw_lines):
        prev_l = raw_lines[i-1] if i > 0 else None
        next_l = raw_lines[i+1] if i+1 < len(raw_lines) else None
        
        if not seen_first_verse:
            if is_real_heading(line, prev_l, next_l, is_start_of_chapter=True, is_poetry_book=is_poetry):
                structured.append({"type": "heading", "text": line})
                continue
        else:
            if is_real_heading(line, prev_l, next_l, is_start_of_chapter=False, is_poetry_book=is_poetry):
                structured.append({"type": "heading", "text": line})
                continue

        tokens = re.split(r"(?:^|\s)(?=\d+\s+[A-ZÀ-Ỹa-zà-ỹ\"“])", line)
        for token in tokens:
            token = token.strip()
            if not token:
                continue
            m = re.match(r"^(\d+)\s+(.*)$", token, re.DOTALL)
            if m:
                seen_first_verse = True
                v_num = int(m.group(1))
                v_text = m.group(2).strip()
                structured.append({
                    "type": "verse",
                    "number": v_num,
                    "text": v_text
                })
            else:
                if structured and structured[-1]["type"] == "verse":
                    structured[-1]["text"] += " " + token
                else:
                    structured.append({
                        "type": "paragraph",
                        "text": token
                    })
                    
    return structured

class BibleHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == '/' or path == '/index.html' or path == '/viewer.html':
            self.serve_app()
            return
        elif path == '/api/books':
            self.serve_books()
            return
        elif path == '/api/chapter':
            self.serve_chapter(query)
            return
        elif path == '/api/today':
            self.serve_today()
            return
        elif path == '/api/search':
            self.serve_search(query)
            return
        elif path == '/api/random':
            self.serve_random()
            return
        else:
            super().do_GET()

    def send_json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_books(self):
        conn = get_db()
        cur = conn.cursor()
        rows = cur.execute('SELECT id, code, name, testament, total_chapters FROM books ORDER BY id').fetchall()
        books = [dict(row) for row in rows]
        conn.close()
        self.send_json_response({'success': True, 'books': books})

    def serve_today(self):
        today_id = calculate_daily_id()
        conn = get_db()
        cur = conn.cursor()
        row = cur.execute('''
            SELECT b.id, b.book_id, b.book_code, b.book_name, b.chapter, b.title, b.data, bk.total_chapters
            FROM bible b
            JOIN books bk ON b.book_id = bk.id
            WHERE b.id = ?
        ''', (today_id,)).fetchone()
        conn.close()

        if row:
            res = dict(row)
            res['structured'] = format_chapter_text(res['data'], res.get('book_code', ''))
            self.send_json_response({'success': True, 'chapter': res, 'daily_id': today_id})
        else:
            self.send_json_response({'success': False, 'error': 'Not found'}, 404)

    def serve_chapter(self, query):
        conn = get_db()
        cur = conn.cursor()
        
        ch_id = query.get('id', [None])[0]
        book_code = query.get('book', [None])[0]
        chapter_num = query.get('chapter', [None])[0]

        row = None
        if ch_id:
            try:
                ch_id = int(ch_id)
                if ch_id < 1: ch_id = 1
                if ch_id > 1189: ch_id = 1189
                row = cur.execute('''
                    SELECT b.id, b.book_id, b.book_code, b.book_name, b.chapter, b.title, b.data, bk.total_chapters
                    FROM bible b
                    JOIN books bk ON b.book_id = bk.id
                    WHERE b.id = ?
                ''', (ch_id,)).fetchone()
            except ValueError:
                pass
        elif book_code and chapter_num:
            try:
                chapter_num = int(chapter_num)
                row = cur.execute('''
                    SELECT b.id, b.book_id, b.book_code, b.book_name, b.chapter, b.title, b.data, bk.total_chapters
                    FROM bible b
                    JOIN books bk ON b.book_id = bk.id
                    WHERE (b.book_code = ? OR b.book_name = ?) AND b.chapter = ?
                ''', (book_code, book_code, chapter_num)).fetchone()
            except ValueError:
                pass

        conn.close()
        if row:
            res = dict(row)
            res['structured'] = format_chapter_text(res['data'], res.get('book_code', ''))
            self.send_json_response({'success': True, 'chapter': res})
        else:
            self.send_json_response({'success': False, 'error': 'Chapter not found'}, 404)

    def serve_random(self):
        import random
        rand_id = random.randint(1, 1189)
        conn = get_db()
        cur = conn.cursor()
        row = cur.execute('''
            SELECT b.id, b.book_id, b.book_code, b.book_name, b.chapter, b.title, b.data, bk.total_chapters
            FROM bible b
            JOIN books bk ON b.book_id = bk.id
            WHERE b.id = ?
        ''', (rand_id,)).fetchone()
        conn.close()
        if row:
            res = dict(row)
            res['structured'] = format_chapter_text(res['data'], res.get('book_code', ''))
            self.send_json_response({'success': True, 'chapter': res})
        else:
            self.send_json_response({'success': False, 'error': 'Random chapter error'}, 500)

    def serve_search(self, query):
        q = query.get('q', [''])[0].strip()
        if not q or len(q) < 2:
            self.send_json_response({'success': True, 'results': [], 'total': 0})
            return

        conn = get_db()
        cur = conn.cursor()
        
        sql_like = f"%{q}%"
        rows = cur.execute('''
            SELECT id, book_id, book_code, book_name, chapter, title, data
            FROM bible
            WHERE data LIKE ? OR title LIKE ?
            LIMIT 50
        ''', (sql_like, sql_like)).fetchall()

        results = []
        for r in rows:
            text = r['data']
            matches = []
            for line in text.split('\n'):
                if q.lower() in line.lower():
                    matches.append(line.strip())
                    if len(matches) >= 3:
                        break
            
            results.append({
                'id': r['id'],
                'book_id': r['book_id'],
                'book_code': r['book_code'],
                'book_name': r['book_name'],
                'chapter': r['chapter'],
                'title': r['title'],
                'snippet': '<br/>'.join(matches) if matches else text[:200]
            })

        conn.close()
        self.send_json_response({'success': True, 'results': results, 'total': len(results), 'query': q})

    def serve_app(self):
        index_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'viewer.html')
        if not os.path.exists(index_file):
            self.send_error(404, "viewer.html not found")
            return
        with open(index_file, 'rb') as f:
            content = f.read()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def run_server():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    socketserver.TCPServer.allow_reuse_address = True
    
    port = PORT
    candidate_ports = [PORT, 8765, 8766, 8899, 9090, 9527, 7788]
    # Remove duplicates preserving order
    seen = set()
    candidate_ports = [p for p in candidate_ports if not (p in seen or seen.add(p))]
    
    httpd = None
    for try_port in candidate_ports:
        try:
            httpd = socketserver.TCPServer(("", try_port), BibleHTTPRequestHandler)
            port = try_port
            break
        except OSError:
            continue
            
    if httpd is None:
        print("Could not bind to any port.")
        sys.exit(1)

    url = f"http://localhost:{port}"
    print("=" * 50)
    print(f"  Vietnamese Bible Server Running at: {url}")
    print(f"  Mở trình duyệt: {url}")
    print("=" * 50)
    
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"Could not auto-open browser: {e}")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()

if __name__ == '__main__':
    run_server()

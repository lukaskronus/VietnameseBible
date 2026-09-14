# Vietnamese–English Bilingual Bible

Trang web "Mỗi ngày một đoạn Kinh Thánh" — nay song ngữ Việt–Anh.

## Nguồn dữ liệu (mới)

- `data/viet.sqlite3` — Kinh Thánh tiếng Việt 1934 (chính)
- `data/nasb.sqlite3` — New American Standard Bible, tiếng Anh (phụ)

Cả hai file dùng chung schema (`books` / `chapters` / `verses` / `metadata`),
66 sách, 1189 chương, cùng mã OSIS (`Gen`, `Exod`, …) và `chapters.id` 1..1189
nên liên kết câu theo `(book, chương, câu)` 1:1. Ngoại lệ duy nhất: 3 Giăng 15
(`3John 1:15`) chỉ có bản Anh, bản Việt để trống.

Các file `data/*.txt`, `data/list.txt`, `data/bible.sql`, `data/gensql.pl` là
di sản (legacy) và **không còn được đọc** — giữ lại để tham khảo.

## Pipeline (GitHub Actions, `.github/workflows/build.yml`)

1. **Phase 1** `tools/parse_bible.py --data data --out build` — gộp 2 sqlite
   thành `build/bible.json` song ngữ + `build/validation_report.md`.
   Mỗi câu: `{type: verse, number, vi, en}` (`text` = bản Việt, tương thích cũ);
   tiêu đề đoạn (`<h3>/<h4>` NASB) thành `{type: heading, en}`.
2. **Phase 2** `tools/build_db.py` — `build/bible.sqlite`
   (`verses.text` = Việt, `verses.text_en` = Anh, FTS trên cả hai) +
   `build/search_index.json` (tìm kiếm song ngữ, không dấu).
3. **Phase 3** `tools/build_site.py` — site tĩnh song ngữ: mỗi chương hiển thị
   tiếng Việt rồi tiếng Anh theo từng câu; trang chủ hiển thị **đoạn song ngữ
   của ngày** (`chapter_id = days_since_epoch % 1189 + 1`), chung quy luật với
   `index.php`.
4. Deploy thủ công từ artifact `site`.

## Trang PHP (`index.php`)

`index.php` đọc trực tiếp 2 file sqlite (PDO SQLite, không còn MySQL) và hiển
thị đoạn song ngữ của ngày. `test.php` là script debug (`?id=N`).

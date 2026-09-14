# Vietnamese–English Bilingual Bible

Trang web "Mỗi ngày một đoạn Kinh Thánh" — song ngữ Việt–Anh với 6 bản dịch
tùy chọn ghép cặp (mặc định: Tiếng Việt 1925 + NASB 1995).

## Nguồn dữ liệu

`data/xml/` — 6 bản dịch, cùng schema
`<bible> → <testament> → <book number=1..66> → <chapter> → <verse>`:

- `VietnameseBible.xml` — Kinh Thánh Tiếng Việt 1925 (`vi1925`)
- `VietnameseNVBBible.xml` — Kinh Thánh Bản Dịch Mới 2002 (`vinvb`)
- `VietnameseVIEBible.xml` — Hiệu Đính 2010 (`vivie`)
- `EnglishESVBible.xml` — ESV 2016 (`enesv`)
- `EnglishNASBBible.xml` — NASB 1995 (`ennasb`)
- `EnglishNETBible.xml` — NET 2005 (`ennet`)

66 sách, 1189 chương ở mọi bản; số câu chênh nhau không đáng kể (hợp nhất
union, bên thiếu để trống — ví dụ 3 Giăng 15). Tên sách tiếng Việt chuẩn
nằm trong `tools/parse_bible.py` (`VI_TITLES`); XML chỉ đánh số sách.

`data/txt/` và `data/sqlite/` là di sản (legacy) và **không còn được đọc**.

Bản quyền các bản dịch hiển thị ở cuối trang chủ; web phi thương mại,
không quảng cáo — xin tôn trọng điều khoản của từng bản dịch.

## Pipeline (GitHub Actions, `.github/workflows/build.yml`)

1. **Phase 1** `tools/parse_bible.py --data data/xml --out build` — gộp 6 XML
   thành `build/bible.json` + `build/validation_report.md`. Mỗi câu giữ text
   cả 6 bản (`texts`), `vi`/`en` là cặp mặc định.
2. **Phase 2** `tools/build_db.py` — `build/bible.sqlite` (cặp mặc định,
   FTS gộp Việt+Anh, tìm không dấu) + `build/search_index.json`.
3. **Phase 3** `tools/build_site.py` — site tĩnh: trang chương bake cặp mặc
   định; trang chủ + trang sách có **bộ chọn ghép cặp** (2 dropdown, lưu
   `localStorage`), nạp `data/tr/<mã-bản-dịch>/ch/<id>.json` không cần tải
   lại trang. Đoạn của ngày:
   `chapter_id = days_since_epoch % 1189 + 1`, chung quy luật với `index.php`.
4. Deploy thủ công từ artifact `site`.

## Trang PHP (`index.php`)

`index.php` đọc trực tiếp 2 file XML mặc định (SimpleXML) và hiển thị đoạn
song ngữ của ngày. `test.php` là script debug (`?id=N`).

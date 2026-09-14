<?php
// Bilingual daily chapter (VI + EN), sourced from data/xml/*.xml.
// Default pair: 1925-VI + NASB 1995.
// Daily surprise: full-cycle shuffle over all chapters, same rule as the
// static site (tools/build_site.py + tools/static/daily.js).
// chapter = ((701 * days_since_unix_epoch + 123) % total) + 1.
// 701 is coprime to 1189 (= 29*41): every chapter appears exactly once per
// cycle, in unpredictable order. Same chapter for all visitors each day.
header('Content-Type: text/html; charset=UTF-8');

// Canonical titles (kept in sync with tools/parse_bible.py).
$VI_TITLES = array('Sáng thế Ký', 'Xuất Ê-díp-tô Ký', 'Lê-vi Ký', 'Dân-số Ký', 'Phục truyền Luật lệ Ký', 'Giô-suê', 'Các Quan Xét', 'Ru-tơ', 'I Sa-mu-ên', 'II Sa-mu-ên', 'I Các Vua', 'II Các Vua', 'I Sử ký', 'II Sử ký', 'E-xơ-ra', 'Nê-hê-mi', 'Ê-xơ-tê', 'Gióp', 'Thi thiên', 'Châm ngôn', 'Truyền đạo', 'Nhã ca', 'Ê-sai', 'Giê-rê-mi', 'Ca-thương', 'Ê-xê-chi-ên', 'Đa-ni-ên', 'Ô-sê', 'Giô-ên', 'A-mốt', 'Áp-đia', 'Giô-na', 'Mi-chê', 'Na-hum', 'Ha-ba-cúc', 'Sô-phô-ni', 'A-ghê', 'Xa-cha-ri', 'Ma-la-chi', 'Ma-thi-ơ', 'Mác', 'Lu-ca', 'Giăng', 'Công-vụ các Sứ-đồ', 'Rô-ma', 'I Cô-rinh-tô', 'II Cô-rinh-tô', 'Ga-la-ti', 'Ê-phê-sô', 'Phi-líp', 'Cô-lô-se', 'I Tê-sa-lô-ni-ca', 'II Tê-sa-lô-ni-ca', 'I Ti-mô-thê', 'II Ti-mô-thê', 'Tít', 'Phi-lê-môn', 'Hê-bơ-rơ', 'Gia-cơ', 'I Phi-e-rơ', 'II Phi-e-rơ', 'I Giăng', 'II Giăng', 'III Giăng', 'Giu-đe', 'Khải-huyền');
$EN_TITLES = array('Genesis', 'Exodus', 'Leviticus', 'Numbers', 'Deuteronomy', 'Joshua', 'Judges', 'Ruth', '1 Samuel', '2 Samuel', '1 Kings', '2 Kings', '1 Chronicles', '2 Chronicles', 'Ezra', 'Nehemiah', 'Esther', 'Job', 'Psalm', 'Proverbs', 'Ecclesiastes', 'Song of Solomon', 'Isaiah', 'Jeremiah', 'Lamentations', 'Ezekiel', 'Daniel', 'Hosea', 'Joel', 'Amos', 'Obadiah', 'Jonah', 'Micah', 'Nahum', 'Habakkuk', 'Zephaniah', 'Haggai', 'Zechariah', 'Malachi', 'Matthew', 'Mark', 'Luke', 'John', 'Acts', 'Romans', '1 Corinthians', '2 Corinthians', 'Galatians', 'Ephesians', 'Philippians', 'Colossians', '1 Thessalonians', '2 Thessalonians', '1 Timothy', '2 Timothy', 'Titus', 'Philemon', 'Hebrews', 'James', '1 Peter', '2 Peter', '1 John', '2 John', '3 John', 'Jude', 'Revelation');

function chapter_verses($xml, $bookNo, $chNo) {
    $out = array();
    foreach ($xml->testament as $t) {
        foreach ($t->book as $b) {
            if ((int)$b['number'] !== $bookNo) continue;
            foreach ($b->chapter as $c) {
                if ((int)$c['number'] !== $chNo) continue;
                foreach ($c->verse as $v) {
                    $n = (int)$v['number'];
                    $t = trim(preg_replace('/\s+/', ' ', (string)$v));
                    if (isset($out[$n])) continue;
                    $out[$n] = $t;
                }
            }
        }
    }
    ksort($out);
    return $out;
}

try {
    $vi = simplexml_load_file(__DIR__ . '/data/xml/VietnameseBible.xml');
    $en = simplexml_load_file(__DIR__ . '/data/xml/EnglishNASBBible.xml');
    if ($vi === false || $en === false) throw new Exception('xml load failed');

    // Resolve chapter id -> (book, chapter) in canon order.
    $map = array();
    foreach ($vi->testament as $t) {
        foreach ($t->book as $b) {
            $bn = (int)$b['number'];
            foreach ($b->chapter as $c) {
                $map[] = array($bn, (int)$c['number']);
            }
        }
    }
    $total = count($map);
    if ($total < 1) throw new Exception('no chapters');
    $day = (int)floor(time() / 86400);
    $id = (int)((701 * $day + 123) % $total);
    list($bookNo, $chNo) = $map[$id];

    $viVerses = chapter_verses($vi, $bookNo, $chNo);
    $enVerses = chapter_verses($en, $bookNo, $chNo);
    $vnums = array_unique(array_merge(array_keys($viVerses), array_keys($enVerses)));
    sort($vnums);

    $title = $VI_TITLES[$bookNo - 1] . ' ' . $chNo . ' · ' . $EN_TITLES[$bookNo - 1] . ' ' . $chNo;
} catch (Exception $e) {
    http_response_code(500);
    echo 'Lỗi tải Kinh Thánh / Bible load error.';
    exit;
}
?>
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title><?php echo htmlspecialchars($title, ENT_QUOTES, 'UTF-8'); ?></title>
  <link rel="stylesheet" type="text/css" href="/css.css"/>
  <style>main{max-width:42rem;margin:0 auto;padding:0 1.5rem 4rem;font-family:Georgia,serif;line-height:2}
  .verse-pair{margin:0 0 1.1em}.en{color:#555;border-left:3px solid #ddd;padding-left:1rem}</style>
</head>
<body>
<main>
<h1><?php echo htmlspecialchars($title, ENT_QUOTES, 'UTF-8'); ?></h1>
<p>Bản dịch mặc định: Tiếng Việt 1925 + NASB 1995.</p>
<?php foreach ($vnums as $v): $xv = isset($viVerses[$v]) ? $viVerses[$v] : ''; $xe = isset($enVerses[$v]) ? $enVerses[$v] : ''; if ($xv === '' && $xe === '') continue; ?>
  <div class="verse-pair"><p><sup><?php echo $v; ?></sup> <?php echo htmlspecialchars($xv, ENT_QUOTES, 'UTF-8'); ?></p>
  <?php if ($xe !== ''): ?><p class="en" lang="en"><sup><?php echo $v; ?></sup> <?php echo htmlspecialchars($xe, ENT_QUOTES, 'UTF-8'); ?></p><?php endif; ?></div>
<?php endforeach; ?>
</main>
</body>
</html>

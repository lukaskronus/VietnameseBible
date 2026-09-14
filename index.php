<?php
// Bilingual daily chapter (VI + EN), sourced from data/*.sqlite3.
// Rotation: chapter_id = (days_since_unix_epoch % 1189) + 1, same rule as
// the static site (tools/build_site.py + tools/static/daily.js).
header('Content-Type: text/html; charset=UTF-8');

function decodeVerse($vfloat) {
    $ch = (int)$vfloat;
    $v = (int)round(((float)$vfloat - $ch) * 1000);
    return array($ch, $v);
}

try {
    $viet = new PDO('sqlite:' . __DIR__ . '/data/viet.sqlite3');
    $nasb = new PDO('sqlite:' . __DIR__ . '/data/nasb.sqlite3');
    $viet->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $nasb->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

    $total = (int)$viet->query('SELECT COUNT(*) FROM chapters')->fetchColumn();
    if ($total < 1) { throw new Exception('no chapters'); }
    $id = (int)(floor(time() / 86400) % $total) + 1;

    $st = $viet->prepare('SELECT reference_osis FROM chapters WHERE id = ?');
    $st->execute(array($id));
    $ref = $st->fetchColumn(); // e.g. Gen.1
    list($bookOsis, $chNo) = explode('.', $ref);

    $st = $viet->prepare('SELECT human FROM books WHERE osis = ?');
    $st->execute(array($bookOsis));
    $bookVi = $st->fetchColumn();
    $st = $nasb->prepare('SELECT human FROM books WHERE osis = ?');
    $st->execute(array($bookOsis));
    $bookEn = $st->fetchColumn();

    // Headings come from the NASB chapter HTML (<h3>/<h4>), keyed by verse.
    $st = $nasb->prepare('SELECT content FROM chapters WHERE reference_osis = ?');
    $st->execute(array($ref));
    $html = $st->fetchColumn();
    $headings = array();
    if (preg_match_all('/<h[34][^>]*>(.*?)<\/h[34]>/s', $html, $m)) {
        foreach ($m[1] as $h) {
            $t = trim(html_entity_decode(strip_tags($h), ENT_QUOTES, 'UTF-8'));
            if ($t !== '') { $headings[] = $t; }
        }
    }

    $loadVerses = function ($pdo, $bookOsis) {
        $st = $pdo->prepare('SELECT verse, unformatted FROM verses WHERE book = ? ORDER BY verse');
        $st->execute(array($bookOsis));
        $out = array();
        while ($row = $st->fetch(PDO::FETCH_NUM)) {
            list($ch, $v) = decodeVerse($row[0]);
            $out[$ch][$v] = $row[1];
        }
        return $out;
    };
    $viAll = $loadVerses($viet, $bookOsis);
    $enAll = $loadVerses($nasb, $bookOsis);
    $viVerses = isset($viAll[(int)$chNo]) ? $viAll[(int)$chNo] : array();
    $enVerses = isset($enAll[(int)$chNo]) ? $enAll[(int)$chNo] : array();
    ksort($viVerses); ksort($enVerses);
    $vnums = array_unique(array_merge(array_keys($viVerses), array_keys($enVerses)));
    sort($vnums);

    $clean = function ($t) { return trim(preg_replace('/\s+/', ' ', str_replace("\n", ' ', $t))); };
    // Strip NASB heading repeat: "The Creation\nIn the beginning..."
    $stripHead = function ($t, $headings) use ($clean) {
        $parts = explode("\n", $t);
        if (count($parts) > 1) {
            $first = $clean($parts[0]);
            foreach ($headings as $h) {
                if ($first === $h) { array_shift($parts); return $clean(implode("\n", $parts)); }
            }
        }
        return $clean($t);
    };

    $title = $bookVi . ' ' . $chNo . ' · ' . $bookEn . ' ' . $chNo;
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
  .en{color:#555;border-left:3px solid #ddd;padding-left:1rem}h2.sec{color:#92400e;font-size:1rem;text-transform:uppercase}</style>
</head>
<body>
<main>
<h1><?php echo htmlspecialchars($title, ENT_QUOTES, 'UTF-8'); ?></h1>
<?php foreach ($headings as $h): ?>
  <h2 class="sec"><?php echo htmlspecialchars($h, ENT_QUOTES, 'UTF-8'); ?></h2>
<?php endforeach; ?>
<?php foreach ($vnums as $v): $vi = isset($viVerses[$v]) ? $clean($viVerses[$v]) : ''; $en = isset($enVerses[$v]) ? $stripHead($enVerses[$v], $headings) : ''; ?>
  <div class="verse-pair"><p><sup><?php echo $v; ?></sup> <?php echo htmlspecialchars($vi, ENT_QUOTES, 'UTF-8'); ?></p>
  <?php if ($en !== ''): ?><p class="en" lang="en"><sup><?php echo $v; ?></sup> <?php echo htmlspecialchars($en, ENT_QUOTES, 'UTF-8'); ?></p><?php endif; ?></div>
<?php endforeach; ?>
</main>
</body>
</html>

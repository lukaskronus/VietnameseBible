<?php
// Debug: dump one chapter (default id=1, ?id=N) from the default XML pair.
header('Content-Type: text/plain; charset=UTF-8');
$id = isset($_GET['id']) ? max(1, (int)$_GET['id']) : 1;
foreach (array('vi1925' => 'VietnameseBible.xml', 'ennasb' => 'EnglishNASBBible.xml') as $label => $fn) {
    echo "== $label ==\n";
    $xml = simplexml_load_file(__DIR__ . '/data/xml/' . $fn);
    $n = 0;
    foreach ($xml->testament as $t) {
        foreach ($t->book as $b) {
            foreach ($b->chapter as $c) {
                $n++;
                if ($n === $id) {
                    echo "book " . $b['number'] . " ch " . $c['number'] . "\n";
                    $k = 0;
                    foreach ($c->verse as $v) {
                        echo $v['number'] . ' | ' . mb_substr(trim((string)$v), 0, 100) . "\n";
                        if (++$k >= 5) break;
                    }
                }
            }
        }
    }
    echo "\n";
}
?>

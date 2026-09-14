<?php
// Debug: dump one bilingual chapter (default id=1, ?id=N) from sqlite sources.
header('Content-Type: text/plain; charset=UTF-8');
$id = isset($_GET['id']) ? (int)$_GET['id'] : 1;
$viet = new PDO('sqlite:' . __DIR__ . '/data/viet.sqlite3');
$nasb = new PDO('sqlite:' . __DIR__ . '/data/nasb.sqlite3');
$ref = $viet->query('SELECT reference_osis FROM chapters WHERE id = ' . $id)->fetchColumn();
echo "chapter $id = $ref\n\n";
foreach (array('viet' => $viet, 'nasb' => $nasb) as $label => $pdo) {
    echo "== $label ==\n";
    list($b, $c) = explode('.', $ref);
    $st = $pdo->prepare('SELECT verse, substr(unformatted, 1, 120) FROM verses WHERE book = ? ORDER BY verse LIMIT 5');
    $st->execute(array($b));
    foreach ($st->fetchAll(PDO::FETCH_NUM) as $row) {
        echo $row[0] . ' | ' . $row[1] . "\n";
    }
    echo "\n";
}
?>

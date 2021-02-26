<?php
header('Content-Type: text/html; charset=UTF-8');
$sql = new mysqli("asus.ml", "root", "root", "mydb");
if(mysqli_connect_error()){
	die(mysqli_connect_error());
}
$sql->set_charset("utf8");
$id = 178+round((time()-1440194290)/86400-0.5);

$res = $sql->query("SELECT `data` FROM `bible` WHERE `id`=".$id);
$data = $res->fetch_row();
$res = $sql->query("SELECT `title` FROM `bible` WHERE `id`=".$id);
$title = $res->fetch_row();
$sql->close();
?>
<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
    <title><?php
        echo $title[0];
    ?></title>
  <link rel="stylesheet" type="text/css" href="/css.css"/>
</head>
<body>
<?php
echo $data[0];
?>
</body>
</html>

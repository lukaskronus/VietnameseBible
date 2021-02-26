<?php
$id = 974;
$sql = new mysqli("asus.ml", "root", "root", "mydb");
if(mysqli_connect_error()){
	die(mysqli_connect_error());
}

$res = $sql->query("SELECT data FROM bible WHERE id=".$id);
$row = $res->fetch_row();
echo $row[0];



$sql->close();
?>
#!/usr/bin/perl
# this file generates bible's sql file for
# importing
use strict;
use warnings;

my$output = "";
$output.='
SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
SET time_zone = "+00:00";
DROP TABLE IF EXISTS `bible`;
CREATE TABLE `bible` (
  `id` int(11) DEFAULT NULL,
  `title` text,
  `data` longtext
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
';
my$sql_id=1;
my@filename = map { $_.'.txt' } split(/\s/,`cat list.txt`);
for (@filename) {  
    open my$f, "<$_";
    print "processing $_\n";
    my$n_doan = 1;
    my$read_title = 1;
    my$title = '';
    my@data;
    while (<$f>) {
        chomp $_;
        $_ =~ s/\s*$//;
        if ($read_title) {
            $read_title = 0;
            $_ =~ s/^...//;
            $title = $_;
        }
        $n_doan++ if ($_ eq ($n_doan+1));
        $data[$n_doan].=$_.'<br\>';
    }
    close $f;
    $output.="INSERT INTO `bible` (`id`, `title`, `data`) VALUES\n";
    for my$i(1..$n_doan) {
        $output.="($sql_id, '$title $i', '$data[$i]')";
        $output.= ($i==$n_doan? ";\n":",\n");
        $sql_id++;
    }
}
open(my$f, ">bible.sql");
print $f "$output";
close($f);

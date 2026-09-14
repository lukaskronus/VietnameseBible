"use strict";
function esc(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}
function base(){var b=document.querySelector('meta[name="kt-base"]');return b?b.content:""}
fetch(base()+"/data/chapters.json").then(function(r){return r.json()}).then(function(chs){
var id=(Math.floor(Date.now()/864e5)%chs.length)+1;
return fetch(base()+"/data/ch/"+id+".json").then(function(r){return r.json()})}).then(function(d){
var bp=base();
var title=d.book+" "+d.n;
if(d.book_en){title+=" · "+d.book_en+" "+d.n}
document.getElementById("daily-title").textContent=title;
document.getElementById("daily-link").href=bp+"/"+d.slug+"/"+d.n+"/";
var h="";
for(var i=0;i<d.blocks.length;i++){var b=d.blocks[i];
if(b.t==="h"){var hx=b.en||b.x||"";h+="<h2>"+esc(hx)+"</h2>"}
else{var vi=b.vi||b.x||"",en=b.en||"";
h+='<div class="verse-pair"><p class="reading vi"><sup>'+b.n+"</sup>"+esc(vi)+"</p>";
if(en){h+='<p class="reading en" lang="en"><sup>'+b.n+"</sup>"+esc(en)+"</p>"}
h+="</div>"}}
document.getElementById("daily-text").innerHTML=h}).catch(function(){
document.getElementById("daily-text").innerHTML="<p>Không tải được đoạn Kinh Thánh hôm nay.</p>"});

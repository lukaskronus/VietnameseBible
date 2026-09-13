"use strict";
function esc(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}
function base(){var b=document.querySelector('meta[name="kt-base"]');return b?b.content:""}
fetch(base()+"/data/chapters.json").then(function(r){return r.json()}).then(function(chs){
var id=(Math.floor(Date.now()/864e5)%chs.length)+1;
return fetch(base()+"/data/ch/"+id+".json").then(function(r){return r.json()})}).then(function(d){
var bp=base();document.getElementById("daily-title").textContent=d.book+" "+d.n;
document.getElementById("daily-link").href=bp+"/"+d.slug+"/"+d.n+"/";
var h="",p=[];for(var i=0;i<d.blocks.length;i++){var b=d.blocks[i];
if(b.t==="h"){if(p.length){h+='<p class="reading">'+p.join("")+"</p>";p=[]}
h+="<h2>"+esc(b.x)+"</h2>"}else{p.push("<sup>"+b.n+"</sup>"+esc(b.x)+" ")}}
if(p.length){h+='<p class="reading">'+p.join("")+"</p>"}
document.getElementById("daily-text").innerHTML=h}).catch(function(){
document.getElementById("daily-text").innerHTML="<p>Kh\u00f4ng t\u1ea3i \u0111\u01b0\u1ee3c \u0111o\u1ea1n Kinh Th\u00e1nh h\u00f4m nay.</p>"});

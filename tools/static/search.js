"use strict";
function fold(s){return s.normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/\u0111/g,"d").replace(/\u0110/g,"D").toLowerCase()}
function toks(s){var m=s.match(/[a-z0-9]+/g)||[];return m.filter(function(t){return t.length>=2})}
var IDX=null,CHS=null;
function esc(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}
function base(){var b=document.querySelector('meta[name="kt-base"]');return b?b.content:""}
function run(e){if(e){e.preventDefault()}var box=document.getElementById("q");var out=document.getElementById("results");var q=toks(fold(box.value));if(!q.length){out.innerHTML="<p>Vui l\u00f2ng nh\u1eadp \u00edt nh\u1ea5t 2 k\u00fd t\u1ef1.</p>";return}if(!IDX){out.innerHTML="<p>\u0110ang t\u1ea3i d\u1eef li\u1ec7u t\u00ecm ki\u1ebfm\u2026</p>";return}
var hit=null;for(var i=0;i<q.length;i++){var ids=IDX.index[q[i]]||[];if(hit===null){hit={};for(var j=0;j<ids.length;j++){hit[ids[j]]=1}}else{var nx={};for(var k=0;k<ids.length;k++){if(hit[ids[k]]){nx[ids[k]]=1}}hit=nx}if(!Object.keys(hit).length){break}}
var keys=Object.keys(hit||{}).map(Number).sort(function(a,b){return a-b});var bp=base();
if(!keys.length){out.innerHTML="<p>Kh\u00f4ng t\u00ecm th\u1ea5y k\u1ebft qu\u1ea3.</p>";return}
var h="<p>T\u00ecm th\u1ea5y "+keys.length+" \u0111o\u1ea1n.</p>";var lim=Math.min(keys.length,100);
for(var n=0;n<lim;n++){var c=CHS[keys[n]-1];h+='<a href="'+bp+"/"+c.slug+"/"+c.n+'/">'+esc(c.book)+" "+c.n+"</a>"}
if(keys.length>lim){h+="<p>\u2026ch\u1ec9 hi\u1ec3n th\u1ecb 100 k\u1ebft qu\u1ea3 \u0111\u1ea7u.</p>"}
out.innerHTML=h}
document.getElementById("search-form").addEventListener("submit",run);
Promise.all([fetch(base()+"/data/search_index.json").then(function(r){return r.json()}),fetch(base()+"/data/chapters.json").then(function(r){return r.json()})]).then(function(v){IDX=v[0];CHS=v[1];var pre=document.getElementById("q").value;if(pre){run()}}).catch(function(){document.getElementById("results").innerHTML="<p>Kh\u00f4ng t\u1ea3i \u0111\u01b0\u1ee3c d\u1eef li\u1ec7u t\u00ecm ki\u1ebfm.</p>"});

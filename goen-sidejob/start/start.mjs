import {T,W,Q,decodeAnswers,encodeAnswers,validAnswers,diagnoseAnswers,buildPrompt} from '../core.mjs';
import {copyText} from '../copy.mjs';
const $=id=>document.getElementById(id);
let answers=decodeAnswers(new URLSearchParams(location.hash.slice(1)).get('diagnosis'));
if(!answers)try{if(sessionStorage.getItem('goen.sidejob.completed')==='yes'){const a=JSON.parse(sessionStorage.getItem('goen.sidejob.answers'));if(validAnswers(a))answers=a;}}catch{}
if(!answers)$('missing').hidden=false;
else{
 $('ready').hidden=false;const r=diagnoseAnswers(answers);
 $('summary').textContent=`主タイプ：${T[r.primary].name} ／ 副タイプ：${T[r.secondary].name} ／ 働き方：${W[r.work].name}`;
 $('conditions').textContent=`使える時間：${Q[3][2][answers[3]][0]}。守りたいこと：${Q[4][2][answers[4]][0]}。`;
 $('prompt').value=buildPrompt(answers);
 const hash=new URLSearchParams({diagnosis:encodeAnswers(answers)}).toString();
 for(const [id,path] of [['goen-join','/join'],['goen-dashboard','/sidejob-start']]){const url=new URL(path,'https://goen-sites.honotoku.chatgpt.site');url.searchParams.set('from','sidejob');for(const key of ['ref','utm_source','utm_medium','utm_campaign']){const v=new URLSearchParams(location.search).get(key);if(v)url.searchParams.set(key,v.slice(0,100));}url.hash=hash;$(id).href=url.href;}
 $('revise').href='../#'+hash;
 try{sessionStorage.setItem('goen.sidejob.answers',JSON.stringify(answers));sessionStorage.setItem('goen.sidejob.completed','yes');}catch{}
 $('copy').addEventListener('click',()=>copyText($('prompt'),$('copy-status')));
}

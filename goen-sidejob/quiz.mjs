import {T,W,Q,validAnswers,encodeAnswers,decodeAnswers,diagnoseAnswers,buildPrompt} from './core.mjs';
import {copyText} from './copy.mjs';
const $=id=>document.getElementById(id);
const answers=Array(Q.length).fill(null);
let completed=false;
try { const saved=JSON.parse(sessionStorage.getItem('goen.sidejob.answers')||'null'); if(Array.isArray(saved)&&saved.length===Q.length) saved.forEach((v,i)=>{if(Number.isInteger(v)&&v>=0&&v<Q[i][2].length)answers[i]=v;}); completed=sessionStorage.getItem('goen.sidejob.completed')==='yes'; } catch {}
const fromHash=decodeAnswers(new URLSearchParams(location.hash.slice(1)).get('diagnosis'));
if(fromHash){answers.splice(0,answers.length,...fromHash);completed=true;}
Q.forEach((q,i)=>{
 const e=document.createElement('fieldset');e.className='q';e.id='q-'+i;
 const legend=document.createElement('legend');legend.className='qtitle';legend.textContent=`${i+1}. ${q[0]}`;e.append(legend);
 if(q[1]){const p=document.createElement('p');p.className='hint';p.textContent=q[1];e.append(p);}
 const opts=document.createElement('div');opts.className='opts';
 q[2].forEach((o,j)=>{const l=document.createElement('label');l.className='opt';const input=document.createElement('input');input.type='radio';input.name='q'+i;input.value=j;input.checked=answers[i]===j;input.addEventListener('change',()=>{answers[i]=j;completed=false;$('result').classList.remove('show');try{sessionStorage.setItem('goen.sidejob.answers',JSON.stringify(answers));sessionStorage.removeItem('goen.sidejob.completed');}catch{}progress();});const span=document.createElement('span');span.textContent=o[0];l.append(input,span);opts.append(l);});
 e.append(opts);$('questions').append(e);
});
function progress(){const n=answers.filter(Number.isInteger).length;$('pbar').style.width=n/10*100+'%';$('ptext').textContent=`${n} / 10`;}
function render(scroll=true){
 const missing=answers.findIndex(v=>!Number.isInteger(v));
 if(missing!==-1){$('quiz-error').textContent=`${missing+1}問目に回答してください。未回答の質問へ移動しました。`;$('q-'+missing).scrollIntoView({block:'center'});$('q-'+missing).querySelector('input').focus({preventScroll:true});return;}
 $('quiz-error').textContent='';
 const r=diagnoseAnswers(answers),A=T[r.primary],B=T[r.secondary],C=W[r.work],max=r.ranked[0][1]||1;
 $('tags').innerHTML=`<span class="tag">主タイプ：${A.name}</span><span class="tag">副タイプ：${B.name}</span><span class="tag work">働き方：${C.name}</span>`;
 $('rtitle').textContent=`${A.name} × ${C.name}`;$('rdesc').textContent=`${A.desc} また、${B.name}の要素もあります。${C.desc}`;
 $('scores').innerHTML=r.ranked.map(([k,v])=>`<div class="score"><span>${T[k].name.replace('型','')}</span><div class="bar"><i style="width:${Math.round(v/max*100)}%"></i></div><b>${v}</b></div>`).join('');
 $('examples').innerHTML=[...new Set([...A.ex,...B.ex])].slice(0,6).map(x=>`<div class="item">✓ ${x}</div>`).join('');
 $('workfit').innerHTML=[...C.fit,'使える時間：'+Q[3][2][answers[3]][0],'守りたいこと：'+Q[4][2][answers[4]][0]].map(x=>`<div class="item">${x}</div>`).join('');
 $('safety').innerHTML=[['勤務先ルール','就業規則・届出・許可の要否を確認'],['競業・利益相反','勤務先と競合しないか確認'],['秘密保持','顧客情報・社内資料を持ち出さない'],['時間・健康','睡眠・本業・家族時間を削りすぎない'],['契約・税務','契約条件・報酬・必要な税務手続きを確認']].map(([a,b])=>`<div class="safe"><i>✓</i><div><b>${a}</b><br>${b}</div></div>`).join('');
 $('steps').innerHTML=A.st.map((x,i)=>`<div class="item">${i+1}. ${x}</div>`).join('');
 $('result-text').value=buildPrompt(answers);
 const next=new URL('./start/',location.href);for(const key of ['ref','utm_source','utm_medium','utm_campaign']){const v=new URLSearchParams(location.search).get(key);if(v)next.searchParams.set(key,v.slice(0,100));}
 next.hash=new URLSearchParams({diagnosis:encodeAnswers(answers)}).toString();$('continue-goen').href=next.href;
 try{sessionStorage.setItem('goen.sidejob.completed','yes');}catch{}
 $('result').classList.add('show');if(scroll)$('result').scrollIntoView({block:'start'});
}
$('begin-quiz').addEventListener('click',()=>$('quiz').scrollIntoView());$('show-result').addEventListener('click',()=>render());
$('copy-result').addEventListener('click',()=>copyText($('result-text'),$('copy-status')));
progress();if(completed&&validAnswers(answers))render(false);

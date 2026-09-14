import test from 'node:test';
import assert from 'node:assert/strict';
import {encodeAnswers,decodeAnswers,diagnoseAnswers,buildPrompt,validAnswers} from './core.mjs';
import {copyText} from './copy.mjs';
const answers=[0,0,0,0,0,0,0,2,1,0];
test('diagnosis round-trips through the URL fragment without losing constraints',()=>{
 const url=new URL('https://goen.example/join');url.hash=new URLSearchParams({diagnosis:encodeAnswers(answers)}).toString();
 const received=decodeAnswers(new URLSearchParams(url.hash.slice(1)).get('diagnosis'));
 assert.deepEqual(received,answers);assert.equal(diagnoseAnswers(received).primary,'people');
 const prompt=buildPrompt(received);assert.match(prompt,/平日30分〜1時間/);assert.match(prompt,/夜の家族時間/);assert.match(prompt,/長時間拘束/);assert.match(prompt,/公開前/);assert.ok(prompt.includes('\n'));assert.ok(!prompt.includes('\\n'));
});
test('missing, old, malformed and out-of-range answers are rejected',()=>{
 for(const s of [null,'','v2.0,0,0,0,0,0,0,0,0,0','v1.0,0','v1.0,4,0,0,0,0,0,0,0,0','<script>','v1.0,0,0,0,0,0,0,0,0,-1'])assert.equal(decodeAnswers(s),null);
 assert.equal(validAnswers(Array(10).fill(null)),false);assert.throws(()=>buildPrompt([]));
});
test('copy success and denied clipboard both leave clear feedback',async()=>{
 const original=Object.getOwnPropertyDescriptor(globalThis,'navigator');const oldDoc=globalThis.document;
 const field={value:'diagnosis',focus(){},select(){},setSelectionRange(){}};const status={textContent:''};
 try{Object.defineProperty(globalThis,'navigator',{configurable:true,value:{clipboard:{async writeText(v){assert.equal(v,'diagnosis');}}}});assert.equal(await copyText(field,status),true);assert.match(status.textContent,/コピーしました/);
 Object.defineProperty(globalThis,'navigator',{configurable:true,value:{clipboard:{async writeText(){throw Error('denied');}}}});globalThis.document={execCommand:()=>false};assert.equal(await copyText(field,status),false);assert.match(status.textContent,/長押し/);
 }finally{if(original)Object.defineProperty(globalThis,'navigator',original);else delete globalThis.navigator;globalThis.document=oldDoc;}
});

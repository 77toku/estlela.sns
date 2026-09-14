export async function copyText(field,status){
 try{await navigator.clipboard.writeText(field.value);status.textContent='コピーしました。AIの会話に貼り付けてください。';return true;}
 catch{field.focus();field.select();field.setSelectionRange(0,field.value.length);try{if(document.execCommand('copy')){status.textContent='コピーしました。AIの会話に貼り付けてください。';return true;}}catch{}status.textContent='自動コピーができませんでした。下の文章を長押しして「すべて選択」→「コピー」を選んでください。';return false;}
}

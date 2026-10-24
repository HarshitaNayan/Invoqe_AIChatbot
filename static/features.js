/* Hynex enhancements: original UI and original chat functions are preserved. */
(() => {
'use strict';
let authRequired=false;
// Memory only: reload, closing the tab or signing out clears this key.
let geminiKey='';
function keyPanel(){
  const box=panel('Your Gemini API key');
  box.append(element('p','Use your own Gemini key and quota for chat, file summaries, quizzes and flashcards. Your key is kept only in this page’s memory, and is cleared on reload, tab close or sign-out. It passes through the Hynex backend to Google; it is not saved in our database. Use only a Hynex host you trust.'));
  const input=field(box,'Gemini API key','password');input.autocomplete='off';input.spellcheck=false;
  input.placeholder=geminiKey?'A key is already set. Paste to replace it.':'Paste your Gemini API key';
  const msg=errorBox(box);
  box.append(button('Use key for this tab',()=>{
    const key=input.value.trim();
    if(!/^[A-Za-z0-9._-]{20,2048}$/.test(key)){msg.textContent='Paste only your Gemini API key (no quotes or variable name).';return}
    geminiKey=key;input.value='';dialog.close();toast('Key set for this tab. It will be checked when you make an AI request.');
  },'fx-primary'),button('Remove key',()=>{geminiKey='';input.value='';dialog.close();toast('Key removed. Basic offline chat remains available.')}));
  const link=element('a','Get a Gemini API key in Google AI Studio');link.href='https://aistudio.google.com/apikey';link.target='_blank';link.rel='noopener noreferrer';box.append(link);
}
function aiHeaders(){return geminiKey?{'X-Gemini-API-Key':geminiKey}:{}}

let user=null, version=0, syncTimer, syncBlocked=false, syncRunning=false, dirty=false;
let selectedIds=[], recognition=null, listening=false;
const hex=()=>Array.from(crypto.getRandomValues(new Uint8Array(32)),b=>b.toString(16).padStart(2,'0')).join('');
let guest=localStorage.getItem('hynex_guest');
if(!/^[a-f0-9]{64}$/.test(guest||'')){guest=hex();localStorage.setItem('hynex_guest',guest)}
const originalFetch=window.fetch.bind(window);
const localKey=()=>user?'hynex_account_'+user.id:'hynex';
const status=t=>{$('feature-status').textContent=t};
function toast(t){let el=$('fx-toast');if(!el){el=document.createElement('div');el.id='fx-toast';el.setAttribute('role','status');document.body.append(el)}el.textContent=t;clearTimeout(el.timer);el.timer=setTimeout(()=>el.remove(),6500)}
async function api(path,opts={}){
  const headers={'X-Guest-ID':guest,...opts.headers,...(['/study','/summarize'].includes(path)?aiHeaders():{})};
  if(opts.body && !(opts.body instanceof FormData))headers['Content-Type']='application/json';
  const r=await originalFetch('/api'+path,{...opts,headers});
  if(!r.ok){let data;try{data=await r.json()}catch{}throw new Error(typeof data?.detail==='string'?data.detail:'Request failed. Please try again.')}
  return r;
}
function button(text,fn,cls='fx-btn'){const b=document.createElement('button');b.type='button';b.className=cls;b.textContent=text;b.onclick=fn;return b}
function element(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e}
const controls=element('div',undefined);controls.id='feature-controls';
const statusEl=element('div','Guest · chats saved in this browser');statusEl.id='feature-status';
$('side').append(controls,statusEl);
const toolbar=element('div');toolbar.id='feature-toolbar';$('bar').prepend(toolbar);
const attached=element('span');attached.id='attachment-status';attached.setAttribute('aria-live','polite');
const fileChips=element('div');fileChips.id='attachment-chips';
const fileNames=new Map();let fileRefresh=false;
function attachmentStatus(){
  toolbar.hidden=!selectedIds.length;
  attached.textContent=selectedIds.length?`${selectedIds.length} attached`:'';
  fileChips.replaceChildren();
  selectedIds.forEach(id=>{
    const chip=element('div',undefined,'fx-attachment');
    const name=fileNames.get(id)||'Attached file';
    const open=button(name,filePanel,'fx-file-name');open.title='Manage '+name;
    const remove=button('×',()=>{selectedIds=selectedIds.filter(v=>v!==id);rememberAttachments()},'fx-file-remove');
    remove.title='Detach '+name;remove.setAttribute('aria-label','Detach '+name);
    chip.append(open,remove);fileChips.append(chip);
  });
  if(selectedIds.some(id=>!fileNames.has(id))&&!fileRefresh){
    fileRefresh=true;api('/uploads').then(r=>r.json()).then(files=>{files.forEach(f=>fileNames.set(f.id,f.name));if(selectedIds.every(id=>fileNames.has(id)))attachmentStatus()}).catch(()=>{}).finally(()=>fileRefresh=false);
  }
}
const dialog=document.createElement('dialog');dialog.id='fx-dialog';document.body.append(dialog);
function panel(title){
  if(dialog.open)dialog.close();dialog.replaceChildren();
  const head=element('div',undefined,'fx-head');head.append(element('h2',title),button('Close',()=>dialog.close()));
  const content=element('div');dialog.append(head,content);dialog.showModal();return content;
}
function errorBox(parent){const e=element('div','','fx-message');e.setAttribute('role','status');parent.append(e);return e}
function field(parent,label,type='text',value=''){
  const l=element('label',label),i=document.createElement(type==='textarea'?'textarea':'input');
  if(type!=='textarea')i.type=type;i.value=value;l.append(i);parent.append(l);return i;
}
function download(name,text,type='text/plain'){
  const url=URL.createObjectURL(new Blob([text],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function safeLoad(key){try{const v=JSON.parse(localStorage.getItem(key)||'[]');return Array.isArray(v)?v:[]}catch{return[]}}
function localSave(){localStorage.setItem(localKey(),JSON.stringify(chats))}
store.set=()=>{localSave();if(user){dirty=true;clearTimeout(syncTimer);syncTimer=setTimeout(sync,450)}};
async function sync(){
  if(!user||syncBlocked||syncRunning||!dirty)return;
  syncRunning=true;const account=user.id;dirty=false;status('Saving chats…');
  try{
    const snapshot=JSON.parse(JSON.stringify(chats));
    const data=await (await api('/chats',{method:'PUT',body:JSON.stringify({version,chats:snapshot})})).json();
    if(user?.id===account){version=data.version;status('Signed in as '+user.username+' · synced')}
  }catch(e){syncBlocked=true;dirty=true;status('Sync paused · local copy retained');toast(e.message)}
  finally{syncRunning=false;if(dirty&&!syncBlocked&&user)setTimeout(sync,100)}
}
// Preserve the original stream request and add only selected attachment IDs.
window.fetch=(input,opts={})=>{
  if(input==='/chat'){
    const payload=JSON.parse(opts.body);payload.attachment_ids=selectedIds.slice();payload.history=(payload.history||[]).slice(-10);
    const c=chats.find(c=>c.id===cur);if(c)c.attachment_ids=selectedIds.slice();
    opts={...opts,body:JSON.stringify(payload),headers:{...opts.headers,'X-Guest-ID':guest,...aiHeaders()}};
  }
  return originalFetch(input,opts);
};
const baseRender=renderList;
renderList=function(){
  baseRender();
  document.querySelectorAll('#list .row').forEach(r=>{
    const title=r.querySelector('.item').textContent;
    // Resolve by the original visual order, including pins, rather than a possibly duplicate title.
    const ordered=[...chats.filter(c=>c.pinned),...chats.filter(c=>!c.pinned)];
    const index=Array.from(document.querySelectorAll('#list .row')).indexOf(r),chat=ordered[index];
    if(!chat)return;
    const b=button('✎',()=>{const value=prompt('Rename chat',chat.title);if(value?.trim()){chat.title=value.trim().slice(0,120);store.set(chats);renderList()}},'act');b.title='Rename chat';b.setAttribute('aria-label','Rename '+title);r.querySelector('.acts').prepend(b);
  });
};
const baseOpen=open_;open_=function(id){if(busy){toast('Wait for the current reply to finish.');return}selectedIds=(chats.find(c=>c.id===id)?.attachment_ids||[]).slice();attachmentStatus();baseOpen(id)};
const baseNew=newChat;newChat=function(){if(busy){toast('Wait for the current reply to finish.');return}selectedIds=[];attachmentStatus();baseNew()};
const baseSend=send;
send=function(text){if(authRequired&&!user){toast('Sign in to use Hynex.');accountPanel();return}return baseSend(text)};
const baseRow=row;
row=function(role,text){
  const body=baseRow(role,text);
  if(role!=='user'){
    const tools=element('div',undefined,'fx-reply-tools');
    tools.append(button('Review answer',()=>qualityPanel(body.textContent)),button('Sources',()=>sourcePanel()));
    body.parentElement.append(tools);
  }
  return body;
};
function themePanel(){
  const box=panel('Appearance');
  const mode=element('label','Mode'),select=document.createElement('select');
  ['dark','light'].forEach(v=>{const o=element('option',v[0].toUpperCase()+v.slice(1));o.value=v;select.append(o)});
  select.value=localStorage.hynex_theme||'dark';select.onchange=()=>{document.body.dataset.theme=select.value;localStorage.hynex_theme=select.value};mode.append(select);box.append(mode);
  const accent=element('label','Accent'),colors=document.createElement('select');
  [['red','Original red'],['wine','Wine'],['teal','Teal'],['blue','Blue']].forEach(([v,t])=>{const o=element('option',t);o.value=v;colors.append(o)});
  colors.value=localStorage.hynex_accent||'red';colors.onchange=()=>{document.body.dataset.accent=colors.value;localStorage.hynex_accent=colors.value};accent.append(colors);box.append(accent);
}
async function loadAccount(u){
  const data=await (await api('/chats')).json();
  user=u;version=data.version;syncBlocked=false;dirty=false;clearTimeout(syncTimer);
  chats=data.chats;localSave();selectedIds=[];cur=null;renderList();welcome();attachmentStatus();
  status('Signed in as '+u.username+' · synced');
}
async function accountPanel(){
  if(busy||syncRunning){toast('Wait for the current operation to finish.');return}
  const box=panel(user?'Your account':'Account & chat storage');
  box.append(button('API key',keyPanel));
  if(user){
    box.append(element('p','Signed in as '+user.username+'. Account chats are stored on this server. Guest chats stay separate in your browser.'));
    box.append(button('Import guest chats into account',async()=>{
      if(!confirm('Copy guest chats from this browser into this account? Existing account chats will be kept.'))return;
      const existing=new Set(chats.map(c=>String(c.id)));
      const imported=safeLoad('hynex').filter(c=>!existing.has(String(c.id))).map(c=>({...c,attachment_ids:[]}));
      chats=[...imported,...chats];store.set(chats);renderList();toast('Imported '+imported.length+' chats.');
    }));
    box.append(button('Retry chat sync',async()=>{try{const data=await (await api('/chats')).json();if(data.version!==version){toast('Another tab changed the server copy. Export your local chats, then reload.');return}syncBlocked=false;dirty=true;await sync()}catch(e){toast(e.message)}}));
    box.append(button('Export account chats',()=>download('hynex-account-chats.json',JSON.stringify(chats,null,2),'application/json')));
    box.append(button('Sign out',async()=>{
      if(syncRunning||busy){toast('Wait for the current operation to finish.');return}
      clearTimeout(syncTimer);if(dirty){await sync();if(dirty){toast('Sync has not finished. Export your chats or resolve the sync issue before signing out.');return}}
      try{await api('/auth/logout',{method:'POST'});user=null;geminiKey='';chats=safeLoad('hynex');cur=null;selectedIds=[];renderList();welcome();attachmentStatus();status('Guest · chats saved in this browser');dialog.close()}catch(e){toast(e.message)}
    }));return;
  }
  const google=button('Continue with Google',()=>{window.location.assign('/api/auth/google/start')},'fx-google');
  google.disabled=true;box.append(google);
  const googleNote=element('p','Checking Google sign-in…');box.append(googleNote);
  api('/auth/config').then(r=>r.json()).then(config=>{
    authRequired=config.require_login;google.disabled=!config.google_enabled;
    googleNote.textContent=config.google_enabled?'Google opens its own secure sign-in page. Hynex never asks for your Google password.':'Google sign-in needs one-time setup by the app owner. See GOOGLE_SIGN_IN_SETUP.md. Local account sign-in is available below.';
  }).catch(()=>{googleNote.textContent='Could not load Google sign-in settings. Try again.'});
  box.append(element('p','Or use a Hynex account below. This password belongs to Hynex, not Google. Usernames use lowercase letters, digits and underscores. Passwords need at least 10 characters.'));
  const form=document.createElement('form');box.append(form);
  const username=field(form,'Username'),password=field(form,'Password','password');username.autocomplete='username';password.autocomplete='current-password';
  const error=errorBox(form);let register=false;
  const login=button('Sign in',()=>{register=false;form.requestSubmit()},'fx-primary');
  const create=button('Create account',()=>{register=true;form.requestSubmit()});form.append(login,create);
  form.onsubmit=async e=>{e.preventDefault();login.disabled=create.disabled=true;error.textContent='';try{
    const u=await (await api('/auth/'+(register?'register':'login'),{method:'POST',body:JSON.stringify({username:username.value,password:password.value})})).json();await loadAccount(u);dialog.close();toast('Signed in. Guest chats were kept separately.');
  }catch(e){error.textContent=e.message}finally{login.disabled=create.disabled=false}};
}
function rememberAttachments(){const c=chats.find(c=>c.id===cur);if(c){c.attachment_ids=selectedIds.slice();store.set(chats)}attachmentStatus()}
async function filePanel(){
  const box=panel('Files & summaries');
  box.append(element('p','Attach PDF, TXT/MD, PNG, JPG or WEBP (up to 5 MB each). Select at most six files for this chat. Attached content is sent to Gemini when you ask a question or request a summary. Summaries of text sources use the first 30,000 characters per file. Guest uploads expire after one day; account files stay on this server until deleted.'));
  const pick=document.createElement('input');pick.type='file';pick.multiple=true;pick.accept='.pdf,.txt,.md,.png,.jpg,.jpeg,.webp';pick.setAttribute('aria-label','Upload study files');box.append(pick);
  const msg=errorBox(box),list=element('div',undefined,'fx-stack');box.append(list);
  const output=element('div',undefined,'fx-output');box.append(output);
  async function refresh(){
    const files=await (await api('/uploads')).json();files.forEach(f=>fileNames.set(f.id,f.name));const available=new Set(files.map(f=>f.id));selectedIds=selectedIds.filter(id=>available.has(id));rememberAttachments();list.replaceChildren();
    if(!files.length)list.append(element('p','No files uploaded yet.'));
    for(const file of files){
      const row=element('div',undefined,'fx-file'),check=document.createElement('input');check.type='checkbox';check.checked=selectedIds.includes(file.id);check.setAttribute('aria-label','Attach '+file.name);
      check.onchange=()=>{if(check.checked){if(selectedIds.length>=6){check.checked=false;toast('Select up to six files.');return}selectedIds.push(file.id)}else selectedIds=selectedIds.filter(id=>id!==file.id);rememberAttachments()};
      row.append(check,element('span',file.name,'name'),button('Remove',async()=>{if(!confirm('Delete '+file.name+' from your file library?'))return;try{await api('/uploads/'+file.id,{method:'DELETE'});await refresh()}catch(e){msg.textContent=e.message}}));list.append(row);
    }
  }
  pick.onchange=async()=>{pick.disabled=true;msg.textContent='Uploading…';try{
    for(const file of pick.files){if(file.size>5*1024*1024)throw Error('Each file must be smaller than 5 MB.');const data=new FormData();data.append('file',file);const f=await (await api('/uploads',{method:'POST',body:data})).json();fileNames.set(f.id,f.name);if(selectedIds.length<6)selectedIds.push(f.id)}
    msg.textContent='Uploaded. Selected files will be attached to your next message.';await refresh();
  }catch(e){msg.textContent=e.message}finally{pick.disabled=false;pick.value=''}};
  const summary=button('Summarize selected files',async()=>{
    if(!selectedIds.length){msg.textContent='Select at least one file.';return}summary.disabled=true;output.textContent='';msg.textContent='Generating summary…';
    try{const r=await api('/summarize',{method:'POST',body:JSON.stringify({attachment_ids:selectedIds})}),reader=r.body.getReader(),decoder=new TextDecoder();for(;;){const {value,done}=await reader.read();if(done)break;output.textContent+=decoder.decode(value,{stream:true})}msg.textContent='Summary response received.'}
    catch(e){msg.textContent=e.message}finally{summary.disabled=false}
  },'fx-primary');box.insertBefore(summary,output);
  try{await refresh()}catch(e){msg.textContent=e.message}
}
function studyPanel(){
  const box=panel('Quiz & flashcards');box.append(element('p','Choose a topic or use the files currently attached to your chat. Generated content may contain mistakes; verify it against your notes.'));
  const topic=field(box,'Topic or instructions'),label=element('label','Activity'),kind=document.createElement('select');
  for(const [v,t] of [['quiz','Multiple-choice quiz'],['flashcards','Flashcards']]){const o=element('option',t);o.value=v;kind.append(o)}label.append(kind);box.append(label);
  const count=field(box,'Number of items (1–10)','number','5');count.min=1;count.max=10;
  const error=errorBox(box),result=element('div',undefined,'fx-stack');
  const run=button('Generate',async()=>{
    if(!topic.value.trim()){error.textContent='Enter a topic first.';return}run.disabled=true;error.textContent='Generating…';result.replaceChildren();
    try{
      const data=await (await api('/study',{method:'POST',body:JSON.stringify({topic:topic.value,kind:kind.value,count:Number(count.value),attachment_ids:selectedIds})})).json();error.textContent='';
      if(data.cards){data.cards.forEach((c,i)=>{const details=element('details',undefined,'fx-card');details.append(element('summary',(i+1)+'. '+c.front),element('p',c.back));result.append(details)});return}
      const form=document.createElement('form'),choices=[],explanations=[];result.append(form);
      data.questions.forEach((q,i)=>{
        const card=element('div',undefined,'fx-question');card.append(element('strong',(i+1)+'. '+q.question));const radios=[];
        q.options.forEach((o,j)=>{const label=element('label'),radio=document.createElement('input');radio.type='radio';radio.name='question_'+i;radio.value=j;radios.push(radio);label.append(radio,document.createTextNode(o));card.append(label)});
        const explanation=element('p');card.append(explanation);form.append(card);choices.push(radios);explanations.push(explanation);
      });
      const grade=element('button','Check answers','fx-primary');grade.type='submit';const score=element('p');form.append(grade,score);
      form.onsubmit=e=>{e.preventDefault();if(choices.some(rs=>!rs.some(r=>r.checked))){score.textContent='Answer every question before checking.';return}let correct=0;data.questions.forEach((q,i)=>{const chosen=choices[i].findIndex(r=>r.checked),ok=chosen===q.correct_index;if(ok)correct++;explanations[i].textContent=(ok?'Correct. ':'Incorrect. ')+'Answer: '+q.options[q.correct_index]+'. '+q.explanation});score.textContent='Score: '+correct+' / '+data.questions.length};
    }catch(e){error.textContent=e.message}finally{run.disabled=false}
  },'fx-primary');box.append(run,result);
}
function voice(){
  const Speech=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!Speech){toast('Voice input is unavailable in this browser. Please type your message.');return}
  if(listening){recognition.stop();return}
  recognition=new Speech();recognition.lang='en-IN';recognition.interimResults=false;
  recognition.onstart=()=>{listening=true;setMicState(true);toast('Listening. Your browser may send audio to its speech service. Review the text before sending.')};
  recognition.onresult=e=>{const spoken=Array.from(e.results).map(r=>r[0].transcript).join(' ');$('in').value=($('in').value+' '+spoken).trim();$('in').dispatchEvent(new Event('input'));$('in').focus()};
  recognition.onerror=e=>toast('Voice input: '+e.error+'. You can still type your message.');
  recognition.onend=()=>{listening=false;setMicState(false)};try{recognition.start()}catch{toast('Could not start the microphone.')}
}
function lastAnswer(){const c=chats.find(c=>c.id===cur);return c?.messages.filter(m=>m.role==='assistant').at(-1)?.content||''}
function lastQuestion(){const c=chats.find(c=>c.id===cur);return c?.messages.filter(m=>m.role==='user').at(-1)?.content||''}
function qualityPanel(answer=lastAnswer()){
  const box=panel('Review answer quality');box.append(element('p','Compare an answer with your own trusted reference and record a human rating. Word overlap does not establish factual correctness.'));
  const value=field(box,'Answer to review','textarea',answer),reference=field(box,'Trusted reference (optional)','textarea'),rating=field(box,'Your rating (1–5)','number','3');rating.min=1;rating.max=5;
  const comment=field(box,'Review notes (optional)','textarea'),msg=errorBox(box),output=element('div',undefined,'fx-output');
  box.append(button('Compare wording',async()=>{try{const r=await (await api('/quality/check',{method:'POST',body:JSON.stringify({answer:value.value,reference:reference.value})})).json();output.textContent='Words: '+r.word_count+(r.token_f1!==undefined?'\nReference token F1: '+r.token_f1+'\nPrecision: '+r.precision+' · Recall: '+r.recall:'\nAdd a reference to calculate overlap.')+'\n'+r.notice}catch(e){msg.textContent=e.message}}));
  box.append(button('Save my rating',async()=>{try{await api('/quality/feedback',{method:'POST',body:JSON.stringify({question:lastQuestion(),answer:value.value,rating:Number(rating.value),comment:comment.value})});msg.textContent='Your rating was saved.'}catch(e){msg.textContent=e.message}},'fx-primary'));
  box.append(button('Export my feedback',async()=>{try{const data=await (await api('/quality/feedback')).json();download('hynex-feedback.json',JSON.stringify(data,null,2),'application/json')}catch(e){msg.textContent=e.message}}),output);
}
async function sourcePanel(){
  const box=panel('Knowledge search'),query=field(box,'Search question','text',lastQuestion()),msg=errorBox(box),out=element('div',undefined,'fx-stack');
  box.append(element('p','Hybrid TF-IDF and local LSA embeddings search the bundled notes and your selected text attachments. Scores measure retrieval similarity, not answer correctness. Image content is understood by Gemini, not this local index.'));
  const run=async()=>{try{out.replaceChildren();const data=await (await api('/knowledge/search',{method:'POST',body:JSON.stringify({query:query.value,attachment_ids:selectedIds})})).json();if(!data.hits.length)out.append(element('p','No matching reference notes found.'));for(const hit of data.hits){const card=element('div',undefined,'fx-card');card.append(element('strong',hit.source+' · '+hit.score),element('p',hit.text));out.append(card)}}catch(e){msg.textContent=e.message}};
  box.append(button('Search notes',run,'fx-primary'),out);if(query.value)await run();
}
controls.append(button('API key',keyPanel),button('Appearance',themePanel),button('Account',accountPanel),button('Review',()=>qualityPanel()),button('Knowledge',sourcePanel));
// Compact composer: add on the left, dictation beside the existing send button.
const svg=(paths)=>'<svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+paths+'</svg>';
const micIcon=svg('<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/>');
const stopIcon=svg('<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none"/>');
function iconButton(label,icon,fn){const b=button('',fn,'fx-composer-icon');b.innerHTML=icon;b.title=label;b.setAttribute('aria-label',label);return b}
const quickPicker=document.createElement('input');quickPicker.type='file';quickPicker.hidden=true;quickPicker.multiple=true;quickPicker.accept='.pdf,.txt,.md,.png,.jpg,.jpeg,.webp';quickPicker.id='composer-file-input';
const attach=iconButton('Add files',svg('<path d="M12 5v14M5 12h14"/>'),()=>{
  if(authRequired&&!user){accountPanel();return}quickPicker.click();
});attach.id='composer-attach';
const mic=iconButton('Use microphone',micIcon,voice);mic.id='composer-mic';mic.setAttribute('aria-pressed','false');
function setMicState(active){mic.innerHTML=active?stopIcon:micIcon;mic.classList.toggle('is-listening',active);mic.setAttribute('aria-pressed',String(active));mic.setAttribute('aria-label',active?'Stop dictation':'Use microphone');mic.title=active?'Stop dictation':'Use microphone'}
quickPicker.onchange=async()=>{
  const pending=Array.from(quickPicker.files);
  if(pending.length+selectedIds.length>6){toast('Attach up to six files. Detach one first.');quickPicker.value='';return}
  attach.disabled=true;attach.setAttribute('aria-busy','true');
  try{
    for(const file of pending){
      if(file.size>5*1024*1024)throw Error('Each file must be smaller than 5 MB.');
      const form=new FormData();form.append('file',file);
      const doc=await (await api('/uploads',{method:'POST',body:form})).json();
      fileNames.set(doc.id,doc.name);selectedIds.push(doc.id);rememberAttachments();
    }
    if(pending.length)toast('Files attached. Ask a question, or click a file chip to summarize or manage files.');
  }catch(e){toast(e.message)}finally{attach.disabled=false;attach.removeAttribute('aria-busy');quickPicker.value=''}
};
$('box').prepend(attach);$('box').insertBefore(mic,$('go'));$('box').append(quickPicker);
controls.append(button('Quiz / flashcards',studyPanel),button('Files',filePanel));
toolbar.append(fileChips,attached);attachmentStatus();
document.body.dataset.theme=localStorage.hynex_theme||'dark';document.body.dataset.accent=localStorage.hynex_accent||'red';
renderList();
// Restore account chats without deleting the existing guest localStorage key.
(async()=>{try{
  const config=await (await api('/auth/config')).json();authRequired=config.require_login;
  const data=await (await api('/auth/me')).json();
  if(data.user){if(busy){toast('Signed-in session detected. Finish this reply, then reload to load account chats.');return}await loadAccount(data.user)}
  else if(authRequired){status('Sign in required');await accountPanel()}
  const result=new URLSearchParams(location.search).get('signin');
  if(result){toast(result==='cancelled'?'Google sign-in was cancelled.':'Google sign-in could not be completed. Try again or check the setup.');history.replaceState(null,'',location.pathname)}
}catch{status('Guest · account service unavailable')}})();
})();

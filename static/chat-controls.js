/* Additional chat controls. Loaded after features.js. */
(()=>{
'use strict';
const byId=id=>document.getElementById(id);
const notice=text=>{let n=byId('chat-control-status');if(!n){n=document.createElement('div');n.id='chat-control-status';n.setAttribute('role','status');document.body.append(n)}n.textContent=text;clearTimeout(n.timer);n.timer=setTimeout(()=>n.remove(),4500)};
const makeButton=(label,action)=>{const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=action;return b};
const side=byId('side'),menu=byId('menu');
const mobile=()=>matchMedia('(max-width: 760px)').matches;
function toggleSide(){if(mobile()){side.classList.toggle('open');menu.setAttribute('aria-expanded',String(side.classList.contains('open')))}else{document.body.classList.toggle('sidebar-collapsed');localStorage.setItem('hynex_sidebar_collapsed',String(document.body.classList.contains('sidebar-collapsed')));menu.setAttribute('aria-expanded',String(!document.body.classList.contains('sidebar-collapsed')))}}
if(localStorage.getItem('hynex_sidebar_collapsed')==='true')document.body.classList.add('sidebar-collapsed');
menu.textContent='☰';menu.title='Toggle sidebar';menu.setAttribute('aria-label','Toggle sidebar');menu.setAttribute('aria-controls','side');menu.setAttribute('aria-expanded',String(!mobile()&&!document.body.classList.contains('sidebar-collapsed')));menu.onclick=toggleSide;
const close=makeButton('‹',toggleSide);close.id='sidebar-close';close.title='Close sidebar';close.setAttribute('aria-label','Close sidebar');side.querySelector('.brand').append(close);
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&mobile()){side.classList.remove('open');menu.setAttribute('aria-expanded','false')}});
async function copyText(text){try{await navigator.clipboard.writeText(text);notice('Message copied.')}catch{const box=document.createElement('textarea');box.value=text;document.body.append(box);box.select();const ok=document.execCommand('copy');box.remove();notice(ok?'Message copied.':'Copy unavailable. Select the message and press Ctrl+C.')}}
function current(){return chats.find(c=>c.id===cur)}
function messageIndex(node){return Array.from(byId('msgs').children).filter(el=>el.classList.contains('msg')).indexOf(node)}
async function regenerate(index,text){if(busy){notice('Wait for the current reply to finish.');return}const chat=current();if(!chat||index<0)return;if(index<chat.messages.length-2&&!confirm('This will replace this message and the replies after it. Continue?'))return;chat.messages=chat.messages.slice(0,index);store.set(chats);open_(chat.id);await send(text)}
function editMessage(index){if(busy){notice('Wait for the current reply to finish.');return}const chat=current(),message=chat?.messages[index];if(!message||message.role!=='user')return;
const dialog=document.createElement('dialog');dialog.className='message-edit';const title=document.createElement('h3');title.textContent='Edit message';const input=document.createElement('textarea');input.value=message.content;input.setAttribute('aria-label','Edit your message');const actions=document.createElement('div');const cancel=makeButton('Cancel',()=>dialog.close());const save=makeButton('Save and send',async()=>{const text=input.value.trim();if(!text){input.focus();return}dialog.close();await regenerate(index,text)});actions.append(cancel,save);dialog.append(title,input,actions);document.body.append(dialog);dialog.addEventListener('close',()=>dialog.remove(),{once:true});dialog.showModal();input.focus()}
const previousRow=row;
row=function(role,text){const body=previousRow(role,text),node=body.closest('.msg'),tools=document.createElement('div');tools.className='message-actions';
tools.append(makeButton('Copy',()=>{const m=current()?.messages[messageIndex(node)];copyText(m?.content||body.textContent)}));
if(role==='user')tools.append(makeButton('Edit',()=>editMessage(messageIndex(node))));
else tools.append(makeButton('Retry',async()=>{const chat=current();let i=messageIndex(node)-1;while(i>=0&&chat?.messages[i]?.role!=='user')i--;if(i>=0)await regenerate(i,chat.messages[i].content)}));
node.append(tools);return body};
// Text is inserted as plain text. Image-only clipboard contents use existing uploads.
const composer=byId('in');
composer.addEventListener('paste',event=>{const clipboard=event.clipboardData;if(!clipboard)return;const text=clipboard.getData('text/plain');if(text){event.preventDefault();composer.setRangeText(text,composer.selectionStart,composer.selectionEnd,'end');composer.dispatchEvent(new Event('input',{bubbles:true}));return}const files=Array.from(clipboard.files||[]).filter(f=>f.type.startsWith('image/'));if(!files.length)return;event.preventDefault();if(busy){notice('Wait for the current reply before pasting an image.');return}const picker=byId('composer-file-input'),add=byId('composer-attach');if(!picker||!add||add.disabled){notice('Please wait for the current upload.');return}const transfer=new DataTransfer();files.forEach(f=>transfer.items.add(f));picker.files=transfer.files;picker.dispatchEvent(new Event('change',{bubbles:true}))});
// Existing messages, if any, also receive controls.
if(cur!==null)open_(cur);
})();

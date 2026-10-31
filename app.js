'use strict';
const $ = id => document.getElementById(id);
const STATIC_DEMO = window.STATIC_DEMO === true;
const SEED = [
  {mac:'02:11:22:33:44:51',name:'iPhone de casa',ip:'192.168.88.24',connection:'Wi-Fi confirmado',online:true,protected:true,blocked:false},
  {mac:'02:11:22:33:44:52',name:'Smart TV',ip:'192.168.88.31',connection:'Wi-Fi confirmado',online:true,protected:false,blocked:false},
  {mac:'02:11:22:33:44:53',name:'Laptop',ip:'192.168.88.42',connection:'DHCP · conexión no confirmada',online:false,protected:false,blocked:false},
  {mac:'02:11:22:33:44:54',name:'Teléfono invitado',ip:'192.168.88.57',connection:'Wi-Fi confirmado',online:true,protected:false,blocked:false},
  {mac:'02:11:22:33:44:55',name:'Consola de juegos',ip:'192.168.88.70',connection:'Wi-Fi confirmado',online:true,protected:false,blocked:false}
];
let devices=[],csrf='',mode='demo',filter='all',selected=null,toastTimer=null;
let sample=SEED.map(d=>({...d}));

async function call(path,options={}){
  const response=await fetch('/api'+path, {credentials:'same-origin',cache:'no-store',...options,
    headers:{'Content-Type':'application/json',...(csrf?{'X-CSRF-Token':csrf}:{}),...(options.headers||{})}});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(data.error||'Error al conectar con la consola.');
  return data;
}
function toast(message,error=false){
  const node=$('toast');node.textContent=message;node.classList.toggle('error',error);node.classList.add('show');
  if(toastTimer)clearTimeout(toastTimer);toastTimer=setTimeout(()=>node.classList.remove('show'),3600);
}
function setView(auth){
  $('loginView').hidden=auth;$('dashboard').hidden=!auth;$('logout').hidden=!auth||STATIC_DEMO;
  $('connection-word').textContent=auth?'RED DOMÉSTICA':'ENTORNO PRIVADO';
}
function chooseIcon(name){
  const t=name.toLowerCase();
  if(/tv|televisor/.test(t))return '▣';
  if(/laptop|pc|computador/.test(t))return '▤';
  if(/consola|xbox|playstation/.test(t))return '◈';
  if(/iphone|teléfono|android|phone/.test(t))return '▯';
  return '⌁';
}
function span(txt,cls){const el=document.createElement('span');el.textContent=txt;if(cls)el.className=cls;return el;}
function showDevice(d){
  const row=document.createElement('article');row.className='device-row';
  const symbol=span(chooseIcon(d.name),'device-symbol');symbol.setAttribute('aria-hidden','true');row.append(symbol);
  const info=document.createElement('div');info.className='device-info';
  const title=document.createElement('div');title.className='device-title';
  const strong=document.createElement('strong');strong.textContent=d.name;title.append(strong);
  if(d.blocked)title.append(span('SIN INTERNET','chip chip-block'));
  else title.append(span(d.online?'WI-FI ACTIVO':'DHCP','chip '+(d.online?'chip-on':'chip-dhcp')));
  if(d.protected)title.append(span('PROTEGIDO','chip chip-safe'));
  info.append(title);
  const meta=document.createElement('div');meta.className='device-meta';
  meta.textContent=(d.ip||'IP no disponible')+' · '+d.mac+' · '+d.connection;info.append(meta);
  row.append(info);
  const action=document.createElement('button');action.className='device-action'+(d.blocked?' allow':'');
  action.textContent=d.protected?'Protegido':(d.blocked?'Restaurar':'Bloquear internet');
  action.disabled=!!d.protected;
  action.addEventListener('click',()=>openModal(d));row.append(action);
  return row;
}
function render(){
  $('countTotal').textContent=devices.length;
  $('countOnline').textContent=devices.filter(d=>d.online).length;
  $('countBlocked').textContent=devices.filter(d=>d.blocked).length;
  $('rowCount').textContent='('+devices.length+')';
  const q=$('search').value.trim().toLowerCase();
  const matching=devices.filter(d=>(filter==='all'||(filter==='online'&&d.online)||(filter==='blocked'&&d.blocked))&&
    [d.name,d.ip,d.mac].some(v=>String(v||'').toLowerCase().includes(q)));
  const list=$('deviceList');list.replaceChildren(...matching.map(showDevice));$('empty').hidden=matching.length>0;
}
async function refresh(){
  $('refresh').disabled=true;
  try{
    const result=STATIC_DEMO?{devices:sample,mode:'demo',simulated:true}:{...await call('/devices')};
    devices=result.devices;mode=result.mode;
    $('modeLabel').textContent=result.simulated?'DEMOSTRACIÓN':'MIKROTIK · REAL';
    $('demoBanner').hidden=!result.simulated;
    $('lastUpdated').textContent='Actualizado: '+new Date().toLocaleTimeString('es',{hour:'2-digit',minute:'2-digit'});
    render();
  }catch(err){toast(err.message,true);$('deviceList').replaceChildren();$('empty').hidden=false;$('empty').textContent='No se pudo cargar la lista. Verifica el router y la configuración.';}
  finally{$('refresh').disabled=false;}
}
function openModal(d){
  if(d.protected)return;
  selected={...d};const blocking=!d.blocked;
  $('modalIcon').textContent=blocking?'⊘':'✓';$('modalIcon').style.color=blocking?'#ff8697':'#63e5c5';
  $('modalTitle').textContent=blocking?'¿Bloquear acceso a internet?':'¿Restaurar el acceso?';
  $('modalDescription').textContent=blocking
    ?`Vas a bloquear internet al dispositivo «${d.name}» (${d.mac}). No se expulsará físicamente de la red Wi-Fi. ¿Quieres continuar?`
    :`Vas a quitar la regla de CasaControl para «${d.name}» (${d.mac}). ¿Quieres continuar?`;
  const word=blocking?'BLOQUEAR':'DESBLOQUEAR';$('confirmText').textContent=word;
  $('confirmation').value='';$('confirmation').placeholder=word;$('confirm').disabled=true;
  $('confirm').textContent=blocking?'Bloquear internet':'Restaurar acceso';
  $('confirm').style.background=blocking?'#ff8897':'#55e1bb';
  $('modal').hidden=false;$('confirmation').focus();
}
function closeModal(){$('modal').hidden=true;selected=null;}
async function confirmAction(){
  if(!selected)return;
  const blocking=!selected.blocked;const word=blocking?'BLOQUEAR':'DESBLOQUEAR';
  if($('confirmation').value.trim().toUpperCase()!==word)return;
  const btn=$('confirm');btn.disabled=true;
  try{
    if(STATIC_DEMO){sample=sample.map(d=>d.mac===selected.mac?{...d,blocked:blocking}:d);}
    else await call(blocking?'/block':'/unblock',{method:'POST',body:JSON.stringify({mac:selected.mac,confirm:word})});
    closeModal();await refresh();toast(STATIC_DEMO?'Acción simulada correctamente.':blocking?'Internet bloqueado.':'Regla retirada. Acceso restaurado.');
  }catch(err){btn.disabled=false;toast(err.message,true);}
}
$('loginForm').addEventListener('submit',async e=>{
  e.preventDefault();const submit=e.currentTarget.querySelector('[type=submit]');submit.disabled=true;
  try{const result=await call('/login',{method:'POST',body:JSON.stringify({password:$('password').value})});
    csrf=result.csrf;mode=result.mode;setView(true);$('password').value='';await refresh();}
  catch(err){toast(err.message,true);}finally{submit.disabled=false;}
});
$('eye').addEventListener('click',()=>{$('password').type=$('password').type==='password'?'text':'password';});
$('logout').addEventListener('click',async()=>{
  try{await call('/logout',{method:'POST',body:'{}'});}catch(_err){}
  csrf='';devices=[];setView(false);toast('Sesión cerrada.');
});
$('refresh').addEventListener('click',refresh);
$('search').addEventListener('input',render);
document.querySelectorAll('[data-filter]').forEach(btn=>btn.addEventListener('click',()=>{
  filter=btn.dataset.filter;document.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('active',b===btn));render();
}));
$('cancel').addEventListener('click',closeModal);
$('modal').addEventListener('click',e=>{if(e.target===$('modal'))closeModal();});
$('confirmation').addEventListener('input',()=>{$('confirm').disabled=!selected||$('confirmation').value.trim().toUpperCase()!==(!selected.blocked?'BLOQUEAR':'DESBLOQUEAR');});
$('confirmation').addEventListener('keydown',e=>{if(e.key==='Enter'&&!$('confirm').disabled)confirmAction();});
$('confirm').addEventListener('click',confirmAction);
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal();});
(async function start(){
  if(STATIC_DEMO){setView(true);$('subheading').textContent='Vista previa en GitHub Pages · datos simulados.';await refresh();return;}
  try{const state=await call('/session');csrf=state.csrf;setView(state.authenticated);if(state.authenticated)await refresh();}
  catch(_err){setView(false);toast('Inicia el servidor local para administrar tu router.',true);}
})();

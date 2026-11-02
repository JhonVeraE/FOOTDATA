'use strict';
// FOOTDATA · cuentas, base de datos (Supabase) y panel de administración.
// Todo el texto que viene de usuarios o de la base de datos entra al DOM como texto (textContent), nunca como HTML.
(function(){
const cfg=window.FOOTDATA_CONFIG||{};
const configured=Boolean(cfg.supabaseUrl&&cfg.supabaseAnonKey&&window.supabase?.createClient);
const sb=configured?window.supabase.createClient(cfg.supabaseUrl,cfg.supabaseAnonKey,{auth:{flowType:'pkce',persistSession:true,autoRefreshToken:true,detectSessionInUrl:true}}):null;
const S={session:null,profile:null,saved:new Map(),ready:false,touched:false};
const ROUTES=new Set(['ingresar','registro','cuenta','admin','nueva-clave']);

function h(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined&&text!==null)n.textContent=String(text);return n;}
function add(p,...c){p.append(...c.filter(Boolean));return p;}
function a(href,text,cls){const n=h('a',cls,text);n.href=href;return n;}
function btn(text,cls,onClick,type='button'){const b=h('button',cls,text);b.type=type;if(onClick)b.addEventListener('click',onClick);return b;}
function field(label,input,hint){const w=h('label','acc-field');add(w,h('span',null,label),input);if(hint)w.append(h('small',null,hint));return w;}
function input(type,name,attrs={}){const i=h('input');i.type=type;i.name=name;for(const [k,v] of Object.entries(attrs))i.setAttribute(k,v);return i;}
function msg(box,text,kind='error'){box.className=`acc-msg ${kind}`;box.textContent=text;box.hidden=!text;}
function main(){return document.querySelector('#main');}
function go(hash){if(location.hash!==hash)location.hash=hash;else window.dispatchEvent(new HashChangeEvent('hashchange'));}
const fmtDate=new Intl.DateTimeFormat('es-PE',{day:'numeric',month:'short',year:'numeric',timeZone:'America/Lima'});
const fmtDateTime=new Intl.DateTimeFormat('es-PE',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'America/Lima'});
function dateText(v){return v?fmtDate.format(new Date(v)):'—';}
function teamName(t){return typeof name==='function'?name(t):t;}
function isAdmin(){return S.profile?.role==='admin';}
function isPremium(){return S.profile?.plan==='premium'&&(!S.profile.plan_expires_at||new Date(S.profile.plan_expires_at)>new Date());}

function errorText(e){
 const m=String(e?.message||e||'');
 if(/Invalid login credentials/i.test(m))return 'Correo o contraseña incorrectos.';
 if(/Email not confirmed/i.test(m))return 'Falta confirmar tu correo. Revisa tu bandeja (y la carpeta de spam).';
 if(/already registered|already been registered/i.test(m))return 'Ese correo ya tiene cuenta. Usa "Ingresar" o recupera tu contraseña.';
 if(/Password should be at least|weak/i.test(m))return 'La contraseña es muy débil: usa al menos 8 caracteres con letras y números.';
 if(/rate limit|too many/i.test(m))return 'Demasiados intentos. Espera unos minutos y vuelve a probar.';
 if(/Failed to fetch|NetworkError/i.test(m))return 'Sin conexión con el servidor. Revisa tu internet.';
 if(/Solo administradores/i.test(m))return 'Esta acción es solo para administradores.';
 if(/No puedes quitarte/i.test(m))return 'No puedes quitarte tu propio rol de administrador.';
 return m||'Ocurrió un error inesperado.';
}

// ─────────────────────────────── Sesión ───────────────────────────────
async function loadProfile(){
 if(!sb||!S.session){S.profile=null;S.saved=new Map();return;}
 const {data,error}=await sb.from('profiles').select('*').eq('id',S.session.user.id).maybeSingle();
 S.profile=error?null:data;
 const picks=await sb.from('saved_picks').select('*').order('kickoff_utc',{ascending:true});
 S.saved=new Map((picks.data||[]).map(p=>[`${p.fixture_id}|${p.pick_id}`,p]));
 if(S.profile&&!S.touched){S.touched=true;sb.from('profiles').update({last_seen_at:new Date().toISOString()}).eq('id',S.session.user.id).then(()=>{});}
}
async function refresh(rerender=true){
 await loadProfile();S.ready=true;renderAccountSlot();document.dispatchEvent(new CustomEvent('footdata:auth'));
 if(rerender){const part=(location.hash.replace(/^#\/?/,'').split(/[/?]/)[0]);if(ROUTES.has(part)||part===''||part==='fijas'||part==='partido')window.dispatchEvent(new HashChangeEvent('hashchange'));}
}
async function init(){
 renderAccountSlot();
 if(!sb){S.ready=true;return;}
 const {data}=await sb.auth.getSession();S.session=data.session;await refresh(false);
 sb.auth.onAuthStateChange((event,session)=>{
  const prev=S.session?.user?.id;S.session=session;
  if(event==='PASSWORD_RECOVERY'){go('#/nueva-clave');return;}
  if(event==='SIGNED_IN'&&prev!==session?.user?.id){setTimeout(async()=>{if(/[?&]code=/.test(location.search)){history.replaceState(null,'',`${location.pathname}#/cuenta`);}await refresh();const part=location.hash.replace(/^#\/?/,'').split(/[/?]/)[0];if(part==='ingresar'||part==='registro')go('#/cuenta');},0);}
  if(event==='SIGNED_OUT'){S.profile=null;S.saved=new Map();S.touched=false;renderAccountSlot();document.dispatchEvent(new CustomEvent('footdata:auth'));}
 });
 loadAnnouncement();
}

// ───────────────────────────── Cabecera ──────────────────────────────
function initials(text){return String(text||'?').trim().split(/[\s@._-]+/).filter(Boolean).map(t=>t[0]).slice(0,2).join('').toUpperCase()||'?';}
function renderAccountSlot(){
 document.querySelectorAll('[data-admin-only]').forEach(n=>{n.hidden=!isAdmin();});
 const slot=document.querySelector('#account-slot');if(!slot)return;slot.replaceChildren();
 if(!S.session){add(slot,a('#/ingresar','Ingresar','acc-login-link'),a('#/registro','Crear cuenta','acc-cta'));return;}
 const who=S.profile?.display_name||S.session.user.email;
 const wrap=h('div','acc-menu');const trigger=btn('', 'acc-avatar');trigger.setAttribute('aria-haspopup','menu');trigger.setAttribute('aria-expanded','false');trigger.setAttribute('aria-label',`Cuenta de ${who}`);
 trigger.append(h('span',null,initials(who)));if(isAdmin())trigger.append(h('i','acc-badge-dot'));
 const menu=h('div','acc-dropdown');menu.hidden=true;menu.setAttribute('role','menu');
 const head=h('div','acc-dropdown-head');add(head,h('strong',null,who),h('small',null,isAdmin()?'Administrador':isPremium()?'Premium':'Plan gratis'));
 add(menu,head,a('#/cuenta','Mi cuenta'),a('#/cuenta?tab=fijas',`Mis fijas guardadas (${S.saved.size})`),isAdmin()?a('#/admin','Panel de administración'):null,isAdmin()?a('#/admin?tab=resultados','Resultados'):null,btn('Cerrar sesión','acc-signout',async()=>{await sb.auth.signOut();go('#/');}));
 const close=()=>{menu.hidden=true;trigger.setAttribute('aria-expanded','false');};
 trigger.addEventListener('click',e=>{e.stopPropagation();menu.hidden=!menu.hidden;trigger.setAttribute('aria-expanded',String(!menu.hidden));});
 menu.addEventListener('click',e=>{if(e.target.closest('a'))close();});
 document.addEventListener('click',e=>{if(!wrap.contains(e.target))close();});
 document.addEventListener('keydown',e=>{if(e.key==='Escape')close();});
 add(wrap,trigger,menu);slot.append(wrap);
}
async function loadAnnouncement(){
 if(!sb)return;
 const {data}=await sb.from('announcements').select('id,body,link_url,created_at').eq('active',true).order('created_at',{ascending:false}).limit(1);
 const n=data?.[0];document.querySelector('.announce-bar')?.remove();if(!n)return;
 try{if(localStorage.getItem('footdata-announce-closed')===String(n.id))return;}catch{}
 const bar=h('div','announce-bar');const text=n.link_url&&n.link_url.startsWith('https://')?a(n.link_url,n.body):h('span',null,n.body);if(text.tagName==='A'){text.target='_blank';text.rel='noopener';}
 const x=btn('×','announce-close',()=>{bar.remove();try{localStorage.setItem('footdata-announce-closed',String(n.id));}catch{}});x.setAttribute('aria-label','Cerrar aviso');
 add(bar,text,x);document.body.prepend(bar);
}

// ─────────────────────────── Páginas comunes ─────────────────────────
function shell(kicker,title,sub){
 const page=h('section','acc-page page-enter');const head=h('header','acc-head');add(head,h('p','eyebrow',kicker),h('h1',null,title),sub?h('p','acc-sub',sub):null);page.append(head);main().replaceChildren(page);return page;
}
function notConfigured(){
 const page=shell('Cuentas FOOTDATA','Muy pronto podrás crear tu cuenta','Estamos activando el acceso con usuario y contraseña. Mientras tanto, todo el análisis y las fijas siguen abiertos para todos.');
 page.append(a('#/fijas','Ver las fijas de hoy','acc-button'));return true;
}

function authPage(mode){
 if(!sb)return notConfigured();
 if(S.session){go('#/cuenta');return true;}
 document.title=`${mode==='registro'?'Crear cuenta':'Ingresar'} · FOOTDATA`;
 const page=h('section','acc-auth page-enter');
 const side=h('aside','acc-auth-side');
 add(side,h('p','eyebrow','FOOTDATA · Temporada 26/27'),h('h1',null,mode==='registro'?'Tu fútbol, con datos.':'Bienvenido de vuelta.'),
  h('p',null,'Con tu cuenta gratuita puedes:'),add(h('ul','acc-benefits'),h('li',null,'Seguir a tus equipos y ver primero sus partidos'),h('li',null,'Guardar fijas y revisar cómo terminaron'),h('li',null,'Recibir las novedades de cada jornada')));
 const card=h('div','acc-card');const tabs=h('div','acc-tabs');tabs.setAttribute('role','tablist');
 for(const [id,label] of [['ingresar','Ingresar'],['registro','Crear cuenta']]){const t=a(`#/${id}`,label,`acc-tab${id===mode?' active':''}`);t.setAttribute('role','tab');t.setAttribute('aria-selected',String(id===mode));tabs.append(t);}
 const form=h('form','acc-form');form.noValidate=true;const box=h('p','acc-msg');box.hidden=true;box.setAttribute('role','alert');
 const nameIn=input('text','name',{autocomplete:'name',maxlength:'60',placeholder:'Cómo quieres que te llamemos'});
 const email=input('email','email',{autocomplete:'email',required:'',placeholder:'tu@correo.com'});
 const pass=input('password','password',{autocomplete:mode==='registro'?'new-password':'current-password',required:'',minlength:'8',placeholder:mode==='registro'?'Mínimo 8 caracteres':'Tu contraseña'});
 const submit=btn(mode==='registro'?'Crear cuenta gratis':'Ingresar','acc-button wide',null,'submit');
 add(form,mode==='registro'?field('Nombre',nameIn):null,field('Correo',email),field('Contraseña',pass),box,submit);
 if(mode==='ingresar'){const forgot=btn('¿Olvidaste tu contraseña?','acc-link',async()=>{
   const v=email.value.trim();if(!/^\S+@\S+\.\S+$/.test(v)){msg(box,'Escribe tu correo arriba y vuelve a pulsar aquí.');email.focus();return;}
   forgot.disabled=true;const {error}=await sb.auth.resetPasswordForEmail(v,{redirectTo:`${location.origin}${location.pathname}`});forgot.disabled=false;
   msg(box,error?errorText(error):'Te enviamos un correo para crear una nueva contraseña.',error?'error':'ok');});form.append(forgot);}
 form.addEventListener('submit',async e=>{
  e.preventDefault();const v=email.value.trim(),p=pass.value;
  if(!/^\S+@\S+\.\S+$/.test(v)){msg(box,'Escribe un correo válido.');email.focus();return;}
  if(p.length<8){msg(box,'La contraseña debe tener al menos 8 caracteres.');pass.focus();return;}
  submit.disabled=true;submit.textContent='Un momento…';msg(box,'');
  let r;
  if(mode==='registro')r=await sb.auth.signUp({email:v,password:p,options:{data:{display_name:nameIn.value.trim().slice(0,60)},emailRedirectTo:`${location.origin}${location.pathname}`}});
  else r=await sb.auth.signInWithPassword({email:v,password:p});
  submit.disabled=false;submit.textContent=mode==='registro'?'Crear cuenta gratis':'Ingresar';
  if(r.error){msg(box,errorText(r.error));return;}
  if(mode==='registro'&&!r.data.session){form.replaceChildren(add(h('div','acc-done'),h('h2',null,'Revisa tu correo'),h('p',null,`Te enviamos un enlace a ${v} para activar tu cuenta. Si no lo ves, mira en spam.`)));}
 });
 add(card,tabs,form,h('p','acc-legal','Al crear una cuenta aceptas que FOOTDATA guarde tu correo y tus preferencias para ofrecerte el servicio. Las probabilidades son estimaciones, no garantías. +18.'));
 add(page,side,card);main().replaceChildren(page);return true;
}

function newPasswordPage(){
 if(!sb)return notConfigured();
 const page=shell('Seguridad','Crea una nueva contraseña');
 if(!S.session){page.append(h('p','acc-sub','El enlace expiró o ya se usó. Pide uno nuevo desde "Ingresar".'),a('#/ingresar','Ir a Ingresar','acc-button'));return true;}
 const form=h('form','acc-form acc-card narrow');const pass=input('password','password',{autocomplete:'new-password',minlength:'8',placeholder:'Mínimo 8 caracteres'});const box=h('p','acc-msg');box.hidden=true;
 add(form,field('Nueva contraseña',pass),box,btn('Guardar contraseña','acc-button',null,'submit'));
 form.addEventListener('submit',async e=>{e.preventDefault();if(pass.value.length<8){msg(box,'Usa al menos 8 caracteres.');return;}const {error}=await sb.auth.updateUser({password:pass.value});msg(box,error?errorText(error):'Listo. Tu contraseña fue actualizada.',error?'error':'ok');if(!error)setTimeout(()=>go('#/cuenta'),1200);});
 page.append(form);return true;
}

// ───────────────────────────── Mi cuenta ─────────────────────────────
function allTeams(){
 const out=new Map();const data=window.state?.teamData||(typeof state!=='undefined'?state.teamData:null);
 for(const [league,c] of Object.entries(data?.competitions||{}))for(const t of c.teams||[])if(!out.has(t.team))out.set(t.team,league);
 return [...out.entries()].map(([team,league])=>({team,league})).sort((x,y)=>teamName(x.team).localeCompare(teamName(y.team),'es'));
}
function accountPage(params){
 if(!sb)return notConfigured();
 if(!S.session){go('#/ingresar');return true;}
 if(!S.ready||!S.profile){const page=shell('Mi cuenta','Cargando tu cuenta…');if(S.ready&&!S.profile)page.append(h('p','acc-sub','No encontramos tu perfil. Si acabas de registrarte, recarga la página en unos segundos.'));return true;}
 document.title='Mi cuenta · FOOTDATA';const P=S.profile;
 const page=shell(isAdmin()?'Administrador':'Mi cuenta',`Hola, ${P.display_name||P.email.split('@')[0]}`,P.email);
 const tabsDef=[['perfil','Perfil'],['equipos','Mis equipos'],['fijas',`Fijas guardadas (${S.saved.size})`],['plan','Plan']];
 const current=tabsDef.some(([k])=>k===params.get('tab'))?params.get('tab'):'perfil';
 const tabs=h('nav','acc-subnav');for(const [k,label] of tabsDef){const t=a(`#/cuenta?tab=${k}`,label,k===current?'active':'');tabs.append(t);}
 if(isAdmin())tabs.append(a('#/admin','Panel admin ↗','acc-admin-link'));
 const body=h('div','acc-body');add(page,tabs,body);
 if(current==='perfil'){
  const form=h('form','acc-card acc-form');const nm=input('text','display_name',{maxlength:'60',value:P.display_name||''});const box=h('p','acc-msg');box.hidden=true;
  add(form,h('h2',null,'Tus datos'),field('Nombre visible',nm),field('Correo',input('email','email',{value:P.email,disabled:''}),'Para cambiar el correo escríbenos.'),box,btn('Guardar cambios','acc-button',null,'submit'));
  form.addEventListener('submit',async e=>{e.preventDefault();const {error}=await sb.from('profiles').update({display_name:nm.value.trim().slice(0,60)||null}).eq('id',P.id);msg(box,error?errorText(error):'Guardado.',error?'error':'ok');if(!error){await loadProfile();renderAccountSlot();}});
  const sec=h('form','acc-card acc-form');const np=input('password','new',{autocomplete:'new-password',minlength:'8',placeholder:'Mínimo 8 caracteres'});const box2=h('p','acc-msg');box2.hidden=true;
  add(sec,h('h2',null,'Contraseña'),field('Nueva contraseña',np),box2,btn('Cambiar contraseña','acc-button ghost',null,'submit'));
  sec.addEventListener('submit',async e=>{e.preventDefault();if(np.value.length<8){msg(box2,'Usa al menos 8 caracteres.');return;}const {error}=await sb.auth.updateUser({password:np.value});msg(box2,error?errorText(error):'Contraseña actualizada.',error?'error':'ok');if(!error)np.value='';});
  const meta=add(h('div','acc-card acc-meta'),h('h2',null,'Tu cuenta'),add(h('dl'),h('dt',null,'Miembro desde'),h('dd',null,dateText(P.created_at)),h('dt',null,'Rol'),h('dd',null,isAdmin()?'Administrador':'Usuario'),h('dt',null,'Plan'),h('dd',null,isPremium()?'Premium':'Gratis')),btn('Cerrar sesión','acc-button ghost',async()=>{await sb.auth.signOut();go('#/');}));
  add(body,add(h('div','acc-grid'),form,sec,meta));
 }else if(current==='equipos'){
  const card=h('div','acc-card');const chosen=new Set(P.favorite_teams||[]);const box=h('p','acc-msg');box.hidden=true;
  const search=input('search','q',{placeholder:'Buscar equipo…','aria-label':'Buscar equipo'});const list=h('div','acc-team-list');const picked=h('div','acc-chips');
  const teams=allTeams();
  const save=async()=>{const arr=[...chosen].slice(0,30);const {error}=await sb.from('profiles').update({favorite_teams:arr}).eq('id',P.id);if(error)msg(box,errorText(error));else{P.favorite_teams=arr;msg(box,'Tus equipos se guardaron. Sus partidos aparecerán primero en el inicio.','ok');}};
  const draw=()=>{
   picked.replaceChildren(...(chosen.size?[...chosen].map(t=>{const c=btn(`${teamName(t)} ×`,'acc-chip on',()=>{chosen.delete(t);draw();save();});c.setAttribute('aria-label',`Quitar ${teamName(t)}`);return c;}):[h('span','acc-muted','Aún no sigues ningún equipo.')]));
   const q=(search.value||'').normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase();
   list.replaceChildren(...teams.filter(t=>!q||teamName(t.team).normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase().includes(q)).slice(0,60).map(t=>{
    const on=chosen.has(t.team);const b=btn('', `acc-team${on?' on':''}`,()=>{if(on)chosen.delete(t.team);else{if(chosen.size>=30){msg(box,'Puedes seguir hasta 30 equipos.');return;}chosen.add(t.team);}draw();save();});
    if(typeof crest==='function')b.append(crest(t.team,'acc-crest'));add(b,h('span',null,teamName(t.team)),h('small',null,t.league));b.setAttribute('aria-pressed',String(on));return b;}));
  };
  search.addEventListener('input',draw);
  add(card,h('h2',null,'Equipos que sigues'),h('p','acc-muted','Toca un equipo para seguirlo o dejar de seguirlo. Se guarda al instante.'),picked,box,field('Buscar',search),list);body.append(card);draw();
 }else if(current==='fijas'){
  const card=h('div','acc-card');card.append(h('h2',null,'Fijas guardadas'));
  const items=[...S.saved.values()].sort((x,y)=>new Date(y.kickoff_utc||0)-new Date(x.kickoff_utc||0));
  if(!items.length)add(card,h('p','acc-muted','Todavía no guardas ninguna fija. En cada selección verás el botón "☆ Guardar".'),a('#/fijas','Ver fijas de hoy','acc-button'));
  const list=h('ul','acc-saved');
  for(const p of items){const li=h('li');const when=p.kickoff_utc?fmtDateTime.format(new Date(p.kickoff_utc))+' Lima':'';const past=p.kickoff_utc&&new Date(p.kickoff_utc)<new Date();
   const info=add(h('div'),h('strong',null,p.label),h('span',null,[p.match_label,when].filter(Boolean).join(' · ')),past?h('small','acc-tag','Jugado · mira el resultado en la revisión diaria'):null);
   const links=h('div','acc-row');links.append(a(`#/partido/${encodeURIComponent(p.fixture_id)}`,'Ver partido','acc-link'));
   links.append(btn('Quitar','acc-link danger',async()=>{const {error}=await sb.from('saved_picks').delete().match({fixture_id:p.fixture_id,pick_id:p.pick_id});if(!error){S.saved.delete(`${p.fixture_id}|${p.pick_id}`);li.remove();renderAccountSlot();}}));
   add(li,info,links);list.append(li);}
  if(items.length)card.append(list);body.append(card);
 }else{
  const card=h('div','acc-card acc-plan');
  add(card,h('h2',null,isPremium()?'Tienes FOOTDATA Premium':'Plan gratis'),
   h('p','acc-muted',isPremium()?(P.plan_expires_at?`Activo hasta el ${dateText(P.plan_expires_at)}.`:'Activo sin fecha de vencimiento.'):'Incluye todos los pronósticos, fijas de cada jornada, equipos favoritos y fijas guardadas.'),
   add(h('div','acc-premium-teaser'),h('strong',null,'Premium · próximamente'),h('p',null,'Estamos preparando un plan con alertas antes de cada partido, historial completo de aciertos y análisis exclusivos.')));
  body.append(card);
 }
 return true;
}

// ───────────────────────────── Panel admin ───────────────────────────
async function adminPage(){
 if(!sb)return notConfigured();
 if(!S.session){go('#/ingresar');return true;}
 if(!S.ready||!S.profile){shell('Administración','Cargando…');return true;}
 if(!isAdmin()){const page=shell('Administración','Acceso restringido','Esta sección es solo para administradores.');page.append(a('#/','Volver al inicio','acc-button'));return true;}
 document.title='Panel admin · FOOTDATA';
 const params=new URLSearchParams(location.hash.split('?')[1]||'');const tab=['resultados','datos'].includes(params.get('tab'))?params.get('tab'):'usuarios';
 const page=shell('Panel de administración','FOOTDATA · Control',{usuarios:'Usuarios, planes y avisos de la web.',resultados:'Cómo terminaron las fijas y los partidos. Solo visible para administradores.',datos:'Base de datos de partidos con estadísticas.'}[tab]);
 const nav=h('nav','acc-subnav');for(const [k,l] of [['usuarios','Usuarios y avisos'],['resultados','Resultados'],['datos','Estadísticas']])nav.append(a(`#/admin?tab=${k}`,l,k===tab?'active':''));page.append(nav);
 if(tab==='resultados'){await resultsTab(page);return true;}
 if(tab==='datos'){await dataTab(page);return true;}
 const stats=h('div','acc-stats');const users=h('div','acc-card');const ann=h('div','acc-card');add(page,stats,add(h('div','acc-admin-grid'),users,ann));
 // Estadísticas
 sb.rpc('admin_stats').then(({data,error})=>{
  if(error){stats.append(h('p','acc-msg error',errorText(error)));return;}
  for(const [k,label] of [['users','Usuarios'],['new_7d','Nuevos (7 días)'],['active_7d','Activos (7 días)'],['premium','Premium'],['saved_picks','Fijas guardadas'],['admins','Administradores']])stats.append(add(h('div','acc-stat'),h('strong',null,String(data?.[k]??0)),h('span',null,label)));
 });
 // Usuarios
 const search=input('search','q',{placeholder:'Buscar por correo o nombre…'});const table=h('div','acc-users');const ubox=h('p','acc-msg');ubox.hidden=true;
 add(users,add(h('div','acc-card-head'),h('h2',null,'Usuarios'),search),ubox,table);
 let rows=[];
 const draw=()=>{
  const q=search.value.trim().toLowerCase();const list=rows.filter(r=>!q||r.email.includes(q)||(r.display_name||'').toLowerCase().includes(q));
  if(!list.length){table.replaceChildren(h('p','acc-muted',rows.length?'Sin coincidencias.':'Aún no hay usuarios.'));return;}
  table.replaceChildren(...list.map(r=>{
   const row=h('div','acc-user');const role=h('select');for(const [v,l] of [['user','Usuario'],['admin','Admin']]){const o=h('option',null,l);o.value=v;o.selected=r.role===v;role.append(o);}
   const plan=h('select');for(const [v,l] of [['free','Gratis'],['premium','Premium']]){const o=h('option',null,l);o.value=v;o.selected=r.plan===v;plan.append(o);}
   const until=input('date','until',{value:r.plan_expires_at?r.plan_expires_at.slice(0,10):''});until.disabled=r.plan!=='premium';plan.addEventListener('change',()=>{until.disabled=plan.value!=='premium';});
   role.setAttribute('aria-label',`Rol de ${r.email}`);plan.setAttribute('aria-label',`Plan de ${r.email}`);until.setAttribute('aria-label',`Premium hasta (${r.email})`);
   const save=btn('Guardar','acc-button small',async()=>{save.disabled=true;const {error}=await sb.rpc('admin_set_user',{target:r.id,new_role:role.value,new_plan:plan.value,new_expires:plan.value==='premium'&&until.value?new Date(`${until.value}T23:59:59-05:00`).toISOString():null});save.disabled=false;
    if(error){msg(ubox,errorText(error));return;}Object.assign(r,{role:role.value,plan:plan.value,plan_expires_at:plan.value==='premium'&&until.value?until.value:null});msg(ubox,`Actualizado: ${r.email}`,'ok');});
   add(row,add(h('div','acc-user-id'),h('strong',null,r.display_name||r.email.split('@')[0]),h('span',null,r.email),h('small',null,`Alta ${dateText(r.created_at)} · Última visita ${r.last_seen_at?dateText(r.last_seen_at):'—'}${r.favorite_teams?.length?` · ${r.favorite_teams.length} equipos`:''}`)),
    add(h('div','acc-user-controls'),role,plan,until,save));return row;}));
 };
 search.addEventListener('input',draw);
 const {data,error}=await sb.from('profiles').select('*').order('created_at',{ascending:false}).limit(500);
 if(error)msg(ubox,errorText(error));else{rows=data;draw();}
 // Avisos
 const form=h('form','acc-form');const body=h('textarea');body.maxLength=280;body.rows=3;body.placeholder='Ej.: Nuevas fijas cada jueves. ¡Síguenos en TikTok!';const url=input('url','link',{placeholder:'https://… (opcional)'});const abox=h('p','acc-msg');abox.hidden=true;const list=h('ul','acc-ann');
 add(form,field('Texto del aviso (máx. 280)',body),field('Enlace',url),abox,btn('Publicar aviso','acc-button',null,'submit'));
 const loadAnn=async()=>{const {data}=await sb.from('announcements').select('*').order('created_at',{ascending:false}).limit(20);
  list.replaceChildren(...(data||[]).map(n=>{const li=h('li',n.active?'on':'');add(li,add(h('div'),h('p',null,n.body),h('small',null,`${fmtDateTime.format(new Date(n.created_at))}${n.link_url?' · con enlace':''} · ${n.active?'Visible':'Oculto'}`)),
   add(h('div','acc-row'),btn(n.active?'Ocultar':'Mostrar','acc-link',async()=>{await sb.from('announcements').update({active:!n.active}).eq('id',n.id);loadAnn();loadAnnouncement();}),
    btn('Eliminar','acc-link danger',async()=>{if(!li.classList.contains('confirm')){li.classList.add('confirm');abox.hidden=false;msg(abox,'Pulsa "Eliminar" otra vez para confirmar.','ok');return;}await sb.from('announcements').delete().eq('id',n.id);loadAnn();loadAnnouncement();})));return li;}));
  if(!data?.length)list.append(h('li','acc-muted','No hay avisos.'));};
 form.addEventListener('submit',async e=>{e.preventDefault();const text=body.value.trim();const link=url.value.trim();if(!text){msg(abox,'Escribe el aviso.');return;}if(link&&!/^https:\/\//.test(link)){msg(abox,'El enlace debe empezar por https://');return;}
  const {error}=await sb.from('announcements').insert({body:text,link_url:link||null});if(error){msg(abox,errorText(error));return;}body.value='';url.value='';msg(abox,'Aviso publicado en la web.','ok');loadAnn();loadAnnouncement();});
 add(ann,h('h2',null,'Aviso en la web'),h('p','acc-muted','Se muestra arriba de todas las páginas. El más reciente visible es el que se ve.'),form,list);loadAnn();
 return true;
}


// ───────────────────────── Resultados (solo admin) ───────────────────
const TIERS=['Conservadora','Normal','Arriesgada'];
const STAT_LABELS=[['shots','Remates'],['sot','Al arco'],['corners','Córners'],['fouls','Faltas'],['cards','Tarjetas']];
const METRIC_ES={goals:'goles',shots:'remates',sot:'tiros al arco',corners:'córners',fouls:'faltas',cards:'tarjetas'};
function pctText(w,n){return n?`${Math.round(w/n*100)}%`:'—';}
function tierCard(name,won,settled,sub){const c=h('div','res-tier '+name.toLowerCase());add(c,h('span',null,name),h('strong',null,settled?`${won}/${settled}`:'—'),h('small',null,sub||pctText(won,settled)+' acierto'));return c;}
async function resultsTab(page){
 const box=h('div','res-wrap');page.append(box);box.append(h('p','acc-muted','Cargando resultados…'));
 const [all,days]=await Promise.all([sb.from('pick_results').select('date,tier,status').limit(5000),sb.from('daily_reviews').select('date,summary').order('date',{ascending:false}).limit(60)]);
 if(all.error||days.error){box.replaceChildren(h('p','acc-msg error',errorText(all.error||days.error)));return;}
 box.replaceChildren();
 if(!days.data.length){box.append(h('div','acc-card',null),h('p','acc-muted','Aún no hay resultados sincronizados. Se cargan solos con la actualización diaria.'));return;}
 const totals=h('section','res-totals');totals.append(h('h2',null,'Acumulado'));const grid=h('div','res-tier-grid');
 for(const t of TIERS){const rows=all.data.filter(r=>r.tier===t&&(r.status==='won'||r.status==='lost'));grid.append(tierCard(t,rows.filter(r=>r.status==='won').length,rows.length));}
 const last7=days.data.slice(0,7).map(d=>d.date);const r7=all.data.filter(r=>last7.includes(r.date)&&(r.status==='won'||r.status==='lost'));
 grid.append(tierCard('Últimos 7 días',r7.filter(r=>r.status==='won').length,r7.length,'todas las fijas'));totals.append(grid);box.append(totals);
 const chips=h('div','res-dates');const detail=h('div','res-detail');add(box,add(h('section','res-day'),h('h2',null,'Por jornada'),chips,detail));
 const show=async date=>{
  chips.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.date===date));detail.replaceChildren(h('p','acc-muted','Cargando…'));
  const picks=await sb.from('pick_results').select('*').eq('date',date);const ids=[...new Set((picks.data||[]).map(p=>p.fixture_id))];
  const games=ids.length?await sb.from('match_results').select('*').in('fixture_id',ids):{data:[]};
  if(picks.error){detail.replaceChildren(h('p','acc-msg error',errorText(picks.error)));return;}
  const day=days.data.find(d=>d.date===date);const sum=h('div','res-tier-grid');
  for(const t of TIERS){const rows=picks.data.filter(r=>r.tier===t&&(r.status==='won'||r.status==='lost'));sum.append(tierCard(t,rows.filter(r=>r.status==='won').length,rows.length));}
  detail.replaceChildren(sum);
  const byFixture=new Map();for(const p of picks.data){if(!byFixture.has(p.fixture_id))byFixture.set(p.fixture_id,[]);byFixture.get(p.fixture_id).push(p);}
  const gameBy=new Map((games.data||[]).map(g=>[g.fixture_id,g]));const list=h('div','res-matches');
  for(const [fid,ps] of byFixture){
   const g=gameBy.get(fid);const card=h('article','res-match');const label=ps[0].match_label||(g?`${g.home} – ${g.away}`:fid);
   const head=h('div','res-match-head');add(head,h('strong',null,label),h('span','res-score',g&&g.home_score!=null?`${g.home_score} – ${g.away_score}`:'sin dato'));card.append(head);
   if(g?.forecast){const f=g.forecast;card.append(h('p','res-forecast',`Modelo: ${f.predicted_score||'—'} · 1X2 ${f.hit_1x2?'acertado':'fallado'} · ambos marcan ${f.hit_btts?'acertado':'fallado'}`));}
   const pl=h('ul','res-picks');ps.sort((x,y)=>TIERS.indexOf(x.tier)-TIERS.indexOf(y.tier));
   for(const p of ps){const li=h('li',p.status);add(li,h('i',null,p.status==='won'?'✓':p.status==='lost'?'✗':'·'),h('span','res-tierlabel',p.tier),h('span',null,p.label),h('small',null,p.metric&&p.actual_home!=null?`${METRIC_ES[p.metric]||p.metric}: ${p.actual_home}–${p.actual_away}`:p.status==='unverified'?'sin verificar':''));pl.append(li);}
   card.append(pl);
   if(g?.stats){const t=h('table','res-stats');const tb=h('tbody');for(const [k,l] of STAT_LABELS){const v=g.stats[k];if(!v||v[0]==null)continue;const tr=h('tr');add(tr,h('td',null,v[0]),h('th',null,l),h('td',null,v[1]));tb.append(tr);}if(tb.childElementCount){t.append(tb);card.append(t);}}
   list.append(card);
  }
  detail.append(list);
  if(day?.summary?.analysis?.length){const an=h('details','res-analysis');an.append(h('summary',null,'Análisis automático de la jornada'));const ul=h('ul');for(const x of day.summary.analysis)ul.append(h('li',null,x));an.append(ul);detail.append(an);}
 };
 for(const d of days.data){const b=btn(dateText(d.date+'T12:00:00Z'),'filter-chip',()=>show(d.date));b.dataset.date=d.date;chips.append(b);}
 show(days.data[0].date);
}
async function dataTab(page){
 const card=h('div','acc-card');const q=input('search','q',{placeholder:'Equipo (ej. Barcelona, Arsenal)…'});const out=h('div','res-matches');const info=h('p','acc-muted');
 add(card,add(h('div','acc-card-head'),h('h2',null,'Partidos con estadísticas'),q),info,out);page.append(card);
 const count=await sb.from('match_results').select('match_id',{count:'exact',head:true});info.textContent=count.error?errorText(count.error):`${count.count||0} partidos en la base de datos. Busca un equipo para ver sus últimos 20.`;
 let timer;const run=async()=>{const v=q.value.trim();if(v.length<3){out.replaceChildren();return;}
  const like=`%${v.replace(/[%_,()]/g,'')}%`;const {data,error}=await sb.from('match_results').select('*').or(`home.ilike.${like},away.ilike.${like}`).order('date',{ascending:false}).limit(20);
  if(error){out.replaceChildren(h('p','acc-msg error',errorText(error)));return;}
  out.replaceChildren(...data.map(g=>{const c=h('article','res-match');add(c,add(h('div','res-match-head'),h('strong',null,`${g.home} – ${g.away}`),h('span','res-score',`${g.home_score??'–'} – ${g.away_score??'–'}`)),h('p','res-forecast',`${dateText(g.date+'T12:00:00Z')} · ${g.league}`));
   const t=h('table','res-stats');const tb=h('tbody');for(const [k,l] of STAT_LABELS){const v=g.stats?.[k];if(!v||v[0]==null)continue;const tr=h('tr');add(tr,h('td',null,v[0]),h('th',null,l),h('td',null,v[1]));tb.append(tr);}if(tb.childElementCount){t.append(tb);c.append(t);}return c;}));
  if(!data.length)out.append(h('p','acc-muted','Sin partidos para esa búsqueda.'));};
 q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(run,300);});
}

// ───────────────────────── Guardar fijas (botón) ─────────────────────
function saveButton(c){
 if(!c?.fixture_id||!c.id)return null;
 const key=`${c.fixture_id}|${c.id}`;const b=btn('','acc-save');
 const paint=()=>{const on=S.saved.has(key);b.textContent=on?'★ Guardada':'☆ Guardar';b.classList.toggle('on',on);b.setAttribute('aria-pressed',String(on));};
 b.addEventListener('click',async()=>{
  if(!sb){go('#/registro');return;}
  if(!S.session){try{sessionStorage.setItem('footdata-after-login',location.hash);}catch{}go('#/ingresar');return;}
  b.disabled=true;
  if(S.saved.has(key)){const {error}=await sb.from('saved_picks').delete().match({fixture_id:String(c.fixture_id),pick_id:c.id});if(!error)S.saved.delete(key);}
  else{const m=(typeof state!=='undefined'?state.payload?.matches:[])?.find(x=>String(x.fixture_id)===String(c.fixture_id));
   const row={fixture_id:String(c.fixture_id),pick_id:c.id,label:(typeof pickLabel==='function'?pickLabel(c):c.label).slice(0,200),match_label:m?`${teamName(m.local)} vs ${teamName(m.visitante)}`:null,kickoff_utc:m?.kickoff_utc||null};
   const {data,error}=await sb.from('saved_picks').insert(row).select().single();if(!error)S.saved.set(key,data);}
  b.disabled=false;paint();renderAccountSlot();
 });
 paint();return b;
}
function wrapPickView(){
 if(typeof window.pickView!=='function'||window.pickView.__fd)return;
 const orig=window.pickView;
 const wrapped=function(c,level,compact){const card=orig.apply(this,arguments);if(c){const b=saveButton(c);if(b)card.append(b);}return card;};
 wrapped.__fd=true;window.pickView=wrapped;
}

// ─────────────────────────────── Router ──────────────────────────────
function route(parts){
 const key=parts[0];if(!ROUTES.has(key))return false;
 const params=new URLSearchParams(location.hash.split('?')[1]||'');
 if(key==='ingresar'||key==='registro')return authPage(key);
 if(key==='nueva-clave')return newPasswordPage();
 if(key==='cuenta')return accountPage(params);
 if(key==='admin'){adminPage();return true;}
 return false;
}
document.addEventListener('footdata:auth',()=>{if(S.session){let back='';try{back=sessionStorage.getItem('footdata-after-login')||'';sessionStorage.removeItem('footdata-after-login');}catch{}if(back&&/^#\/(partido|fijas)/.test(back))go(back);}});

window.FDAuth={route,init,configured,isAdmin,isPremium,favorites:()=>S.profile?.favorite_teams||[],session:()=>S.session,profile:()=>S.profile};
document.addEventListener('DOMContentLoaded',()=>{wrapPickView();init();});
})();

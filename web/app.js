'use strict';
// Public, versioned predictions. Provider/user strings enter the DOM as text only.
const LEAGUES=[
 {slug:'la-liga',name:'La Liga',country:'España',accent:'#df5a47'},
 {slug:'premier-league',name:'Premier League',country:'Inglaterra',accent:'#673b88'},
 {slug:'bundesliga',name:'Bundesliga',country:'Alemania',accent:'#c74139'},
 {slug:'serie-a',name:'Serie A',country:'Italia',accent:'#3e75a2'},
 {slug:'ligue-1',name:'Ligue 1',country:'Francia',accent:'#718154'},
 {slug:'champions-league',name:'UEFA Champions League',display:'Champions League',country:'Europa',accent:'#33557c',featured:true}
];
const WINDOWS=[['temporada','Temporada'],['ultimos_10','Últimos 10'],['ultimos_5','Últimos 5'],['ultimos_3','Últimos 3']];
const METRICS=[['goals','Goles'],['shots','Remates'],['sot','Tiros al arco'],['corners','Córners'],['cards','Tarjetas'],['fouls','Faltas']];
const SHORT_NAMES={'Paris SG':'Paris Saint-Germain','Ath Madrid':'Atlético Madrid',"Nott'm Forest":'Nottingham Forest','Man City':'Manchester City','Man United':'Manchester United',"M'gladbach":'Mönchengladbach','Betis':'Real Betis','Espanol':'Espanyol','FC Koln':'FC Köln','Santander':'Racing Santander','Bodo/Glimt':'Bodø/Glimt','Vallecano':'Rayo Vallecano','Sociedad':'Real Sociedad','La Coruna':'Deportivo','Malaga':'Málaga','Alaves':'Alavés'};
const state={payload:null,teamData:null,fijas:null,fijasDate:'',parlaySize:3,assets:{teams:{},competitions:{}},leagueFilter:'all',search:'',window:'temporada',goalLine:'2.5',lastRoute:''};
const main=document.querySelector('#main');
function E(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined&&text!==null)n.textContent=String(text);return n;}
function append(parent,...children){parent.append(...children.filter(Boolean));return parent;}
function link(href,text,cls){const a=E('a',cls,text);a.href=href;return a;}
function pct(x,precision=1){return x!==null&&x!==undefined&&Number.isFinite(Number(x))?`${Number(x).toFixed(precision)}%`:'Sin datos';}
function num(x,precision=2){return x===null||x===undefined||!Number.isFinite(Number(x))?'—':Number(x).toFixed(precision);}
function name(team){return SHORT_NAMES[team]||team;}
function norm(text){return String(text).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();}
const dateFmt=new Intl.DateTimeFormat('es-PE',{day:'numeric',month:'short',timeZone:'America/Lima'});
const weekdayFmt=new Intl.DateTimeFormat('es-PE',{weekday:'long',day:'numeric',month:'long',timeZone:'America/Lima'});
const timeFmt=new Intl.DateTimeFormat('es-PE',{hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'America/Lima'});
const dayKey=date=>new Intl.DateTimeFormat('en-CA',{year:'numeric',month:'2-digit',day:'2-digit',timeZone:'America/Lima'}).format(new Date(date));
function kickoff(m){return new Date(m.kickoff_utc||`${m.fecha}T${m.hora||'00:00'}:00Z`);}
function futureMatches(){return state.payload.matches.filter(m=>Number.isFinite(kickoff(m).getTime())&&kickoff(m)>new Date());}
function leagueFor(name){return LEAGUES.find(l=>l.name===name);}
function leagueHref(l){return `#/liga/${l.slug}`;}
function matchHref(m){return `#/partido/${encodeURIComponent(m.fixture_id)}`;}
function initials(text){return text.split(/[\s/]+/).filter(Boolean).map(t=>t[0]).slice(0,2).join('').toUpperCase();}
function crest(team,cls='crest'){
 const asset=state.assets.teams[team];
 if(!asset?.image){const fallback=E('span',`${cls} crest-placeholder`,initials(name(team)));fallback.setAttribute('aria-label',`Escudo no disponible de ${name(team)}`);return fallback;}
 const img=E('img',cls);img.src=asset.image;img.alt=`Escudo de ${name(team)}`;img.width=64;img.height=64;img.loading='lazy';img.decoding='async';
 img.addEventListener('error',()=>{const fallback=E('span','crest-placeholder',initials(name(team)));fallback.setAttribute('aria-label',`Escudo no disponible de ${name(team)}`);img.replaceWith(fallback);},{once:true});return img;
}
function competitionLogo(l,cls){
 const wrap=E('span',cls);const asset=state.assets.competitions[l.name];
 if(asset?.image){const img=E('img');img.src=asset.image;img.alt=`Emblema de ${l.display||l.name}`;img.width=80;img.height=80;wrap.append(img);}
 else wrap.append(E('span','crest-placeholder',l.name==='UEFA Champions League'?'CL':initials(l.name)));
 return wrap;
}
function eyebrow(text){return E('p','eyebrow',text);}
function breadcrumbs(items){const nav=E('nav','breadcrumbs');nav.setAttribute('aria-label','Ruta de navegación');items.forEach((item,i)=>{if(i)nav.append(E('span','crumb-divider','/'));if(item.href)nav.append(link(item.href,item.label));else{const span=E('span',null,item.label);span.setAttribute('aria-current','page');nav.append(span);}});return nav;}
function empty(title,message,reset){const box=E('div','empty-state');append(box,E('h2',null,title),E('p',null,message));if(reset){const b=E('button','plain-button','Mostrar todos los partidos');b.addEventListener('click',reset);box.append(b);}return box;}
function teamBlock(team,side,hero=false){const node=E('div',`team-block ${side}`);const text=E('div');append(text,E(hero?'h2':'h3','team-name',name(team)),E('p','team-role',side==='home'?'Local':'Visitante'));append(node,crest(team),text);return node;}
function probabilities(m,big=false){
 const grid=E('div',`result-probabilities${big?' big-probs':''}`);
 for(const [key,label,value] of [['home','Gana el local',m.p_home],['draw','Empate',m.p_draw],['away','Gana el visitante',m.p_away]]){
  const cell=E('div',`prob-cell ${key}`);append(cell,E('span',null,label),E('strong',null,pct(value)));grid.append(cell);
 }return grid;
}
function track(m){const node=E('div','prob-track');node.setAttribute('aria-hidden','true');for(const [key,value] of [['home',m.p_home],['draw',m.p_draw],['away',m.p_away]]){const b=E('span',key);b.style.width=`${Math.max(0,Math.min(100,Number(value)||0))}%`;node.append(b);}return node;}
function scoreParts(m){const pair=m.marcador_top1||m.marcadores_top5?.[0]||['—',null];return [String(pair[0]).replace('-',' – '),pair[1]];}
function panel(title,description,number){const box=E('section','panel');const head=E('div','panel-head');const text=append(E('div'),E('h2',null,title),description?E('p',null,description):null);append(head,text,number?E('span','section-num',number):null);box.append(head);return box;}
function sectionIntro(title,description){const row=E('div','section-intro');append(row,append(E('div'),E('h2',null,title),E('p',null,description)));return row;}
function home(){
 document.title='FOOTDATA · Elige tu competición';const page=E('section','home-screen page-enter');
 const heading=E('div','home-heading');const title=E('div');title.append(eyebrow('Tu próxima lectura del partido'));
 const h=E('h1','home-title','FOOT');h.append(E('span',null,'DATA.'));title.append(h);
 append(heading,title,E('p','home-caption','Elige una competición. El análisis empieza aquí.'));page.append(heading);
 const grid=E('div','competitions-grid');
 for(const l of LEAGUES){
  const matches=futureMatches().filter(m=>m.competition===l.name);const a=link(leagueHref(l),null,`competition-card${l.featured?' featured':''}`);a.style.setProperty('--league',l.accent);
  const top=append(E('div','competition-top'),competitionLogo(l,'competition-logo'),E('span','country-label',l.country));
  const nextCount=matches.filter(m=>m.forecast_scope==='next_complete_round').length;const pendingCount=matches.filter(m=>m.forecast_scope==='pending_previous_round').length;
  const caption=nextCount?`${nextCount} próxima jornada${pendingCount?` · ${pendingCount} ${pendingCount===1?'pendiente':'pendientes'}`:''}`:matches.length?`${matches.length} próximos partidos`:'Ver competición';
  append(a,top,E('h2',null,l.display||l.name),E('p',null,caption),E('span','round-arrow','↗'));grid.append(a);
 }page.append(grid);const fijas=link('#/fijas',null,'home-fijas-link');fijas.append(E('strong',null,'Fijas y combinadas del día ↗'),E('small',null,'Tres niveles de riesgo y selecciones por partido'));page.append(fijas);main.replaceChildren(page);
}
function matchCard(m){
 const card=E('article','match-card');
 append(card,append(E('div','match-meta'),E('span',null,`${m.forecast_scope==='pending_previous_round'?'Pendiente · ':''}Jornada ${m.jornada}`),E('time',null,`${dateFmt.format(kickoff(m))} · ${timeFmt.format(kickoff(m))} Lima`)));
 const fixture=append(E('div','fixture-teams'),teamBlock(m.local,'home'),E('span','versus','VS'),teamBlock(m.visitante,'away'));card.append(fixture,probabilities(m));
 const [score,p]=scoreParts(m);const scoreText=append(E('span','score-preview',score),E('small',null,pct(p)));
 append(card,append(E('div','card-score'),E('span',null,'Marcador más probable'),scoreText));
 const cta=link(matchHref(m),null,'card-link');cta.setAttribute('aria-label',`Ver análisis de ${name(m.local)} contra ${name(m.visitante)}`);append(cta,E('span',null,'Ver análisis completo'),E('span',null,'↗'));card.append(cta);return card;
}
function leaguePage(l){
 document.title=`${l.display||l.name} · FOOTDATA`;const page=E('div','league-page page-enter');
 page.append(breadcrumbs([{label:'Inicio',href:'#/'},{label:l.display||l.name}]));
 const all=futureMatches().filter(m=>m.competition===l.name).sort((a,b)=>kickoff(a)-kickoff(b));
 const banner=E('section','league-banner');const desc=E('div');append(desc,eyebrow(`${l.country} · Temporada 2026/27`),E('h1',null,l.display||l.name),E('p',null,'Próxima jornada completa y partidos pendientes. Análisis antes del inicio.'));
 append(banner,competitionLogo(l,'league-logo'),desc,append(E('div','banner-stat'),E('strong',null,String(all.length).padStart(2,'0')),E('span',null,'partidos por analizar')));page.append(banner,teamLeagueNavigation(l,'matches'));
 const toolbar=E('div','listing-toolbar');const dates=E('div','date-filters');dates.setAttribute('aria-label','Filtrar por fecha');
 const today=dayKey(new Date());const available=[...new Set(all.map(m=>dayKey(kickoff(m))))];
 const filters=[['all','Todos'],...available.map(d=>[d,d===today?'Hoy':dateFmt.format(kickoff(all.find(m=>dayKey(kickoff(m))===d)))])];
 if(!filters.some(([id])=>id===state.leagueFilter))state.leagueFilter='all';
 const searchWrap=E('label','search');const search=E('input');search.type='search';search.placeholder='Buscar equipo…';search.value=state.search;search.setAttribute('aria-label','Buscar un equipo en esta competición');append(searchWrap,E('span','search-icon','⌕'),search);
 const info=E('p','list-meta');info.setAttribute('aria-live','polite');const grid=E('div','match-grid');
 const update=()=>{
  const filtered=all.filter(m=>(state.leagueFilter==='all'||dayKey(kickoff(m))===state.leagueFilter)&&(!state.search||norm(`${name(m.local)} ${name(m.visitante)} ${m.local} ${m.visitante}`).includes(norm(state.search))));
  dates.querySelectorAll('button').forEach(b=>{const active=b.dataset.date===state.leagueFilter;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
  info.textContent=`${filtered.length} ${filtered.length===1?'partido disponible':'partidos disponibles'} · Horarios de Lima (UTC−5)`;
  const reset=()=>{state.search='';search.value='';state.leagueFilter='all';update();};
  const grouped=filtered.some(m=>m.forecast_scope==='next_complete_round'||m.forecast_scope==='pending_previous_round');
  grid.className=grouped?'fixture-groups':'match-grid';
  if(grouped){
   const sections=[];for(const [scope,label] of [['next_complete_round','Próxima jornada completa'],['pending_previous_round','Pendientes de jornadas anteriores']]){
    const fixtures=filtered.filter(m=>m.forecast_scope===scope);if(!fixtures.length)continue;
    const section=E('section','fixture-group');const round=[...new Set(fixtures.map(m=>m.jornada))].join(', ');section.append(sectionIntro(`${label}${scope==='next_complete_round'?` · Jornada ${round}`:''}`,`${fixtures.length} partidos${scope==='pending_previous_round'?` · Jornadas ${round}`:''}`));const cards=E('div','match-grid');cards.append(...fixtures.map(matchCard));section.append(cards);sections.push(section);
   }grid.replaceChildren(...sections);
  }else grid.replaceChildren(...(filtered.length?filtered.map(matchCard):[empty(all.length?'No encontramos ese partido':'Próximos encuentros por confirmar',all.length?'Prueba con otro equipo o una fecha diferente.':'No hay predicciones futuras disponibles para esta competición.',all.length?reset:null)]));
 };
 filters.forEach(([id,label])=>{const b=E('button','filter-chip',label);b.type='button';b.dataset.date=id;b.addEventListener('click',()=>{state.leagueFilter=id;update();});dates.append(b);});
 search.addEventListener('input',()=>{state.search=search.value.trim();update();});append(toolbar,dates,searchWrap);page.append(toolbar,info,grid);main.replaceChildren(page);update();
}
function probabilityPanel(m){
 const box=panel('¿Quién tiene más opciones?','Tiempo reglamentario. Porcentajes redondeados a una décima.','01');box.id='probabilidades';box.append(probabilities(m,true),track(m));
 const values=[m.p_home,m.p_draw,m.p_away];const index=values.indexOf(Math.max(...values));const fav=[name(m.local),'el empate',name(m.visitante)][index];
 box.append(E('p','prob-insight',`El escenario más probable es ${fav}, con ${pct(values[index])}.`));
 box.append(E('p','explanation',m.competition==='UEFA Champions League'?'Champions tiene una muestra limitada. Estas probabilidades no tienen una calibración europea propia.':'La calibración se ajustó con partidos históricos de las ligas domésticas. Un 60% describe una estimación, no un resultado seguro.'));return box;
}
function goalsPanel(m){
 const box=panel('La lectura de los goles','Cuánto espera el modelo de cada ataque.','02');
 const totals=E('div','goals-overview');
 for(const [team,value] of [[m.local,m.lam_home],[m.visitante,m.lam_away]]){
  if(totals.childElementCount)totals.append(E('span','expected-plus','+'));
  append(totals,append(E('div','expected-goals'),E('strong',null,num(value)),E('span',null,name(team))));
 }box.append(totals);
 const top=append(E('div','btts-top'),E('span','btts-label','Ambos equipos anotan'),E('strong','btts-number',pct(m.btts)));
 const bar=E('div','btts-bar');const fill=E('span');fill.style.width=`${Math.min(100,Math.max(0,m.btts))}%`;bar.append(fill);
 box.append(top,bar,E('p','explanation','Los goles esperados son una media del modelo, no un marcador exacto. BTTS se calcula con la distribución de goles, sin calibración específica.'));return box;
}
function scoresPanel(m){
 const box=panel('Cinco marcadores posibles','Ordenados de mayor a menor probabilidad.','03');const list=E('div','scores-list');const highest=m.marcadores_top5?.[0]?.[1]||1;
 for(const [score,p] of m.marcadores_top5||[]){const meter=E('div','score-meter');const fill=E('span');fill.style.width=`${Math.max(0,p/highest*100)}%`;meter.append(fill);append(list,append(E('div','score-line'),E('strong',null,String(score).replace('-',' – ')),meter,E('span',null,pct(p))));}
 box.append(list);return box;
}
function goalLinesPanel(m){
 const box=panel('¿Un partido con muchos goles?','Explora la probabilidad de superar cada línea de goles.','04');const picker=E('div','line-picker');const values=E('div','goal-line-split');
 const update=()=>{const market=m.goal_lines[state.goalLine];values.replaceChildren();for(const [key,label] of [['over','Más de'],['under','Menos de']])values.append(append(E('div'),E('span',null,`${label} ${state.goalLine} goles`),E('strong',null,pct(market[key]*100))));picker.querySelectorAll('button').forEach(b=>{const active=b.dataset.line===state.goalLine;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});};
 if(!m.goal_lines[state.goalLine])state.goalLine=Object.keys(m.goal_lines)[0];
 for(const line of Object.keys(m.goal_lines)){const b=E('button',null,line);b.type='button';b.dataset.line=line;b.addEventListener('click',()=>{state.goalLine=line;update();});picker.append(b);}
 box.append(picker,values,E('p','explanation','Ejemplo: más de 2,5 significa 3 goles o más entre ambos equipos. Estas líneas proceden de la distribución de goles; no de cuotas de una casa de apuestas.'));update();return box;
}
function projections(m){
 const section=E('section','detail-section');section.id='estadisticas';section.append(sectionIntro('El partido, estadística por estadística','Proyección por equipo. Verde para el local y violeta para el visitante.'));
 const box=E('div','panel stats-panel');const legend=E('div','legend-row');for(const [team,side] of [[m.local,'home'],[m.visitante,'away']])legend.append(append(E('span',`legend-item ${side}`),E('i'),E('span',null,name(team))));box.append(legend);
 for(const [key,label] of METRICS){const v=m.cruces[key];const row=E('div','stat-row');append(row,append(E('div','stat-head'),E('strong',null,num(v.home)),E('span','stat-label',label),E('strong',null,num(v.away))));
  const track=E('div','comparison-track');const max=Math.max(v.home||0,v.away||0,1);
  for(const value of [v.home,v.away]){const half=E('div');const bar=E('span');bar.style.width=`${value==null?0:Math.max(0,value/max*100)}%`;half.append(bar);track.append(half);}row.append(track,E('p','stat-total',v.home!=null&&v.away!=null?`Total esperado: ${num(v.home+v.away)}${key==='goals'?' · modelo de goles':' · estimación descriptiva'}`:'No hay información suficiente para esta proyección.'));box.append(row);
 }section.append(box,E('div','note-box',m.model.count_refinements?.length?'Medias de córners, tarjetas, remates y faltas contrastadas con partidos históricos de ligas domésticas. Las probabilidades de córners y tarjetas aún no tienen calibración propia. Tarjetas = amarillas + rojas.':'Córners, tarjetas, remates y faltas son estimaciones descriptivas. Córners y tarjetas todavía no tienen validación propia. Tarjetas = amarillas + rojas.'));
 return section;
}
function formTeam(m,side,key){
 const home=side==='home';const team=home?m.local:m.visitante;const window=(home?m.forma_home:m.forma_away)[key];const box=E('div','panel');
 append(box,append(E('div','form-team-heading'),crest(team),append(E('div'),E('h3',null,name(team)),E('p',null,`${home?'Como local':'Como visitante'}${(home?m.contexto_home:m.contexto_away)==='general'?' · historial general disponible':''}`))));
 if(!window){box.append(E('p','explanation','No hay partidos disponibles en esta ventana.'));return box;}
 append(box,append(E('div','form-summary'),E('span',null,`${window.partidos} partidos en esta ventana`),E('strong',null,`${num(window.puntos_por_partido)} pts/partido`)));
 const record=E('div','form-record');for(const [field,label] of [['victorias','Victorias'],['empates','Empates'],['derrotas','Derrotas']])record.append(append(E('div'),E('strong',null,window[field]),E('span',null,label)));box.append(record);
 const table=E('table','form-table');table.setAttribute('aria-label',`Estadísticas de ${name(team)} en la ventana ${key}`);const head=E('tr');for(const txt of ['Media por partido','A favor','En contra'])head.append(E('th',null,txt));const thead=E('thead');thead.append(head);table.append(thead);const body=E('tbody');
 for(const [stat,label] of METRICS){const tr=E('tr');append(tr,E('td',null,label),E('td',null,num(window[`${stat}_for`])),E('td',null,num(window[`${stat}_against`])));body.append(tr);}table.append(body);box.append(table);return box;
}
function formSection(m){
 const section=E('section','detail-section');section.id='forma';const scope=m.quality?.statistics_scope==='combined_competitions_estimate'?'Historial doméstico y europeo combinado, separado en local/visitante.':'Ventanas históricas de esta competición, separadas en local/visitante.';const intro=sectionIntro('La forma de los equipos',scope);const tabs=E('div','window-tabs');tabs.setAttribute('aria-label','Ventana de forma');const grid=E('div','form-grid');
 const update=()=>{grid.replaceChildren(formTeam(m,'home',state.window),formTeam(m,'away',state.window));tabs.querySelectorAll('button').forEach(b=>{const active=b.dataset.window===state.window;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});};
 for(const [key,label] of WINDOWS){const b=E('button','window-tab',label);b.type='button';b.dataset.window=key;b.addEventListener('click',()=>{state.window=key;update();});tabs.append(b);}intro.append(tabs);section.append(intro,grid);update();return section;
}
function trends(m){
 const box=panel('Qué está cambiando','Últimos tres partidos frente a la temporada. La dirección no implica por sí sola una mejora.');const grid=E('div','trends-grid');
 const labels={goals_for:'Goles a favor',goals_against:'Goles recibidos',shots_for:'Remates',corners_for:'Córners',cards_for:'Tarjetas'};
 for(const [team,observations] of [[m.local,m.tendencias_home],[m.visitante,m.tendencias_away]]){
  const col=append(E('div'),E('h3','trend-team-title',name(team)));for(const [key,label] of Object.entries(labels)){const t=observations?.[key];const change=t?.cambio_pct_ultimo;const status=t?.estado==='subiendo'?'↑ Sube':t?.estado==='bajando'?'↓ Baja':t?.estado==='estable'?'Sin tendencia':'Muestra insuficiente';const text=`${status}${typeof change==='number'?` · ${change>0?'+':''}${change.toFixed(0)}%`:''}`;col.append(append(E('div','trend-item'),E('span',null,label),E('span',`trend-value ${t?.estado==='subiendo'?'up':t?.estado==='bajando'?'down':''}`,text)));}grid.append(col);
 }box.append(grid);return box;
}
function h2h(m){
 const box=panel('Cuando se enfrentaron','Historial descriptivo. El marcador se muestra desde la perspectiva del local de este próximo encuentro.');box.id='historial';
 const rows=m.h2h_ida?.detalle||[];
 if(!rows.length){box.append(E('p','explanation','No hay enfrentamientos directos en el historial disponible. El modelo no inventa antecedentes.'));return box;}
 const wrap=E('div','table-wrap');const table=E('table','h2h-table');const head=E('tr');for(const label of ['Fecha',`${name(m.local)} / ${name(m.visitante)}`,'Córners','Tarjetas'])head.append(E('th',null,label));const thead=E('thead');thead.append(head);const body=E('tbody');
 for(const r of [...rows].reverse()){const tr=E('tr');for(const text of [dateFmt.format(new Date(r.fecha+'T12:00:00Z'))+' '+r.fecha.slice(0,4),r.marcador.replace('-',' – '),r.corners,r.tarjetas])tr.append(E('td',null,text));body.append(tr);}table.append(thead,body);wrap.append(table);box.append(wrap,E('p','explanation','Cada partido se cuenta una vez. El H2H no modifica la proyección de goles.'));return box;
}
function methodology(m){
 const details=E('details','methodology');details.id='metodo';details.append(E('summary',null,'Datos, muestra y método'));const content=E('div','method-content');
 const sample=E('div');append(sample,E('h3',null,'Qué información utiliza'),E('p',null,`Datos anteriores al ${m.cutoff}. Último resultado disponible: ${m.latest_observation}.`),E('p',null,`Muestra efectiva: ${num(m.confianza.sample_effective_home,1)} partidos del local y ${num(m.confianza.sample_effective_away,1)} del visitante. Los encuentros recientes tienen más peso.`));
 const list=E('ul');for(const text of m.data_warnings||[])list.append(E('li',null,text));sample.append(list);
 const method=E('div');append(method,E('h3',null,'Una lectura transparente'),E('p',null,'El modelo estima fuerzas de ataque y defensa, ajustadas por rival y competición. Las cifras describen escenarios posibles en 90 minutos.'),E('p',null,`Modelo: ${m.model.version}. Elo orientativo: ${Math.round(m.elo_home)} / ${Math.round(m.elo_away)}. El Elo no alimenta las probabilidades de esta versión.`),E('p',null,`Fuentes: ${m.sources.join(', ')}.`));
 const identification=E('p',null,'Versión de los datos: ');identification.append(E('code',null,m.dataset_id||'No disponible'));method.append(identification);content.append(sample,method);details.append(content);return details;
}
function matchPage(m){
 const l=leagueFor(m.competition);document.title=`${name(m.local)} vs ${name(m.visitante)} · FOOTDATA`;const page=E('article','match-page page-enter');
 page.append(breadcrumbs([{label:'Inicio',href:'#/'},{label:l.display||l.name,href:leagueHref(l)},{label:`${name(m.local)} vs ${name(m.visitante)}`}]))
 page.append(E('h1','visually-hidden',`${name(m.local)} contra ${name(m.visitante)}: análisis del partido`));
 const hero=E('section','match-hero');const smallLogo=competitionLogo(l,'competition-inline');smallLogo.append(E('span',null,`${l.display||l.name} · Jornada ${m.jornada}`));
 append(hero,append(E('div','match-hero-top'),smallLogo,E('span',null,`${weekdayFmt.format(kickoff(m))} · ${timeFmt.format(kickoff(m))} Lima`)));
 const [score,p]=scoreParts(m);const prediction=append(E('div','hero-score'),E('span',null,'MARCADOR MÁS PROBABLE'),E('strong',null,score),E('p',null,`${pct(p)} de probabilidad`));
 const timeNote=kickoff(m)>new Date()?'Predicción previa al partido · tiempo reglamentario':'La fecha de inicio prevista ya pasó. Esta ficha conserva la predicción previa, no un resultado en vivo.';
 hero.append(append(E('div','fixture-teams'),teamBlock(m.local,'home',true),prediction,teamBlock(m.visitante,'away',true)),E('p','score-note',timeNote));page.append(hero);
 const anchors=E('nav','detail-anchor-nav');anchors.setAttribute('aria-label','Secciones del análisis');
 for(const [id,label] of [['fijas','Fijas'],['probabilidades','El pronóstico'],['estadisticas','Estadísticas'],['forma','Estado de forma'],['historial','Enfrentamientos'],['metodo','Datos y método']]){const a=link(`#${id}`,label);a.addEventListener('click',event=>{event.preventDefault();document.getElementById(id)?.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});});anchors.append(a);}page.append(anchors,matchFijas(m));
 page.append(append(E('div','detail-grid'),probabilityPanel(m),goalsPanel(m)));
 const extra=append(E('div','detail-grid detail-section'),scoresPanel(m),goalLinesPanel(m));page.append(extra,projections(m),formSection(m));
 page.append(append(E('div','detail-grid detail-section'),h2h(m),trends(m)),methodology(m));main.replaceChildren(page);
}
function route(){
 if(!state.payload)return;
 const route=location.hash.replace(/^#/,'')||'/';const parts=route.split('?')[0].split('/').filter(Boolean);const changed=state.lastRoute!==route;
 if(changed){state.leagueFilter='all';state.search='';state.window='temporada';state.goalLine='2.5';}
 if(parts.length===0)home();
 else if(parts[0]==='fijas'){if(changed)state.fijasDate='';fijasPage();}
 else if(parts[0]==='liga'&&LEAGUES.some(l=>l.slug===parts[1])){const l=LEAGUES.find(l=>l.slug===parts[1]);if(!handleTeamsRoute(parts,l))leaguePage(l);}
 else if(parts[0]==='partido'){
  let id;try{id=decodeURIComponent(parts[1]||'');}catch{id='';}
  const m=state.payload.matches.find(m=>String(m.fixture_id)===id);
  if(m)matchPage(m);else main.replaceChildren(empty('Partido no disponible','Este encuentro no está en la última actualización. Vuelve a una competición para consultar los próximos partidos.'),link('#/','Volver a las competiciones','plain-button'));
 }else main.replaceChildren(empty('No encontramos esta página','Vuelve al inicio para elegir una competición.'),link('#/','Volver al inicio','plain-button'));
 state.lastRoute=route;if(changed)window.scrollTo({top:0,behavior:'instant'});
}
async function start(){
 try{
  const [response,assetResponse,teamResponse,fijasResponse]=await Promise.all([fetch('data/predictions.json',{cache:'no-store'}),fetch('data/assets.json'),fetch('data/teams.json',{cache:'no-store'}).catch(()=>null),fetch('data/fijas.json',{cache:'no-store'}).catch(()=>null)]);
  if(!response.ok)throw Error('No se han podido cargar las predicciones.');
  state.payload=await response.json();if(!Array.isArray(state.payload.matches))throw Error('El archivo de predicciones no tiene el formato esperado.');
  if(assetResponse.ok)state.assets=await assetResponse.json();if(teamResponse?.ok){try{state.teamData=await teamResponse.json();}catch{state.teamData=null;}}if(fijasResponse?.ok){try{state.fijas=await fijasResponse.json();}catch{state.fijas=null;}}window.addEventListener('hashchange',route);route();
  let futureIds=futureMatches().map(m=>m.fixture_id).join(',');
  window.setInterval(()=>{const ids=futureMatches().map(m=>m.fixture_id).join(',');if(ids!==futureIds){futureIds=ids;route();}},30000);
 }catch(error){main.replaceChildren(empty('No podemos cargar los partidos',error.message),E('p','explanation','Abre esta web desde su servidor local, no como un archivo HTML suelto.'));}
}
document.querySelector('.skip-link').addEventListener('click',event=>{event.preventDefault();main.focus({preventScroll:true});main.scrollIntoView({block:'start'});});
start();

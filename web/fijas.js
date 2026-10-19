'use strict';
// Text-only rendering. All selections retain the source prediction and cutoff.
function fijasReady(){return state.fijas?.dataset_id===state.payload?.run.dataset_id&&state.fijas?.prediction_run_generated_at===state.payload?.run.generated_at;}
function fijasMatch(m){return fijasReady()?state.fijas.matches.find(x=>String(x.fixture_id)===String(m.fixture_id)&&x.prediction_generated_at===m.generated_at):null;}
function pickLabel(c){for(const team of Object.keys(SHORT_NAMES).sort((a,b)=>b.length-a.length))if(c.label.startsWith(team+' '))return name(team)+c.label.slice(team.length);return c.label;}
function selectionMeaning(c){
 if(c.kind==='result')return c.side==='draw'?'Empate al finalizar los 90 minutos y el añadido.':'Victoria del equipo indicado en tiempo reglamentario.';
 if(c.kind==='result_goals')return 'Deben cumplirse el resultado y la línea de goles. La probabilidad se calcula conjuntamente.';
 if(c.kind==='handicap')return c.line<0?`Necesita ganar por ${Math.floor(-c.line)+1} goles o más.`:`Cobra si gana, empata o pierde por hasta ${Math.floor(c.line)} ${Math.floor(c.line)===1?'gol':'goles'}.`;
 if(['goals','cards','corners','shots','sot','fouls'].includes(c.kind)){const scope=c.scope&&c.scope!=='total'?'del equipo indicado':'entre ambos equipos';return c.side==='over'?`${Math.floor(c.line)+1} o más ${scope}.`:`Hasta ${Math.floor(c.line)} ${scope}.`;}
 if(c.kind==='btts')return c.side==='yes'?'Cada equipo debe anotar al menos un gol.':'Al menos uno de los equipos debe terminar sin marcar.';
 return c.side==='12'?'Se cumple con victoria de cualquiera de los equipos.':'Se cumple con victoria de ese equipo o empate.';
}
function recentText(c){return c.evidence.contexts.map(v=>`${name(v.team)} ${v.hits}/${v.matches}${v.measure&&v.measure!=='partido'?` (${v.measure})`:''} ${v.venue==='general'?'en historial general':`como ${v.venue}`}${v.scope?.startsWith('combined_')?' [varias competiciones]':''}${v.current_hit_streak!==undefined?` · racha actual: ${v.current_hit_streak}`:''}`).join(' · ');}
function oddsComparison(c,quote){if(!Number.isFinite(quote)||quote<=1)return null;return {above:quote>=c.minimum_odds,theoreticalBreakEven:quote>=c.fair_odds};}
function auditedPrice(c){const a=c.odds_audit;if(!a)return null;return a.status==='above_reference'?`Cuota consultada ${num(a.odds)} · Supera el umbral orientativo.`:a.status==='below_reference'?`Cuota consultada ${num(a.odds)} · No pasa el filtro de precio del modelo.`:a.status==='fixture_mismatch'?'Cuota sin validar: el horario o el encuentro no coincide.':'No se encontró una cuota exacta en la oferta consultada.';}
function priceBlock(c){
 const box=E('div','pick-price');box.append(E('p',null,`Cuota teórica ${num(c.fair_odds)} · Umbral orientativo ${num(c.minimum_odds)}`));
 const auditText=auditedPrice(c);if(auditText)box.append(E('p',`audited-price ${c.odds_audit.status}`,auditText));
 const label=E('label','quote-label');label.append(E('span',null,'Comparar otra cuota Betano'));const input=E('input','quote-input');input.type='text';input.inputMode='decimal';input.placeholder='Ej. 1.95';input.setAttribute('aria-label',`Cuota Betano para ${c.label}`);input.autocomplete='off';
 const key=`footdata-price:${state.fijas.prediction_run_generated_at}:${c.fixture_id}:${c.id}`;try{input.value=localStorage.getItem(key)||'';}catch{}
 const observed=c.observed_quote;const fresh=observed&&Date.now()-Date.parse(observed.observed_at)>=0&&Date.now()-Date.parse(observed.observed_at)<=15*60000;
 if(!input.value&&fresh)input.value=String(observed.odds);
 const status=E('small','quote-status');status.setAttribute('aria-live','polite');
 const update=()=>{const value=Number(input.value.trim().replace(',','.'));const result=oddsComparison(c,value);status.textContent=!input.value?(auditText?'Puedes comparar aquí un precio más reciente.':'Precio y disponibilidad sin verificar.'):!result?'Introduce una cuota decimal mayor que 1.':result.above?'La cuota introducida supera el umbral orientativo.':'La cuota introducida queda por debajo del umbral orientativo.';};
 input.addEventListener('input',()=>{try{if(input.value)localStorage.setItem(key,input.value);else localStorage.removeItem(key);}catch{}update();});label.append(input);box.append(label,status);
 if(observed&&observed.source_url.startsWith('https://www.betano.pe/'))box.append(link(observed.source_url,`Betano: ${num(observed.odds)} · capturada ${dateFmt.format(new Date(observed.observed_at))} ${timeFmt.format(new Date(observed.observed_at))} Lima. No es una cuota en vivo.`,'observed-quote'));
 else if(c.odds_audit?.source_url?.startsWith('https://www.betano.pe/'))box.append(link(c.odds_audit.source_url,`Oferta revisada: ${dateFmt.format(new Date(c.odds_audit.observed_at))} ${timeFmt.format(new Date(c.odds_audit.observed_at))} Lima.`,'observed-quote'));
 update();return box;
}
function pickView(c,level,compact=false){
 const card=E('article',`pick-card ${level?.key||'market'}${compact?' compact':''}`);
 if(level)card.append(E('p','pick-level',level.label));
 if(!c){card.append(E('h3',null,'Sin propuesta con respaldo'),E('p','pick-reason',level?.reason||'Ninguna línea reúne mayoría reciente en ambas muestras, probabilidad de este nivel y precio suficiente cuando hay cuota contrastada.'));return card;}
 if(!compact)card.append(E('span','pick-market',c.market));
 card.append(E('h3','pick-title',pickLabel(c)),E('p','pick-meaning',selectionMeaning(c)),E('p','pick-probability',`Prob. del modelo: ${pct(c.probability*100)}`));
 const ev=E('div','pick-evidence');ev.append(E('span','evidence-label','FORMA RECIENTE'),E('p',null,recentText(c)));
 if(!compact)ev.append(E('p','evidence-caption','Veces que se cumplió esta selección; hasta cinco partidos por equipo en su localía.'));
 card.append(ev);
 card.append(priceBlock(c));
 return card;
}
function matchFijas(m){
 const section=E('section','detail-section fijas-section');section.id='fijas';section.append(sectionIntro('Fijas del partido','Prioridad a ganador, doble oportunidad, hándicap, ambos marcan y goles. Tres alternativas por riesgo.'));
 const r=fijasMatch(m);
 if(!r||kickoff(m)<=new Date()){section.append(E('div','note-box',kickoff(m)<=new Date()?'El partido ya comenzó. Las selecciones previas se conservan en el archivo.':'Las selecciones se actualizarán con la próxima generación del modelo.'));return section;}
 const grid=E('div','picks-grid');grid.append(...r.tiers.map(t=>pickView(t.selection,t)));section.append(grid);
 const markets=E('details','market-details');markets.append(E('summary',null,'Explorar resultados, goles, remates, tiros al arco, faltas, córners y otros mercados'));
 for(const [title,kinds] of [['Resultado y goles',new Set(['result','double_chance','handicap','goals','btts','result_goals'])],['Mercados complementarios',new Set(['shots','sot','fouls','corners','cards'])]]){
  markets.append(E('h3','market-group-title',title));const marketGrid=E('div','market-picks');for(const market of r.markets.filter(m=>kinds.has(m.kind)))marketGrid.append(pickView(market.selection,{key:'market',label:market.market,reason:market.reason},true));markets.append(marketGrid);
 }section.append(markets);
 section.append(E('p','fijas-footnote','“Conservadora” compara riesgo entre estas alternativas; ninguna es segura. Forma reciente y modelo se muestran por separado.'),link(`#/fijas?fecha=${r.date_lima}`,'Ver la combinada de este día ↗','fijas-day-link'));
 if(r.limited_european_sample)section.append(E('p','fijas-footnote','Champions: muestra europea reducida, sin calibración propia.'));
 return section;
}
function liveParlay(pool,size){
 // Re-select from the frozen per-match pool when any kickoff has passed.
 const items=pool.filter(m=>m.parlay_selection&&new Date(m.kickoff_utc)>new Date());let best=null,bestP=-1;
 function visit(start,group,teams,p){if(group.length===size){if(p>bestP){best=group.slice();bestP=p;}return;}
  for(let i=start;i<items.length;i++){const m=items[i];if(teams.has(m.home)||teams.has(m.away))continue;visit(i+1,[...group,m],new Set([...teams,m.home,m.away]),p*m.parlay_selection.probability);}}
 visit(0,[],new Set(),1);return best?{legs:best,probability:bestP}:null;
}
function parlayPanel(pool,size){
 const box=E('section','parlay-panel');const head=E('div','parlay-heading');append(head,append(E('div'),eyebrow('COMBINADA DEL DÍA'),E('h2',null,`${size} partidos, una selección por encuentro`)),E('span','parlay-symbol','↗'));box.append(head);
 const parlay=liveParlay(pool,size);
 if(!parlay){box.append(E('p','parlay-empty',`Este día no reúne ${size} partidos distintos con selecciones admisibles. Puedes consultar las propuestas individuales.`));return box;}
 const list=E('ol','parlay-legs');parlay.legs.forEach((m,i)=>{const r=state.payload.matches.find(r=>String(r.fixture_id)===m.fixture_id);const row=E('li');const c=m.parlay_selection;row.append(E('span','leg-index',String(i+1).padStart(2,'0')),append(E('div','leg-body'),link(matchHref(r),`${name(m.home)} — ${name(m.away)}`,'leg-fixture'),E('strong',null,pickLabel(c)),E('small',null,`${timeFmt.format(new Date(m.kickoff_utc))} Lima · ${c.market}`),E('small','leg-price',auditedPrice(c)||'Cuota pendiente de consulta')),E('small','leg-probability',pct(c.probability*100)));list.append(row);});
 box.append(list,E('p','parlay-probability',`Probabilidad conjunta orientativa: ${pct(parlay.probability*100)}. Producto bajo supuesto de independencia entre partidos.`),E('p','parlay-note','Deben acertarse todas las selecciones. Respaldo reciente y cuota disponible son criterios distintos.'));
 const pricing=parlay.legs.reduce((p,m)=>p*m.parlay_selection.pricing_probability,1);
 const quotes=parlay.legs.map(m=>m.parlay_selection.odds_audit);if(quotes.every(q=>q?.odds>1))box.append(E('p','parlay-note',`Producto de cuotas individuales consultadas: ${num(quotes.reduce((p,q)=>p*q.odds,1))}. Es una referencia; la cuota de la combinada en Betano no se ha verificado.`));else box.append(E('p','parlay-note','Cuota de la combinada pendiente: faltan precios exactos de una o más selecciones.'));
 box.append(priceBlock({id:parlay.legs.map(m=>m.parlay_selection.id).join('|'),fixture_id:parlay.legs.map(m=>m.fixture_id).sort().join('-'),label:`combinada de ${size} partidos`,fair_odds:1/parlay.probability,minimum_odds:1.05/pricing}));
 return box;
}
function fijasPage(){
 document.title='Fijas y combinadas del día · FOOTDATA';const page=E('div','fijas-page page-enter');page.append(breadcrumbs([{label:'Inicio',href:'#/'},{label:'Fijas'}]));
 const banner=E('section','fijas-banner');banner.append(eyebrow('UNA LECTURA PARA CADA RIESGO'),E('h1',null,'Las fijas, con fundamento.'),E('p',null,'Ganador, doble oportunidad, hándicap, ambos marcan y goles primero. Rachas y modelo; estadísticas como alternativas.'));page.append(banner);
 if(!fijasReady()){page.append(empty('Selecciones pendientes de actualización','Las predicciones están disponibles; esta sección necesita una versión coincidente de las selecciones.'));main.replaceChildren(page);return;}
 const audit=state.fijas.odds_audit;if(audit){const counts=audit.counts;const summary=E('aside','odds-audit-summary');summary.append(E('strong',null,`Revisión Betano · ${audit.fixtures} partidos · ${audit.selections} sugerencias`),E('p',null,`${(counts.above_reference||0)+(counts.below_reference||0)} cuotas exactas encontradas: ${counts.above_reference||0} superan el umbral del modelo y ${counts.below_reference||0} quedan por debajo. ${audit.selections-(counts.above_reference||0)-(counts.below_reference||0)} sin cuota exacta validada.`),E('small',null,`Consulta del ${dateFmt.format(new Date(audit.first_observed_at))}, ${timeFmt.format(new Date(audit.first_observed_at))}–${timeFmt.format(new Date(audit.last_observed_at))} Lima. Precios capturados, sin actualización en vivo.`),link('revision_cuotas_betano.html','Ver las 532 sugerencias y filtrar por precio ↗','fijas-day-link'));page.append(summary);}
 const matches=futureMatches().map(m=>fijasMatch(m)).filter(Boolean);const days=[...new Set(matches.map(m=>m.date_lima))].sort();
 if(!days.length){page.append(empty('No hay selecciones futuras','Se actualizarán al generar los próximos partidos.'));main.replaceChildren(page);return;}
 const query=new URLSearchParams((location.hash.split('?')[1]||''));const requested=query.get('fecha');
 if(!days.includes(state.fijasDate))state.fijasDate=days.includes(requested)?requested:days[0];
 const tools=E('div','fijas-toolbar');const dates=E('div','date-filters');dates.setAttribute('aria-label','Día de las fijas');
 const sizePicker=E('div','parlay-size');sizePicker.setAttribute('aria-label','Selecciones de la combinada');
 const content=E('div');
 const update=()=>{
  dates.querySelectorAll('button').forEach(b=>{const active=b.dataset.day===state.fijasDate;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});sizePicker.querySelectorAll('button').forEach(b=>{const active=Number(b.dataset.size)===state.parlaySize;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
  const today=matches.filter(m=>m.date_lima===state.fijasDate);const list=E('div','daily-picks');const title=sectionIntro('Las propuestas de cada partido',`${today.length} ${today.length===1?'partido':'partidos'} · Horarios de Lima · Las probabilidades se indican en texto pequeño.`);list.append(title);
  for(const r of today){const m=state.payload.matches.find(m=>String(m.fixture_id)===r.fixture_id);const article=E('article','daily-fixture');const heading=E('div','daily-fixture-heading');const teams=append(E('div','daily-teams'),crest(r.home),E('h3',null,`${name(r.home)} — ${name(r.away)}`),crest(r.away));heading.append(teams,append(E('div','daily-meta'),E('span',null,`${leagueFor(r.competition)?.display||r.competition} · ${timeFmt.format(new Date(r.kickoff_utc))} Lima`),link(matchHref(m),'Ver partido ↗')));const picks=E('div','picks-grid');picks.append(...r.tiers.map(t=>pickView(t.selection,t)));article.append(heading,picks);list.append(article);}
  content.replaceChildren(parlayPanel(today,state.parlaySize),list);
  if(today.some(m=>m.limited_european_sample))content.prepend(E('p','fijas-footnote daily-sample-note','Champions tiene una muestra europea reducida y carece de calibración propia. Consulta la muestra de cada propuesta.'));
 };
 days.forEach(day=>{const b=E('button','filter-chip',dateFmt.format(new Date(day+'T12:00:00Z')));b.type='button';b.dataset.day=day;b.addEventListener('click',()=>{state.fijasDate=day;update();});dates.append(b);});
 [3,4].forEach(size=>{const b=E('button','filter-chip',`${size} selecciones`);b.type='button';b.dataset.size=size;b.addEventListener('click',()=>{state.parlaySize=size;update();});sizePicker.append(b);});tools.append(dates,sizePicker);page.append(tools,content);
 const method=E('details','market-details fijas-method');method.append(E('summary',null,'Cómo elegimos las propuestas'));const notes=E('div','fijas-method-copy');for(const text of Object.values(state.fijas.policy))notes.append(E('p',null,text));notes.append(link(state.fijas.bookmaker.rules_url,'Definiciones oficiales de mercados de Betano ↗'));method.append(notes);page.append(method);main.replaceChildren(page);update();
}

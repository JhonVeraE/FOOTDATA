'use strict';
// Season statistics are observations, independent from the prediction model.
const TEAM_METRICS=[['goals','Goles'],['shots','Remates'],['sot','Tiros al arco'],['corners','Córners'],['cards','Tarjetas'],['fouls','Faltas']];
const TEAM_LEADERS=[
 {metric:'goals',side:'for',direction:'max',label:'Mejor ataque',detail:'Más goles anotados'},
 {metric:'goals',side:'against',direction:'min',label:'Mejor defensa',detail:'Menos goles recibidos'},
 {metric:'shots',side:'for',direction:'max',label:'Más remates',detail:'Producción ofensiva'},
 {metric:'sot',side:'for',direction:'max',label:'Más tiros al arco',detail:'Remates a portería'},
 {metric:'corners',side:'for',direction:'max',label:'Más córners',detail:'Córners a favor'},
 {metric:'cards',side:'for',direction:'min',label:'Menos tarjetas',detail:'Disciplina del equipo'},
 {metric:'fouls',side:'for',direction:'min',label:'Menos faltas',detail:'Faltas cometidas'},
 {metric:'shots',side:'against',direction:'min',label:'Menos remates concedidos',detail:'Remates del rival'},
 {metric:'sot',side:'against',direction:'min',label:'Menos tiros al arco concedidos',detail:'Tiros a portería del rival'},
 {metric:'corners',side:'against',direction:'min',label:'Menos córners concedidos',detail:'Córners del rival'},
 {metric:'cards',side:'for',direction:'max',label:'Más tarjetas',detail:'Mayor cantidad, no mejor rendimiento'},
 {metric:'fouls',side:'for',direction:'max',label:'Más faltas',detail:'Mayor cantidad, no mejor rendimiento'},
 {metric:'cards',side:'against',direction:'max',label:'Rivales con más tarjetas',detail:'Tarjetas mostradas al rival'},
 {metric:'fouls',side:'against',direction:'max',label:'Más faltas recibidas',detail:'Faltas cometidas por el rival'}
];
const teamUI={scope:'all',view:'standings',unit:'average',metric:'shots',side:'for',query:'',sort:'points',direction:'desc',route:''};
function teamDate(value){return value?dateFmt.format(new Date(value+'T12:00:00Z')):'Sin registros';}
function teamStamp(value){if(!value)return 'Sin actualización';return `${dateFmt.format(new Date(value))} · ${timeFmt.format(new Date(value))} Lima`;}
function teamLeagueHref(l){return `${leagueHref(l)}/equipos`;}
function teamHref(l,team){return `${leagueHref(l)}/equipo/${encodeURIComponent(team)}`;}
function teamLeagueNavigation(l,active){
 const nav=E('nav','league-section-nav');nav.setAttribute('aria-label','Apartados de la competición');
 for(const [key,href,label] of [['matches',leagueHref(l),'Próximos partidos'],['teams',teamLeagueHref(l),'Equipos y posiciones']]){
  const a=link(href,label,`league-section-link${key===active?' active':''}`);if(key===active)a.setAttribute('aria-current','page');nav.append(a);
 }return nav;
}
function teamMetric(row,metric,side='for',unit=teamUI.unit){return row?.metrics?.[metric]?.[side]?.[unit]??null;}
function teamNumber(value,unit=teamUI.unit){return value===null||value===undefined?'—':num(value,unit==='total'?0:2);}
function teamScopeLabel(){return {all:'General',home:'Local',away:'Visitante'}[teamUI.scope];}
function teamControls(options,current,onchange,label){
 const group=E('div','team-segment');group.setAttribute('role','group');group.setAttribute('aria-label',label);
 for(const [value,title] of options){const button=E('button',value===current?'active':'',title);button.type='button';button.setAttribute('aria-pressed',String(value===current));button.addEventListener('click',()=>onchange(value));group.append(button);}return group;
}
function teamSelect(label,options,current,onchange){
 const wrap=E('label','team-select');wrap.append(E('span',null,label));const select=E('select');select.setAttribute('aria-label',label);
 for(const [value,title] of options){const option=E('option',null,title);option.value=value;option.selected=value===current;select.append(option);}select.addEventListener('change',()=>onchange(select.value));wrap.append(select);return wrap;
}
function teamIdentity(l,team){const a=link(teamHref(l,team),null,'team-identity');a.setAttribute('aria-label',`Ver estadísticas y partidos de ${name(team)}`);a.append(crest(team,'team-mini-crest'),E('span',null,name(team)),E('span','team-open-arrow','↗'));return a;}
function standingsFor(data){
 const official=data.standings?.tables?.[teamUI.scope];
 return {rows:official||data.recorded_tables[teamUI.scope]||[],official:Boolean(official)};
}
function teamDataNotice(data){
 const box=E('div','team-data-notice');
 box.append(E('span',null,`Estadísticas hasta el ${teamDate(data.statistics_through)} · ${data.statistics_matches} partidos registrados.`));
 if(data.standings)box.append(E('span',null,`Clasificación: football-data.org · consultada el ${teamStamp(data.standings.updated_at)}.`));
 else box.append(E('span',null,'Clasificación calculada con los partidos registrados; puede diferir de la oficial.'));
 return box;
}
function teamTable(headers,rows,label){
 const wrap=E('div','team-table-scroll');wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label',`${label}. Desplázate horizontalmente para ver todas las columnas.`);
 const table=E('table','teams-table');table.setAttribute('aria-label',label);const head=E('thead');const tr=E('tr');
 for(const header of headers){const th=E('th');th.scope='col';if(typeof header==='string')th.textContent=header;else th.append(header);tr.append(th);}head.append(tr);table.append(head);const body=E('tbody');
 for(const cells of rows){const tr=E('tr');for(const cell of cells){const td=E('td');if(cell instanceof Node)td.append(cell);else td.textContent=cell;tr.append(td);}const teamLink=tr.querySelector('.team-identity');if(teamLink){tr.classList.add('team-linked-row');tr.addEventListener('click',event=>{if(!event.target.closest('a,button,input,select')&&!window.getSelection()?.toString())teamLink.click();});}body.append(tr);}table.append(body);wrap.append(table);return {wrap,table};
}
function teamFixtureLists(team,now=new Date()){
 const played=team.matches?.played||[];const scheduled=team.matches?.scheduled||[];
 const upcoming=scheduled.filter(m=>['POSTPONED','SUSPENDED','IN_PLAY','PAUSED'].includes(m.status)||(m.kickoff_utc?new Date(m.kickoff_utc)>now:m.date>=dayKey(now)));
 return {played,upcoming:[...upcoming].sort((a,b)=>{
  const pending=m=>['POSTPONED','SUSPENDED'].includes(m.status)?'9999':m.kickoff_utc||m.date;
  return pending(a).localeCompare(pending(b));
 })};
}
function teamFixtureRow(l,team,m,finished){
 const row=E('li','team-fixture-row');const when=E('div','team-fixture-date');const postponed=['POSTPONED','SUSPENDED'].includes(m.status);
 const stamp=m.kickoff_utc?new Date(m.kickoff_utc):null;
 const date=E('time',null,postponed?'Fecha por confirmar':stamp?dateFmt.format(stamp):teamDate(m.date));if(!postponed)date.dateTime=m.kickoff_utc||m.date;when.append(date);
 if(!finished)when.append(E('small',null,postponed?(m.status==='POSTPONED'?'Aplazado':'Suspendido'):['IN_PLAY','PAUSED'].includes(m.status)?'En juego':stamp?`${timeFmt.format(stamp)} Lima`:'Hora por confirmar'));
 const fixture=E('div','team-fixture-teams');for(const [side,club] of [['home',m.home],['away',m.away]]){const clubNode=append(E('span',`team-fixture-club ${side}`),crest(club,'team-mini-crest'),E(club===team?'strong':'span',null,name(club)));if(side==='away')fixture.append(E('strong','team-fixture-score',finished?`${m.home_score} – ${m.away_score}`:'vs'));fixture.append(clubNode);}
 const result=E('div','team-fixture-result');if(finished){const margin=(m.home_score-m.away_score)*(m.home===team?1:-1);result.append(E('span',`team-result ${margin>0?'won':margin<0?'lost':'draw'}`,margin>0?'Victoria':margin<0?'Derrota':'Empate'));}else{const prediction=state.payload.matches.find(p=>String(p.fixture_id)===m.fixture_id&&p.local===m.home&&p.visitante===m.away&&p.competition===l.name);if(prediction&&!postponed)result.append(link(matchHref(prediction),'Ver análisis ↗','team-fixture-analysis'));}
 result.append(E('small',null,m.home===team?'Local':'Visitante'));row.append(when,fixture,result);return row;
}
function teamFixtures(l,team,t){
 const section=E('section','team-fixtures');section.append(sectionIntro('Los partidos del equipo',`${l.display||l.name} · Temporada ${state.teamData.season}`));
 const lists=teamFixtureLists(t);const grid=E('div','team-fixture-columns');
 for(const [key,title,finished] of [['upcoming','Próximos partidos',false],['played','Partidos anteriores',true]]){const items=lists[key];const box=E('section','team-fixture-panel');box.append(E('h3',null,title),E('p','team-fixture-caption',finished?'Resultados finales · del más reciente al más antiguo':'Calendario disponible · horarios de Lima'));
  if(!items.length)box.append(E('p','team-fixture-empty',finished?'Todavía no hay resultados registrados para este equipo.':'No hay próximos partidos en el calendario disponible.'));
  else{const list=E('ul','team-fixture-list');list.append(...items.slice(0,5).map(m=>teamFixtureRow(l,team,m,finished)));box.append(list);if(items.length>5){const more=E('details','team-fixture-more');more.append(E('summary',null,`Ver ${items.length-5} partidos más`));const rest=E('ul','team-fixture-list');rest.append(...items.slice(5).map(m=>teamFixtureRow(l,team,m,finished)));more.append(rest);box.append(more);}}
  grid.append(box);
 }section.append(grid,E('p','team-legend','Se muestran los resultados y el calendario registrados de esta competición. Las fechas pendientes pueden cambiar.'));return section;
}
function teamsStandings(l,data,items){
 const {rows,official}=standingsFor(data);const positions=new Map(rows.map(r=>[r.team,r]));
 const visible=items.map(t=>positions.get(t.team)).filter(Boolean).sort((a,b)=>a.position-b.position);
 const section=panel(`Clasificación · ${teamScopeLabel()}`,official?'Posiciones publicadas por football-data.org.':'Tabla de los registros disponibles. Orden: puntos, diferencia de gol y goles a favor; no aplica desempates oficiales.');
 const table=teamTable(['Pos.','Equipo','PJ','G','E','P','GF','GC','DG','Pts'],visible.map(r=>[r.position,teamIdentity(l,r.team),r.played,r.won,r.draw,r.lost,r.goals_for,r.goals_against,`${r.goal_difference>0?'+':''}${r.goal_difference}`,r.points]),`Clasificación de ${l.display||l.name}, ${teamScopeLabel()}`);
 section.append(E('p','team-table-hint','Toca un equipo o su fila para ver sus estadísticas y partidos.'),table.wrap,E('p','team-legend','PJ: partidos · G: ganados · E: empatados · P: perdidos · GF / GC: goles a favor / en contra · DG: diferencia · Pts: puntos.'));
 if(!visible.length)section.append(E('p','explanation','No hay posiciones disponibles para esta búsqueda.'));
 return section;
}
function teamsLeaders(l,items){
 const section=E('section','league-leaders');section.append(sectionIntro('Quién destaca en cada estadística',`Todos los equipos de la liga · ${teamScopeLabel()} · ${teamUI.unit==='average'?'Promedios por partido':'Totales acumulados'}`));
 const grid=E('div','team-leaders');
 for(const spec of TEAM_LEADERS){
  const order=items.filter(t=>teamMetric(t.splits[teamUI.scope],spec.metric,spec.side)!==null).sort((a,b)=>(teamMetric(a.splits[teamUI.scope],spec.metric,spec.side)-teamMetric(b.splits[teamUI.scope],spec.metric,spec.side))*(spec.direction==='min'?1:-1)||name(a.team).localeCompare(name(b.team),'es'));
  const card=E('article','team-leader');card.append(E('p','eyebrow',spec.label));
  if(order.length){const t=order[0],s=t.splits[teamUI.scope],value=teamMetric(s,spec.metric,spec.side);const ties=order.filter(t=>Math.abs(teamMetric(t.splits[teamUI.scope],spec.metric,spec.side)-value)<1e-8);card.append(teamIdentity(l,t.team),E('strong','leader-value',teamNumber(value)),E('p','leader-caption',`${spec.detail} · ${teamUI.unit==='average'?'por partido':'en total'} · ${s.metrics[spec.metric][spec.side].observations} partidos con dato`));if(ties.length>1){const tie=E('p','leader-ties',`Empate: ${ties.slice(0,3).map(t=>name(t.team)).join(', ')}${ties.length>3?` y ${ties.length-3} más`:''}`);tie.title=ties.map(t=>name(t.team)).join(', ');card.append(tie);}}
  else card.append(E('p',null,'Sin datos'));
  grid.append(card);
 }section.append(grid,E('p','team-legend','Los líderes se comparan dentro de la temporada y localía seleccionadas. Menos goles recibidos indica mejor defensa. En tarjetas y faltas, una cantidad mayor no significa jugar mejor. Las muestras pequeñas pueden cambiar rápido.'));return section;
}
function teamsStatistics(l,data,items,refresh){
 const section=E('section','team-stats-section');
 const toolbar=E('div','team-stats-toolbar');
 toolbar.append(teamControls([['average','Por partido'],['total','Totales']],teamUI.unit,v=>{teamUI.unit=v;refresh();},'Mostrar promedios o totales'));
 toolbar.append(teamControls([['for','A favor'],['against','En contra']],teamUI.side,v=>{teamUI.side=v;refresh();},'Perspectiva de las estadísticas'));
 section.append(toolbar);
 const sortOptions=[['played','Partidos'],...TEAM_METRICS];
 if(!sortOptions.some(([k])=>k===teamUI.sort))teamUI.sort='shots';
 const sortBar=E('div','team-sort-bar');sortBar.append(teamSelect('Ordenar por',sortOptions,teamUI.sort,v=>{teamUI.sort=v;refresh();}));
 const reverse=E('button','filter-chip',teamUI.direction==='desc'?'Mayor a menor ↓':'Menor a mayor ↑');reverse.type='button';reverse.addEventListener('click',()=>{teamUI.direction=teamUI.direction==='desc'?'asc':'desc';refresh();});sortBar.append(reverse);section.append(sortBar);
 const value=t=>teamUI.sort==='played'?t.splits[teamUI.scope].played:teamMetric(t.splits[teamUI.scope],teamUI.sort,teamUI.side);
 const sorted=[...items].sort((a,b)=>{const x=value(a),y=value(b);if(x===null&&y===null)return name(a.team).localeCompare(name(b.team),'es');if(x===null)return 1;if(y===null)return -1;return (x-y)*(teamUI.direction==='desc'?-1:1)||name(a.team).localeCompare(name(b.team),'es');});
 const table=teamTable(['#','Equipo','PJ',...TEAM_METRICS.map(([k,label])=>`${label}${teamUI.unit==='average'?' / PJ':''}`)],sorted.map((t,i)=>[i+1,teamIdentity(l,t.team),t.splits[teamUI.scope].played,...TEAM_METRICS.map(([k])=>{
  const metric=t.splits[teamUI.scope].metrics[k][teamUI.side];const cell=E('span',null,teamNumber(metric[teamUI.unit]));cell.title=`${metric.observations} partidos con dato`;return cell;
 })]),`Ranking de estadísticas de ${l.display||l.name}, ${teamScopeLabel()}, ${teamUI.side==='for'?'a favor':'en contra'}`);
 section.append(table.wrap,E('p','team-legend','Promedios simples de esta temporada. PJ indica partidos registrados. Cada media utiliza solo partidos con ese dato; pasa el cursor sobre una cifra para ver su muestra. — significa sin datos. Tarjetas = amarillas + rojas.'));
 if(!sorted.length)section.append(empty('No encontramos ese equipo','Prueba con otro nombre.'));
 return section;
}
function teamsRoster(l,data,items){
 const ranks=new Map((data.standings?.tables?.all||data.recorded_tables.all).map(r=>[r.team,r]));const grid=E('div','teams-roster');
 for(const t of items){const r=ranks.get(t.team);const a=link(teamHref(l,t.team),null,'roster-card');a.append(crest(t.team,'roster-crest'),E('h2',null,name(t.team)),E('p',null,r?`${r.position}º · ${r.points} puntos`:'Sin posición disponible'));
  const mini=E('div','roster-averages');for(const [scope,label] of [['home','Local'],['away','Visitante']])mini.append(append(E('div'),E('span',null,label),E('strong',null,teamNumber(teamMetric(t.splits[scope],'goals','for','average'),'average')),E('small',null,'goles / PJ')));a.append(mini,E('span','roster-link','Ver ficha del equipo ↗'));grid.append(a);
 }if(!items.length)return empty('No encontramos ese equipo','Prueba con otro nombre.');return grid;
}
function teamsPage(l){
 document.title=`Equipos y posiciones · ${l.display||l.name} · FOOTDATA`;
 const page=E('div','teams-page');page.append(breadcrumbs([{label:'Inicio',href:'#/'},{label:l.display||l.name,href:leagueHref(l)},{label:'Equipos y posiciones'}]));
 const data=state.teamData?.competitions?.[l.name];
 if(!data){page.append(empty('Estadísticas de equipos no disponibles','Actualiza los datos de equipos para consultar esta competición.'));main.replaceChildren(page);return;}
 const banner=E('section','league-banner teams-banner');const desc=E('div');desc.append(eyebrow(`${l.country} · Temporada ${state.teamData.season}`),E('h1',null,'La liga, equipo a equipo'),E('p',null,`${data.teams.length} clubes · Posiciones, rankings y rendimiento local / visitante`));banner.append(competitionLogo(l,'league-logo'),desc);page.append(banner,teamLeagueNavigation(l,'teams'),teamDataNotice(data));
 const viewChoices=[['standings','Posiciones'],['leaders','Líderes'],['statistics','Estadísticas'],['roster','Todos los equipos']];
 const views=teamControls(viewChoices,teamUI.view,v=>{teamUI.view=v;draw();},'Vista de equipos');
 const scopes=E('div','team-scopes');const result=E('div','teams-results');const searchWrap=E('label','search');const search=E('input');search.type='search';search.placeholder='Buscar equipo…';search.setAttribute('aria-label','Buscar equipo en la liga');search.value=teamUI.query;searchWrap.append(search);
 const controls=E('div','team-controls');controls.append(views,searchWrap);page.append(controls,scopes,result);const count=E('p','list-meta');count.setAttribute('aria-live','polite');result.before(count);
 const draw=()=>{
  views.querySelectorAll('button').forEach((b,i)=>{const active=viewChoices[i][0]===teamUI.view;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
  scopes.replaceChildren();if(teamUI.view!=='roster')scopes.append(teamControls([['all','General'],['home','Local'],['away','Visitante']],teamUI.scope,v=>{teamUI.scope=v;draw();},'Local o visitante'));
  const items=data.teams.filter(t=>norm(`${name(t.team)} ${t.team}`).includes(norm(teamUI.query)));
  count.textContent=`${items.length} ${items.length===1?'equipo':'equipos'} · ${teamUI.view==='roster'?'Promedios de goles por partido':teamScopeLabel()}`;
  if(teamUI.view==='leaders'){
   searchWrap.hidden=true;count.textContent=`${data.teams.length} equipos · ${teamScopeLabel()}`;
   const section=E('section');section.append(teamControls([['average','Por partido'],['total','Totales']],teamUI.unit,v=>{teamUI.unit=v;draw();},'Mostrar promedios o totales'),teamsLeaders(l,data.teams));result.replaceChildren(section);
  }else{searchWrap.hidden=false;result.replaceChildren(teamUI.view==='standings'?teamsStandings(l,data,items):teamUI.view==='statistics'?teamsStatistics(l,data,items,draw):teamsRoster(l,data,items));}
 };
 search.addEventListener('input',()=>{teamUI.query=search.value;draw();});main.replaceChildren(page);draw();
}
function teamProfilePage(l,team){
 const data=state.teamData?.competitions?.[l.name],t=data?.teams.find(t=>t.team===team);if(!t){main.replaceChildren(empty('Equipo no disponible','Vuelve a la lista de equipos.'),link(teamLeagueHref(l),'Ver equipos','plain-button'));return;}
 document.title=`${name(team)} · Estadísticas · FOOTDATA`;const page=E('article','team-profile-page');
 page.append(breadcrumbs([{label:'Inicio',href:'#/'},{label:l.display||l.name,href:leagueHref(l)},{label:'Equipos',href:teamLeagueHref(l)},{label:name(team)}]));
 const hero=E('section','league-banner team-profile-hero');const desc=E('div');const position=(data.standings?.tables?.all||data.recorded_tables.all).find(r=>r.team===team);desc.append(eyebrow(`${l.display||l.name} · ${state.teamData.season}`),E('h1',null,name(team)),E('p',null,position?`${position.position}º · ${position.points} puntos · ${position.played} partidos en la clasificación`:'Perfil estadístico de la temporada'));hero.append(crest(team,'profile-crest'),desc);page.append(hero,teamLeagueNavigation(l,'teams'),teamDataNotice(data));
 const cards=E('div','team-leaders');for(const [scope,label] of [['all','General'],['home','Local'],['away','Visitante']]){const s=t.splits[scope];const card=E('article','team-leader');card.append(E('p','eyebrow',label),E('strong','leader-value',teamNumber(teamMetric(s,'goals','for','average'),'average')),E('p',null,'goles anotados por partido'),E('small','leader-caption',`${s.played} partidos registrados · ${s.won} G / ${s.draw} E / ${s.lost} P`));cards.append(card);}page.append(cards);
 const section=panel('Todos los números del equipo','Promedios de la temporada, separados entre casa y fuera.');const content=E('div');let unit='average';
 const draw=()=>{
  const rows=[];for(const [key,label] of TEAM_METRICS)for(const [side,sideLabel] of [['for','a favor'],['against','en contra']]){const title=key==='cards'?(side==='for'?'Tarjetas recibidas':'Tarjetas del rival'):key==='fouls'?(side==='for'?'Faltas cometidas':'Faltas recibidas'):`${label} ${sideLabel}`;rows.push([title,...['all','home','away'].map(scope=>teamNumber(teamMetric(t.splits[scope],key,side,unit),unit))]);}
  content.replaceChildren(teamTable(['Estadística','General','Local','Visitante'],rows,`Estadísticas de ${name(team)} por localía`).wrap);
 };
 const toggle=teamControls([['average','Por partido'],['total','Totales']],unit,v=>{unit=v;toggle.querySelectorAll('button').forEach((b,i)=>{const active=['average','total'][i]===unit;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});draw();},'Promedios o totales del equipo');section.append(toggle,content,E('p','team-legend','Solo partidos registrados de esta competición y temporada. Los datos ausentes se excluyen de cada promedio. Tarjetas = amarillas + rojas.'));
 page.insertBefore(teamFixtures(l,team,t),cards);page.append(section,link(teamLeagueHref(l),'← Volver a todos los equipos','plain-button'));main.replaceChildren(page);draw();
}
function handleTeamsRoute(parts,l){
 if(parts[2]==='equipos'||parts[2]==='lideres'){if(teamUI.route!==l.slug){Object.assign(teamUI,{scope:'all',view:'standings',query:'',sort:'shots',direction:'desc',route:l.slug});}if(parts[2]==='lideres')teamUI.view='leaders';teamsPage(l);return true;}
 if(parts[2]==='equipo'){let team;try{team=decodeURIComponent(parts[3]||'');}catch{team='';}teamProfilePage(l,team);return true;}
 return false;
}

'use strict';
// Datos de jugadores (temporada en curso). Fuente: estadísticas públicas de SofaScore, capturadas desde la PC.
let PLAYERS_PROMISE=null;
function loadPlayers(){if(!PLAYERS_PROMISE)PLAYERS_PROMISE=fetch('data/players.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null);return PLAYERS_PROMISE;}
const PLAYER_COLS=[['goals','Goles'],['assists','Asist.'],['shots','Remates'],['sot','Tiros al arco'],['yc','Amarillas'],['rc','Rojas'],['fouls','Faltas'],['xg','xG'],['min','Minutos'],['apps','PJ']];
const PLAYER_SORTS=[['goals','Goles'],['sot','Tiros al arco'],['shots','Remates'],['assists','Asistencias'],['cards','Tarjetas'],['cards90','Tarjetas por 90 min'],['sot90','Tiros al arco por 90 min'],['goals90','Goles por 90 min'],['fouls','Faltas'],['xg','Goles esperados (xG)'],['min','Minutos']];
const playerUI={team:'',pos:'',sort:'goals',query:''};
function playerValue(p,key){if(key==='cards90')return p.min>=270?p.p90.cards:-1;if(key==='sot90')return p.min>=270?p.p90.sot:-1;if(key==='goals90')return p.min>=270?p.p90.goals:-1;return p[key]??0;}
function initials(n){return String(n).split(/\s+/).filter(Boolean).slice(0,2).map(w=>w[0]).join('').toUpperCase();}
function playerAvatar(p){const a=E('span','player-avatar',initials(p.name));return a;}
function playerIdentity(p,team){const box=E('div','player-identity');const text=E('div');text.append(E('strong',null,p.name),E('small',null,[team?name(team):null,p.pos,p.jersey?`#${p.jersey}`:null,p.age?`${p.age} años`:null].filter(Boolean).join(' · ')));box.append(playerAvatar(p),text);return box;}
function allPlayers(comp){const out=[];for(const [team,list] of Object.entries(comp.teams))for(const p of list)out.push({...p,team});return out;}
function playerRows(list,showTeam){return list.map(p=>[playerIdentity(p,showTeam?p.team:null),...PLAYER_COLS.map(([k])=>k==='xg'?num(p.xg,2):String(p[k]??0))]);}
function playerNote(comp){return E('p','team-legend',`Temporada ${comp.season} · ${comp.players} jugadores · Datos al ${comp.observed_at?dateFmt.format(new Date(comp.observed_at)):''} Las tasas "por 90 min" solo se calculan con 270 minutos o más jugados.`);}
function leaderCard(title,detail,list,key,fmt){const card=E('article','team-leader player-leader');card.append(E('p','eyebrow',title));const ol=E('ol','player-leader-list');
 for(const p of list.slice(0,5)){const li=E('li');li.append(playerIdentity(p,p.team),E('strong',null,fmt(p)));ol.append(li);}card.append(ol,E('small','leader-caption',detail));return card;}
function playerLeaders(players){
 const by=(key,min=0)=>players.filter(p=>p.min>=min&&playerValue(p,key)>0).sort((a,b)=>playerValue(b,key)-playerValue(a,key)||b.min-a.min);
 const grid=E('div','team-leaders player-leaders');
 grid.append(leaderCard('Goleadores','Goles en la temporada',by('goals'),'goals',p=>String(p.goals)),
  leaderCard('Más tiros al arco','Remates a portería en la temporada',by('sot'),'sot',p=>String(p.sot)),
  leaderCard('Más remates','Remates totales en la temporada',by('shots'),'shots',p=>String(p.shots)),
  leaderCard('Más tarjetas','Amarillas + rojas en la temporada',by('cards'),'cards',p=>`${p.yc}🟨${p.rc?` ${p.rc}🟥`:''}`),
  leaderCard('Propensos a tarjeta','Tarjetas por 90 minutos (mín. 270 min)',by('cards90',270),'cards90',p=>num(p.p90.cards,2)),
  leaderCard('Más faltas','Faltas cometidas en la temporada',by('fouls'),'fouls',p=>String(p.fouls)));
 return grid;
}
function playersLeagueView(l){
 const box=E('div','players-view');box.append(E('div','loading-state',''));
 loadPlayers().then(data=>{
  const comp=data?.competitions?.[l.name];
  if(!comp){box.replaceChildren(empty('Datos de jugadores en preparación','Por ahora están disponibles los jugadores de LaLiga. Pronto sumaremos esta liga.'));return;}
  const players=allPlayers(comp);const teams=[...new Set(players.map(p=>p.team))].sort((a,b)=>name(a).localeCompare(name(b)));
  const tools=E('div','team-controls player-controls');
  const mk=(label,opts,cur,on)=>{const lab=E('label','team-select');lab.append(E('span',null,label));const s=E('select');for(const [v,t] of opts){const o=E('option',null,t);o.value=v;if(v===cur)o.selected=true;s.append(o);}s.addEventListener('change',()=>{on(s.value);draw();});lab.append(s);return lab;};
  const searchWrap=E('label','search');const search=E('input');search.type='search';search.placeholder='Buscar jugador…';search.value=playerUI.query;search.addEventListener('input',()=>{playerUI.query=search.value;draw();});searchWrap.append(search);
  tools.append(mk('Equipo',[['','Todos'],...teams.map(t=>[t,name(t)])],playerUI.team,v=>playerUI.team=v),mk('Posición',[['','Todas'],['Portero','Porteros'],['Defensa','Defensas'],['Mediocampista','Mediocampistas'],['Delantero','Delanteros']],playerUI.pos,v=>playerUI.pos=v),mk('Ordenar por',PLAYER_SORTS,playerUI.sort,v=>playerUI.sort=v),searchWrap);
  const leaders=playerLeaders(players);const meta=E('p','list-meta');const table=E('div');
  const draw=()=>{const list=players.filter(p=>(!playerUI.team||p.team===playerUI.team)&&(!playerUI.pos||p.pos===playerUI.pos)&&norm(p.name).includes(norm(playerUI.query))).sort((a,b)=>playerValue(b,playerUI.sort)-playerValue(a,playerUI.sort)||b.min-a.min);
   meta.textContent=`${list.length} jugadores · ordenados por ${PLAYER_SORTS.find(s=>s[0]===playerUI.sort)[1].toLowerCase()}`;
   table.replaceChildren(teamTable(['Jugador',...PLAYER_COLS.map(c=>c[1])],playerRows(list.slice(0,150),true),'Estadísticas de jugadores').wrap);};
  box.replaceChildren(sectionIntro('Los jugadores de la liga','Goles, remates, tiros al arco, tarjetas y faltas de cada futbolista en esta temporada.'),leaders,tools,meta,table,playerNote(comp));draw();
 });
 return box;
}
function teamPlayersSection(l,team){
 const section=panel('Jugadores','Estadísticas de cada futbolista del equipo en esta temporada.');const body=E('div');section.append(body);
 loadPlayers().then(data=>{const list=data?.competitions?.[l.name]?.teams?.[team];if(!list){section.remove();return;}
  const comp=data.competitions[l.name];body.append(playerLeaders(list.map(p=>({...p,team}))),teamTable(['Jugador',...PLAYER_COLS.map(c=>c[1])],playerRows(list,false),`Jugadores de ${name(team)}`).wrap,playerNote(comp));});
 return section;
}
function matchPlayersSection(m){
 const section=panel('Jugadores a seguir','Quién marca, quién patea al arco y quién ve tarjetas en cada equipo, con datos de esta temporada.');section.id='jugadores';const body=E('div','players-match-grid');section.append(body);
 loadPlayers().then(data=>{const comp=data?.competitions?.[m.competition];if(!comp||!comp.teams[m.local]||!comp.teams[m.visitante]){section.remove();document.querySelector('.detail-anchor-nav a[href="#jugadores"]')?.remove();return;}
  for(const [team,side] of [[m.local,'home'],[m.visitante,'away']]){const ps=comp.teams[team].map(p=>({...p,team}));const col=E('div',`players-match-col ${side}`);
   const head=E('div','form-team-heading');head.append(crest(team),append(E('div'),E('h3',null,name(team)),E('p',null,`${ps.length} jugadores con minutos`)));col.append(head);
   const block=(title,list,fmt,caption)=>{const b=E('div','players-match-block');b.append(E('p','eyebrow',title));const ol=E('ol','player-leader-list');for(const p of list.slice(0,3)){const li=E('li');li.append(playerIdentity(p,null),E('strong',null,fmt(p)));ol.append(li);}if(!list.length)ol.append(E('li',null,'Sin datos suficientes'));b.append(ol,E('small','leader-caption',caption));return b;};
   const by=(key,min=0)=>ps.filter(p=>p.min>=min&&playerValue(p,key)>0).sort((a,b)=>playerValue(b,key)-playerValue(a,key)||b.min-a.min);
   col.append(block('Goleadores',by('goals'),p=>`${p.goals} ${p.goals===1?'gol':'goles'}`,'Goles en la temporada'),
    block('Tiros al arco',by('sot90',270),p=>`${num(p.p90.sot,1)} / 90`,'Tiros al arco cada 90 minutos'),
    block('Propensos a tarjeta',by('cards90',270),p=>`${p.yc}🟨${p.rc?` ${p.rc}🟥`:''}`,'Ordenados por tarjetas cada 90 minutos'));
   body.append(col);}
  section.append(playerNote(comp));});
 return section;
}

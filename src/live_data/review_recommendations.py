"""Settle the frozen published shortlist against verified final full-match data."""
import argparse, hashlib, html, json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
from recommendations import event_values
from paths import ARTIFACT_DIR, WEB_DIR
from review_matchday import save

def settle(selection, metrics):
    kind=selection['kind']
    if kind not in ['result','double_chance','handicap','btts','result_goals','goals','shots','sot','fouls','corners','cards']:
        return {'status':'unverified','reason':'Mercado no soportado.'}
    if kind=='cards':return {'status':'unverified','reason':'El CSV no reproduce las reglas de tarjetas Betano.'}
    metric=kind if kind in ['goals','shots','sot','fouls','corners'] else 'goals'
    values=metrics.get(metric)
    if not values or any(v is None for v in values):return {'status':'unverified','reason':'Estadística final ausente.'}
    if selection.get('line') is not None and float(selection['line'])%1!=.5:
        return {'status':'unverified','reason':'Liquidación con devolución o fracciones no implementada.'}
    row={}
    for key,pair in metrics.items():row[key+'_for'],row[key+'_against']=pair
    hit=bool(event_values(pd.DataFrame([row]),selection,True)[0])
    return {'status':'won' if hit else 'lost','hit':hit,'actual_metric':metric,'actual_home':values[0],'actual_away':values[1]}

def summary(rows):
    n=sum(x['status'] in ['won','lost'] for x in rows);won=sum(x['status']=='won' for x in rows)
    return {'selections':len(rows),'settled':n,'won':won,'lost':n-won,'unverified':len(rows)-n,'hit_rate':won/n if n else None}

def render_html(result):
    e=lambda s:html.escape(str(s));names={'won':'ACIERTO','lost':'FALLO','unverified':'SIN VERIFICAR'}
    metric_names={'goals':'goles','shots':'remates','sot':'tiros a puerta','fouls':'faltas','corners':'córners','cards':'tarjetas'}
    def actual(x):return e(f'{x.get("actual_home","—")} – {x.get("actual_away","—")} ({metric_names.get(x.get("actual_metric"),"sin dato")})')
    def badge(status):return f'<b class="{e(status)}">{names.get(status,e(status))}</b>'
    def table(headers,rows):return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+e(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>'
    s=result['tier_summary'];u=result['unique_summary']
    body=f'<h1>FOOTDATA · Resultados del {e(result["date"])}</h1><p>Comparación con las recomendaciones publicadas antes del inicio. Se conservan las selecciones y probabilidades originales.</p><div class="cards"><article><strong>{s["won"]}/{s["settled"]}</strong> fijas principales acertadas</article><article><strong>{u["won"]}/{u["settled"]}</strong> mercados únicos acertados</article><article><strong>{len(result["matches"])}</strong> partidos con estadísticas finales</article></div>'
    body+='<h2>La combinada que se publicó</h2>'
    for parlay in result['parlays']:
        body+=f'<h3>{parlay["size"]} selecciones · {badge(parlay["status"]) if parlay["status"]!="unavailable" else "No se publicó: partidos insuficientes"}</h3>'
        if parlay['legs']:body+=table(['Partido','Selección publicada','Resultado'],[(e(x['match']),e(x['label']),badge(x['status'])) for x in parlay['legs']])
    body+='<p>El resultado de la combinada mide cumplimiento deportivo. No se calcula beneficio: no hay importe apostado ni cuota combinada de cierre registrada.</p><h2>Las fijas principales</h2>'
    body+=table(['Partido','Nivel','Selección','Probabilidad previa','Resultado real (local–visita)','Balance'],[(e(x['match']),e(x['tier']),e(x['label']),f'{x["probability"]*100:.1f}%',actual(x),badge(x['status'])) for x in result['tiers']])
    body+='<h2>Balance por riesgo</h2>'+table(['Nivel','Acertadas','Falladas','Porcentaje'],[(e(k),v['won'],v['lost'],f'{v["hit_rate"]*100:.1f}%' if v['hit_rate'] is not None else '—') for k,v in result['by_tier'].items()])
    body+='<h2>Todos los mercados publicados, sin contar duplicados</h2><p>Una selección repetida en la ficha, una fija y la combinada cuenta una sola vez aquí.</p>'
    body+=table(['Partido','Mercado','Selección','Probabilidad previa','Resultado real (local–visita)','Balance'],[(e(x['match']),e(x['market']),e(x['label']),f'{x["probability"]*100:.1f}%',actual(x),badge(x['status'])) for x in result['unique_selections']])
    body+='<h2>Estadísticas incorporadas a la base de datos</h2>'
    body+=table(['Partido','Marcador','Remates','A puerta','Faltas','Córners','Tarjetas*'],[(f'<a href="{e(m["source_url"])}">{e(m["home"]+" – "+m["away"])}</a>',*[e(' – '.join(map(str,m['metrics'][k]))) for k in ['goals','shots','sot','fouls','corners','cards']]) for m in result['matches']])
    body+='<p>* Tarjetas en la base = amarillas + rojas, según el criterio existente; no equivale al sistema de liquidación de tarjetas de Betano.</p><h2>Qué funcionó y qué falló</h2>'
    body+=''.join('<p>'+e(x)+'</p>' for x in result['analysis'])
    body+='<h2>Trazabilidad</h2>'
    if result['date']=='2026-10-19':body+='<p>Parma–Torino: 0–3 verificado en Sofascore; se conserva la respuesta original discrepante de la API y la corrección documentada.</p>'
    body+='<p>Fuentes finales enlazadas en la tabla; capturas originales conservadas. Corte de revisión: '+e(result['reviewed_at'])+'.</p>'
    return '<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FOOTDATA · Revisión diaria</title><style>body{font:16px system-ui;background:#f5f5ef;color:#182b25;max-width:1240px;margin:auto;padding:28px}h1{font-size:34px}h2{margin-top:40px}p{line-height:1.6}table{width:100%;border-collapse:collapse;background:white;font-size:14px}th,td{text-align:left;padding:14px;border-bottom:1px solid #dde5db;vertical-align:top}th{background:#173c30;color:white}.scroll{overflow:auto}.won{color:#216b41}.lost{color:#ae3434}.unverified{color:#886a23}.cards{display:flex;gap:18px;flex-wrap:wrap}.cards article{padding:25px;background:white;border-radius:15px;flex:1;min-width:200px}.cards strong{display:block;font-size:40px}a{color:#216b41}</style><main>'+body+'</main></html>'

def main(capture_dir,date,output=None):
    capture=Path(capture_dir);frozen_path=capture/'fijas_before_results.json'
    frozen=json.loads(frozen_path.read_text(encoding='utf-8'));review=json.loads((capture/'review.json').read_text(encoding='utf-8'))
    actual={m['fixture_id']:m for m in review['matches']};all_rows=[];tier_rows=[];matches=[];lookup={}
    deferred={m['fixture_id']:m for m in review.get('deferred',[])+review.get('pending',[])}
    if pd.Timestamp(frozen['generated_at'])>=min(pd.Timestamp(x['kickoff_utc']) for x in actual.values()):raise ValueError('Shortlist is not pre-match')
    for m in frozen['matches']:
        if m['date_lima']!=date and m['fixture_id'] not in actual:continue
        fid=m['fixture_id']
        if fid not in actual and fid not in deferred:raise ValueError('Missing final data without documented postponement')
        a=actual.get(fid)
        if pd.Timestamp(m['prediction_generated_at'])>=pd.Timestamp(m['kickoff_utc']):raise ValueError('Not a pre-match prediction')
        metrics={s['metric']:s['actual'] for s in a['statistics']} if a else {}
        if a:matches.append({'fixture_id':fid,'home':m['home'],'away':m['away'],'metrics':metrics,'source_url':a['source_url']})
        selections={x['selection']['id']:x['selection'] for x in m['markets']+m['tiers'] if x.get('selection')}
        if m.get('parlay_selection'):selections[m['parlay_selection']['id']]=m['parlay_selection']
        for sid,c in selections.items():
            if c.get('published_at') and pd.Timestamp(c['published_at'])>=pd.Timestamp(m['kickoff_utc']):raise ValueError('Selection published after kickoff')
            settled=settle(c,metrics) if a else {'status':'unverified','reason':deferred[fid]['reason']}
            row={'fixture_id':fid,'selection_id':sid,'match':m['home']+' – '+m['away'],'market':c['market'],'label':c['label'],'probability':c['probability'],**settled}
            all_rows.append(row);lookup[(fid,sid)]=row
        for t in m['tiers']:
            if t.get('selection'):tier_rows.append({**lookup[(fid,t['selection']['id'])],'tier':t['label']})
    parlays=[]
    for day in frozen['days']:
        if day['date_lima']!=date:continue
        for p in day['parlays']:
            legs=[lookup[(leg['fixture_id'],leg['selection']['id'])] for leg in p['legs']]
            status='unavailable' if not legs else 'lost' if any(x['status']=='lost' for x in legs) else 'won' if all(x['status']=='won' for x in legs) else 'unverified'
            parlays.append({'size':p['size'],'status':status,'probability_before_match':p['probability'],'legs':legs})
    result={'date':date,'reviewed_at':datetime.now(timezone.utc).isoformat(),'frozen_shortlist_sha256':hashlib.sha256(frozen_path.read_bytes()).hexdigest(),'matches':matches,'tiers':tier_rows,'unique_selections':all_rows,'tier_summary':summary(tier_rows),'unique_summary':summary(all_rows),'by_tier':{k:summary([x for x in tier_rows if x['tier']==k]) for k in dict.fromkeys(x['tier'] for x in tier_rows)},'parlays':parlays,'analysis':[
      'La combinada de tres acertó: Rayo menos de 1,5 goles (1), Monza +1,5 (victoria 4–0) y Parma–Torino menos de 3,5 goles (3). La opción de cuatro no se publicó por falta de partidos elegibles.',
      'Las conservadoras acertaron 4/4; las normales, 3/4; las arriesgadas, 1/4. La falta normal fue Rayo más de 12,5 faltas: cometió 9.',
      'La arriesgada acertada fue Getafe–Rayo más de 19,5 remates: hubo 33. Fallaron Tottenham o empate y menos de 3,5 goles (3–1), Cagliari menos de 12,5 remates (16) y Parma o empate y menos de 3,5 goles (0–3).',
      'El favorito del modelo acertó 2/4, ambos marcan como dirección de probabilidad 2/4 y el marcador exacto 0/4. Los tres aciertos de la combinada no significan que se acertaran los ganadores de todos los partidos.',
      'Los remates totales se desviaron una media de 6,96 por partido, los tiros a puerta 2,88 y las faltas 4,45. Son los conteos que conviene seguir contrastando. Cuatro partidos no bastan para reajustar o validar el modelo; se añaden al seguimiento sin retocar las predicciones anteriores.'
    ]}
    if date!='2026-10-19':result['analysis']=[f"Fijas principales: {result['tier_summary']['won']}/{result['tier_summary']['settled']}. Mercados únicos: {result['unique_summary']['won']}/{result['unique_summary']['settled']}. Se conservan las probabilidades previas y se registran los resultados, sin reajustar el modelo con esta jornada."]
    if date!='2026-10-19':
        result['analysis'].extend(f"{level}: {counts['won']}/{counts['settled']} acertadas." for level,counts in result['by_tier'].items())
        result['analysis'].extend(f"Falló {x['label']} en {x['match']}: resultado final {x['actual_home']}–{x['actual_away']} ({x['actual_metric']})." for x in tier_rows if x['status']=='lost')
        no_picks=len(matches)-len({x['fixture_id'] for x in tier_rows if x['fixture_id'] in actual})
        result['analysis'].append(f'{no_picks} partidos no tenían fijas principales publicadas; no se cuentan como fallos ni aciertos.')
        result['analysis'].extend(f"Pendiente: {m['home']} – {m['away']}. {m['reason']} No se cuenta como acierto ni fallo." for m in deferred.values())
        result['analysis'].extend(f"{m['home']} – {m['away']}: trasladado del {m['forecast_original_date']} al {date}; se evalúan las selecciones publicadas para la fecha original, sin modificarlas." for m in actual.values() if m.get('schedule_change'))
        for p in parlays:
            if p['status']!='unavailable':result['analysis'].append(f"Combinada de {p['size']}: {sum(x['status']=='won' for x in p['legs'])}/{len(p['legs'])} selecciones cumplidas.")
    for level,counts in result['by_tier'].items():
        expected={'Conservadora':4,'Normal':3,'Arriesgada':1}[level]
        if date=='2026-10-19' and counts['won']!=expected:raise ValueError('Analysis does not reconcile with settlements')
    save(capture/'recommendation_review.json',result);save(ARTIFACT_DIR/'daily_reviews'/date/'recommendation_review.json',result);save(WEB_DIR/'data'/f'recommendation_review_{date}.json',result)
    report=render_html(result)
    latest=max([date]+[p.stem.removeprefix('recommendation_review_') for p in (WEB_DIR/'data').glob('recommendation_review_*.json')])
    for path in [WEB_DIR/f'revision_{date}.html']+([WEB_DIR/'revision_ultima_jornada.html'] if date==latest else []):
        path.write_text(report,encoding='utf-8',newline='\n')
    if output:
        out=Path(output);out.mkdir(parents=True,exist_ok=True);(out/f'FOOTDATA_resultados_{date}.html').write_text(report,encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['tier_summary','unique_summary','by_tier']},ensure_ascii=False,indent=2));return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--capture-dir',required=True);p.add_argument('--date',required=True);p.add_argument('--output');a=p.parse_args();main(a.capture_dir,a.date,a.output)

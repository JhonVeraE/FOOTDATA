"""Traceable pre-match market shortlist. No odds, profitability or certainty claims.

Recent event counts select between model markets; they are never relabelled as
calibrated probabilities. Half-line handicaps avoid ambiguous push settlement.
"""
import json
from itertools import combinations
from math import prod
import numpy as np
import pandas as pd
from scipy.stats import nbinom, poisson
from data_store import canonical_team, load_match_stats
from goal_model import score_distribution
from paths import ARTIFACT_DIR, WEB_DIR, DATA_DIR

VERSION='market-shortlist-v3'
LEVELS=[('conservative','Conservadora',.78,.88,.82),('normal','Normal',.63,.78,.70),('risky','Arriesgada',.50,.63,.59)]
MARKETS={'result':'Resultado 1X2','double_chance':'Doble oportunidad','handicap':'Hándicap de goles','goals':'Goles','btts':'Ambos marcan','result_goals':'Resultado y goles','shots':'Remates','sot':'Tiros al arco','fouls':'Faltas','cards':'Tarjetas Betano','corners':'Córners'}
COUNT_KINDS=['shots','sot','fouls','cards','corners']
PRIMARY_MARKETS={'result','double_chance','handicap','goals','btts','result_goals'}
BETANO_RULES='https://support.betano.pe/hc/es-pe/articles/36520716638877-Definiciones-de-mercados-de-f%C3%BAtbol'

def utc(value):
    t=pd.Timestamp(value)
    return t.tz_localize('UTC') if t.tzinfo is None else t.tz_convert('UTC')

def historical_context(stats,report):
    """Only the report's league, preceding 365 days and exclusive result cutoff."""
    cut=min(pd.Timestamp(report['cutoff']),pd.Timestamp(report['fecha']))
    past=stats[(stats.date<cut)&(stats.date>=cut-pd.Timedelta(days=365))&(stats.league==report['competition'])]
    contexts=[]
    for team,venue in [(report['local'],True),(report['visitante'],False)]:
        rows=past[(past.team==canonical_team(team))&(past.is_home==venue)].sort_values(['date','match_id']).tail(5).copy()
        rows.attrs['scope']='competition_and_venue'
        if len(rows)<3 and report['competition']=='UEFA Champions League':
            # Explicitly labelled combined form; never pretend domestic games are Champions games.
            rows=stats[(stats.date<cut)&(stats.date>=cut-pd.Timedelta(days=365))&(stats.team==canonical_team(team))&(stats.is_home==venue)].sort_values(['date','match_id']).tail(5).copy()
            rows.attrs['scope']='combined_competitions_and_venue'
        if len(rows)<3:
            base=stats if report['competition']=='UEFA Champions League' else stats[stats.league==report['competition']]
            general=base[(base.date<cut)&(base.date>=cut-pd.Timedelta(days=365))&(base.team==canonical_team(team))].sort_values(['date','match_id']).tail(5).copy()
            if len(general)>=3:
                rows=general;rows.attrs['scope']='combined_competitions_general' if report['competition']=='UEFA Champions League' else 'competition_general'
        contexts.append(rows)
    return contexts

def event_values(rows,market,current_home):
    """Historical results are reoriented to the upcoming home/away positions."""
    if rows.empty:return np.array([],dtype=bool)
    kind=market['kind']
    if kind in COUNT_KINDS+['goals']:
        scope=market.get('scope','total')
        if scope=='total':values=(rows[kind+'_for']+rows[kind+'_against']).dropna().to_numpy()
        else:
            own=(scope=='home')==current_home
            values=rows[kind+('_for' if own else '_against')].dropna().to_numpy()
        return values>market['line'] if market['side']=='over' else values<market['line']
    gf=rows.goals_for.to_numpy();ga=rows.goals_against.to_numpy()
    h,a=(gf,ga) if current_home else (ga,gf)
    if kind=='result_goals':
        result=event_values(rows,{'kind':'result' if market['side'] in ['home','draw','away'] else 'double_chance','side':market['side']},current_home)
        goals=(h+a)>market['line'] if market['direction']=='over' else (h+a)<market['line']
        return result&goals
    if kind=='result':return h>a if market['side']=='home' else a>h if market['side']=='away' else h==a
    if kind=='btts':
        both=(h>0)&(a>0)
        return both if market['side']=='yes' else ~both
    if kind=='handicap':
        margin=h-a if market['side']=='home' else a-h
        return margin+market['line']>0
    if market['side']=='1X':return h>=a
    if market['side']=='X2':return a>=h
    return h!=a

def evidence(candidate,contexts,report):
    views=[];unique_events={}
    for rows,home in zip(contexts,[True,False]):
        values=event_values(rows,candidate,home)
        scope=rows.attrs.get('scope','competition_and_venue')
        measured=candidate.get('scope','total')
        measure='partido' if measured=='total' else 'producción propia' if (measured=='home')==home else 'permitido al rival'
        streak=0
        for value in values[::-1]:
            if not value:break
            streak+=1
        views.append({'team':report['local' if home else 'visitante'],'venue':'general' if scope.endswith('_general') else 'local' if home else 'visitante','scope':scope,'measure':measure,'hits':int(values.sum()),'matches':len(values),'current_hit_streak':streak})
        # A recent direct encounter can appear in both venue windows. Count it
        # once when ranking support, while retaining each team's honest window.
        valid=rows
        if candidate['kind'] in COUNT_KINDS+['goals']:
            metric=candidate['kind'];scope=candidate.get('scope','total')
            numeric=(rows[metric+'_for']+rows[metric+'_against']) if scope=='total' else rows[metric+('_for' if (scope=='home')==home else '_against')]
            valid=rows[numeric.notna()]
        for match_id,value in zip(valid.match_id,values):unique_events[str(match_id)]=bool(value)
    n=len(unique_events);hits=sum(unique_events.values())
    return {'contexts':views,'matches':n,'hits':hits,'rate':hits/n if n else None,'window':'Hasta cinco por equipo y localía dentro de 365 días; la mezcla de competiciones se identifica en cada muestra','latest_result':max((str(r.date.max().date()) for r in contexts if not r.empty),default=None)}

def fmt(line):return f'{line:g}'.replace('.',',')

def candidates(report,contexts,dispersion_data=None,quotes=None,as_of=None):
    matrix=score_distribution(report['lam_home'],report['lam_away'],report['model']['rho'])
    h,a=np.indices(matrix.shape);total=h+a;out=[]
    clock=utc(as_of) if as_of is not None else pd.Timestamp.now(tz='UTC')
    covered=set()
    for (fixture,_),quote in (quotes or {}).items():
        if fixture==str(report['fixture_id']) and quote.get('complete_market_snapshot') and utc(quote['kickoff_utc'])==utc(report['kickoff_utc']) and pd.Timedelta(0)<=clock-utc(quote['observed_at'])<=pd.Timedelta(minutes=15):covered.add((quote['kind'],quote['scope']))
    def add(kind,side,line,label,p,method,scope='total',**extra):
        stress=.10 if kind in COUNT_KINDS else .05
        pricing_p=max(.01,float(p)-stress)
        item={'id':f'{kind}:{scope}:{side}:{line}:{extra.get("direction", "")}','fixture_id':str(report['fixture_id']),'kind':kind,'market':MARKETS[kind],'scope':scope,'side':side,'line':line,'label':label,'probability':float(p),'probability_method':method,'individually_calibrated':False,
              'fair_odds':1/max(float(p),1e-9),'pricing_probability':pricing_p,'stress_discount':stress,'minimum_odds':1.05/pricing_p,'price_status':'unverified','bookmaker':'Betano',**extra}
        item['evidence']=evidence(item,contexts,report)
        # This is a selection score, not an alternative probability estimate.
        item['support_gap']=abs(item['evidence']['rate']-p) if item['evidence']['rate'] is not None else .25
        quote=(quotes or {}).get((str(report['fixture_id']),item['id']))
        if quote is None and (kind,scope) in covered:item['price_status']='not_in_observed_lines'
        if quote and quote.get('kickoff_utc') and utc(quote['kickoff_utc'])==utc(report['kickoff_utc']):
            age=(utc(as_of) if as_of is not None else pd.Timestamp.now(tz='UTC'))-utc(quote['observed_at'])
            if pd.Timedelta(0)<=age<=pd.Timedelta(minutes=15):
                item['observed_quote']=quote
                item['price_status']='above_reference' if quote['odds']>=item['minimum_odds'] else 'below_reference'
        out.append(item)
    ph,pd_,pa=[report[k]/100 for k in ['p_home','p_draw','p_away']]
    for side,label,p in [('home',f"Gana {report['local']}",ph),('draw','Empate',pd_),('away',f"Gana {report['visitante']}",pa)]:add('result',side,None,label,p,'Probabilidad 1X2 publicada')
    for side,label,p in [('1X',f"{report['local']} o empate",ph+pd_),('X2',f"{report['visitante']} o empate",pa+pd_),('12','Cualquiera gana, sin empate',ph+pa)]:
        add('double_chance',side,None,label,p,'Suma de probabilidades 1X2 publicadas')
    for side,team,margin in [('home',report['local'],h-a),('away',report['visitante'],a-h)]:
        for line in [-2.5,-1.5,1.5,2.5]:
            add('handicap',side,line,f'{team} {line:+g}'.replace('.',','),matrix[margin+line>0].sum(),'Matriz original de goles, sin calibración específica de hándicap')
    for line in [1.5,2.5,3.5,4.5]:
        for side,mask,label in [('over',total>line,'Más de'),('under',total<line,'Menos de')]:
            add('goals',side,line,f'{label} {fmt(line)} goles',matrix[mask].sum(),'Matriz original de goles')
    for scope,team,values in [('home',report['local'],h),('away',report['visitante'],a)]:
        for line in [1.5,2.5,3.5]:
            for side,mask,label in [('over',values>line,'Más de'),('under',values<line,'Menos de')]:add('goals',side,line,f'{team}: {label.lower()} {fmt(line)} goles',matrix[mask].sum(),'Matriz original de goles',scope)
    for side,result,label in [('home',h>a,f"Gana {report['local']}"),('away',a>h,f"Gana {report['visitante']}"),('draw',h==a,'Empate'),('1X',h>=a,f"{report['local']} o empate"),('X2',a>=h,f"{report['visitante']} o empate")]:
        for line in [1.5,2.5,3.5]:
            for direction,goals,label2 in [('over',total>line,'más de'),('under',total<line,'menos de')]:add('result_goals',side,line,f'{label} y {label2} {fmt(line)} goles',matrix[result&goals].sum(),'Probabilidad conjunta de la misma matriz de goles; no producto de mercados',direction=direction)
    both=(h>0)&(a>0)
    for side,mask,label in [('yes',both,'Ambos marcan: sí'),('no',~both,'Ambos marcan: no')]:add('btts',side,None,label,matrix[mask].sum(),'Matriz original de goles')
    for kind,lines in [('corners',[5.5,6.5,7.5,8.5,9.5,10.5,11.5,12.5,13.5])]:
        market=report.get('count_markets',{}).get(kind,{})
        mean=market.get('mean');alpha=market.get('dispersion')
        if market.get('status')!='estimate' or mean is None or alpha is None:continue
        dist=nbinom(1/alpha,1/(1+alpha*mean)) if alpha>1e-6 else poisson(mean)
        for line in lines:
            for side,p,label in [('over',dist.sf(np.floor(line)),'Más de'),('under',dist.cdf(np.floor(line)),'Menos de')]:
                add(kind,side,line,f'{label} {fmt(line)} {MARKETS[kind].lower()}',p,'Distribución de conteos sin calibración propia')
    # Mean from the opponent-adjusted production model. Estimate dispersion on
    # pre-cutoff league data, never from the five observations used for support.
    league_data=dispersion_data
    for kind in ['shots','sot','fouls','corners']:
        cross=report.get('cruces',{}).get(kind,{})
        if league_data is None or kind+'_for' not in league_data:continue
        for scope,team in [('home',report['local']),('away',report['visitante']),('total',None)]:
            if scope=='total' and kind=='corners':continue
            if scope=='total' and (cross.get('home') is None or cross.get('away') is None):continue
            mean=cross['home']+cross['away'] if scope=='total' else cross.get(scope)
            if mean is None or mean<=0:continue
            sample=league_data[league_data.is_home] if scope=='total' else league_data[league_data.is_home==(scope=='home')]
            observations=(sample[kind+'_for']+sample[kind+'_against']) if scope=='total' else sample[kind+'_for']
            observations=observations.dropna()
            if len(observations)<30:continue
            avg=observations.mean();alpha=max(0.,float((observations.var(ddof=1)-avg)/max(avg*avg,.01)))
            dist=nbinom(1/alpha,1/(1+alpha*mean)) if alpha>1e-6 else poisson(mean)
            low=max(1,int(np.floor(mean*.6)));high=min(50,int(np.ceil(mean*1.4))+1)
            for line in np.arange(low+.5,high,1.):
                line=round(float(line),1)
                for side,p,label in [('over',dist.sf(np.floor(line)),'más de'),('under',dist.cdf(np.floor(line)),'menos de')]:
                    text=f'{team}: {label} {fmt(line)} {MARKETS[kind].lower()}' if team else f'{label.capitalize()} {fmt(line)} {MARKETS[kind].lower()} totales'
                    add(kind,side,line,text,p,'Media ajustada por rival y dispersión histórica por localía; probabilidad sin calibración específica',scope)
    return out

def selection_cost(item,target):
    return abs(item['probability']-target)+.30*item['support_gap']+.015*(item['kind'] in COUNT_KINDS)-.08*(item.get('price_status')=='above_reference')

def supported(item):
    ev=item['evidence']
    return ev['matches']>=5 and all(v['matches']>=3 and v['hits']>v['matches']/2 for v in ev['contexts']) and item['support_gap']<=.30 and item['fair_odds']>=1.18 and item.get('price_status') not in ['below_reference','not_in_observed_lines']

def preferred_selection(pool,target):
    """Market families take precedence over the count of available half-lines.

    Hundreds of count lines must not displace a supported goal/result market
    merely by landing closer to an arbitrary probability target.
    """
    primary=[c for c in pool if c['kind'] in PRIMARY_MARKETS]
    return min(primary or pool,key=lambda c:selection_cost(c,target),default=None)

def make_match(report,stats,quotes=None,as_of=None):
    contexts=historical_context(stats,report)
    cut=min(pd.Timestamp(report['cutoff']),pd.Timestamp(report['fecha']))
    dispersion_data=stats[(stats.date<cut)&(stats.date>=cut-pd.Timedelta(days=365))&(stats.league==report['competition'])]
    options=candidates(report,contexts,dispersion_data,quotes,as_of);by_market=[]
    for kind in MARKETS:
        pool=[c for c in options if c['kind']==kind and .50<=c['probability']<=.88 and supported(c)]
        best=min(pool,key=lambda c:selection_cost(c,.74),default=None)
        by_market.append({'kind':kind,'market':MARKETS[kind],'selection':best,'status':'available' if best else 'incompatible_settlement' if kind=='cards' else 'insufficient_support','reason':'Betano cuenta una roja como dos tarjetas y excluye la segunda amarilla. El CSV agregado no permite reconstruir esa liquidación.' if kind=='cards' else None})
    tiers=[];used=set()
    for key,label,lo,hi,target in LEVELS:
        pool=[c for c in options if lo<=c['probability']<hi and c['kind'] not in used and supported(c)]
        best=preferred_selection(pool,target)
        tiers.append({'key':key,'label':label,'selection':best,'status':'available' if best else 'insufficient_data'})
        if best:used.add(best['kind'])
    # Prefer goal/result markets; retain count alternatives only without support there.
    eligible=[c for c in options if .78<=c['probability']<=.88 and supported(c)]
    sample=report.get('quality',{}).get('effective_sample_min',0)
    unknown=any('sin historial' in warning.lower() for warning in report.get('data_warnings',[]))
    pick=preferred_selection(eligible,.82) if sample>=5 and not unknown else None
    return {'fixture_id':str(report['fixture_id']),'competition':report['competition'],'home':report['local'],'away':report['visitante'],'kickoff_utc':report['kickoff_utc'],'date_lima':utc(report['kickoff_utc']).tz_convert('America/Lima').date().isoformat(),'prediction_generated_at':report['generated_at'],'cutoff':report['cutoff'],'tiers':tiers,'markets':by_market,'parlay_selection':pick,'market_priority':'goals_and_results_first','limited_european_sample':report['competition']=='UEFA Champions League'}

def choose_parlay(pool,size,as_of):
    """No same-game multiplication or repeated team across legs. Never pad."""
    pool=[m for m in pool if utc(m['kickoff_utc'])>utc(as_of) and m.get('parlay_selection')]
    best=None;best_p=-1
    for group in combinations(pool,size):
        teams=[canonical_team(t) for m in group for t in [m['home'],m['away']]]
        if len(set(teams))!=2*size:continue
        p=prod(m['parlay_selection']['probability'] for m in group)
        if p>best_p:best=list(group);best_p=p
    if best is None:return {'size':size,'status':'insufficient_matches','legs':[],'probability':None}
    return {'size':size,'status':'available','legs':[{'fixture_id':m['fixture_id'],'selection':m['parlay_selection']} for m in best],'probability':best_p,'assumption':'Producto bajo supuesto de independencia entre partidos. No calibrado como combinada.'}

def build_payload(predictions,stats,as_of=None,quotes=None):
    now=utc(as_of) if as_of is not None else pd.Timestamp.now(tz='UTC')
    matches=[make_match(m,stats,quotes,now) for m in predictions['matches'] if utc(m['kickoff_utc'])>now and m.get('calendar_status') in ['SCHEDULED','TIMED']]
    days=[]
    for day in sorted({m['date_lima'] for m in matches}):
        fixtures=[m for m in matches if m['date_lima']==day]
        days.append({'date_lima':day,'matches':len(fixtures),'parlays':[choose_parlay(fixtures,size,now) for size in [3,4]]})
    return {'schema_version':2,'version':VERSION,'generated_at':now.isoformat(),'dataset_id':predictions['run']['dataset_id'],'prediction_run_generated_at':predictions['run']['generated_at'],'matches':matches,'days':days,'bookmaker':{'name':'Betano','live_odds_available':False,'rules_url':BETANO_RULES},'policy':{'levels':'Conservadora 78–88%, normal 63–78%, arriesgada 50–63%. Además se exige cuota teórica ≥1,18. Son bandas relativas de selección.','selection':'Mayoría estricta en ambas muestras recientes, al menos tres observaciones válidas por equipo y cinco encuentros únicos. Se descartan candidatos con discrepancia modelo/frecuencia superior a 30 puntos. La frecuencia no sustituye a una probabilidad calibrada.','scope':'Hasta cinco partidos por equipo y localía, anteriores al corte. Champions puede usar forma doméstica/europea combinada, identificada expresamente. No se recomienda con muestra insuficiente.','settlement':'90 minutos y añadido; hándicap asiático con medias unidades. Tarjetas excluidas: el CSV agregado no reproduce las reglas Betano de roja = 2, segunda amarilla excluida.','parlay':'Una selección por partido sin repetir equipos. Producto bajo independencia; los mercados combinados de un mismo partido se calculan en la matriz conjunta, nunca multiplicándolos.','odds':'Cuota teórica = 1/p. Umbral orientativo = 1,05/(p − descuento): 5 puntos para goles/resultado y 10 para conteos. Son hipótesis de sensibilidad elegidas, no un intervalo de confianza ni calibración adicional. Introduce la cuota Betano del mismo mercado para comparar. No se han obtenido cuotas en vivo ni confirmado disponibilidad de las líneas.','validation':'Estas reglas de selección y probabilidades de mercados ampliados necesitan evaluación prospectiva propia. Mayor cumplimiento reciente no demuestra rentabilidad futura.'}}

def apply_editorial_overrides(data,predictions,stats,as_of=None,overrides=None):
    """Explicit editorial slots retain the model's joint probability and cutoff.

    Never change archived publications or transfer a different market's quote.
    Ignore expired slots when a later matchday is generated.
    """
    clock=utc(as_of) if as_of is not None else pd.Timestamp.now(tz='UTC')
    if overrides is None:
        path=DATA_DIR/'recommendation_overrides.json'
        overrides=json.loads(path.read_text(encoding='utf-8')).get('overrides',[]) if path.exists() else []
    reports={str(m['fixture_id']):m for m in predictions['matches']}
    applied=[]
    for override in overrides:
        if override.get('effective_from') and utc(override['effective_from'])>clock:continue
        fid=str(override['fixture_id'])
        match=next((m for m in data['matches'] if m['fixture_id']==fid),None)
        report=reports.get(fid)
        if match is None or report is None or utc(match['kickoff_utc'])<=clock:continue
        if [match['home'],match['away'],match['kickoff_utc']]!=[override['home'],override['away'],override['kickoff_utc']]:raise ValueError('Editorial fixture identity mismatch')
        if utc(report['generated_at'])>=utc(report['kickoff_utc']):raise ValueError('Editorial forecast is not pre-match')
        tier=next(t for t in match['tiers'] if t['key']==override['tier'])
        options=candidates(report,historical_context(stats,report),as_of=clock)
        chosen=next((c for c in options if c['id']==override['candidate_id']),None)
        if chosen is None:raise ValueError('Unknown editorial market')
        chosen.update(editorial_override=True,published_at=clock.isoformat(),editorial_reason=override['reason'])
        tier.update(selection=chosen,status='available',selection_origin='user_requested')
        applied.append({'fixture_id':fid,'tier':tier['key'],'candidate_id':chosen['id'],'published_at':clock.isoformat(),'reason':override['reason']})
    if applied:
        data['editorial_overrides']=applied
        data['revised_at']=clock.isoformat()
        data['policy']['editorial']='Las selecciones editoriales solicitadas se identifican en su ficha. El nivel es una etiqueta editorial y puede quedar fuera de las bandas automáticas; la probabilidad del modelo se conserva.'
    return data

def publish_recommendations(predictions,stats=None):
    if stats is None:stats=load_match_stats()
    quote_file=ARTIFACT_DIR/'betano_odds.json'
    quote_records=json.loads(quote_file.read_text(encoding='utf-8'))['records'] if quote_file.exists() else []
    quotes={(r['fixture_id'],r['candidate_id']):r for r in quote_records}
    data=build_payload(predictions,stats,quotes=quotes)
    apply_editorial_overrides(data,predictions,stats)
    data['policy']['priority']='Se priorizan ganador, doble oportunidad, hándicap, ambos marcan, goles y resultado con goles entre las propuestas que cumplen los mismos filtros de respaldo y precio. Remates, tiros al arco, faltas y córners son complementarios. La prioridad no modifica las probabilidades del modelo.'
    data['policy']['streaks']='Cada muestra muestra los aciertos consecutivos más recientes de la selección, hasta cinco observaciones válidas. Es un dato descriptivo para revisar la continuidad, no un multiplicador de probabilidad.'
    data['bookmaker'].update(observed_odds_records=len(quote_records),observed_fixtures=len({r['fixture_id'] for r in quote_records}),latest_quote_observation=max((r['observed_at'] for r in quote_records),default=None),live_odds_available=False)
    # Local import avoids importing the generation entry point during tests.
    from generate_jornada_predictions import atomic_json
    atomic_json(WEB_DIR/'data/fijas.json',data)
    atomic_json(ARTIFACT_DIR/'recommendations.json',data)
    stamp=utc(data['generated_at']).strftime('%Y%m%dT%H%M%S%fZ')
    atomic_json(ARTIFACT_DIR/'recommendation_archive'/f'{stamp}.json',data)
    print(f"Fijas: {len(data['matches'])} matches, {len(data['days'])} local dates; archived before kickoff.")
    return data

if __name__=='__main__':
    predictions=json.loads((WEB_DIR/'data/predictions.json').read_text(encoding='utf-8'))
    publish_recommendations(predictions)

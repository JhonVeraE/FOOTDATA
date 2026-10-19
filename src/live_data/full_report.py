"""Versioned prediction contract shared by JSON, Excel, web and content."""
import json
import numpy as np
import pandas as pd
from scipy.stats import poisson,nbinom
from data_store import before,canonical_team,results_from_stats,today_local,season_for
from goal_model import AttackDefenceModel,ModelConfig
from match_analysis import build_full_profiles,head_to_head_ponderado
from team_profile import detectar_tendencia,DEFAULT_LAMBDA
from paths import ARTIFACT_DIR

def model_settings(cutoff):
    p=ARTIFACT_DIR/'model_selection.json'
    if not p.exists():raise ValueError('Run evaluate_models.py first')
    s=json.loads(p.read_text(encoding='utf-8'))
    if not s.get('promoted') or pd.Timestamp(s['calibration_until'])>pd.Timestamp(cutoff):
        raise ValueError('No validated model available for this cutoff; use the temporal evaluator')
    return s

def clean_json(obj):
    if isinstance(obj,dict):return {k:clean_json(v) for k,v in obj.items()}
    if isinstance(obj,(list,tuple)):return [clean_json(v) for v in obj]
    if isinstance(obj,(float,np.floating)):return float(obj) if np.isfinite(obj) else None
    if isinstance(obj,np.integer):return int(obj)
    return obj

def count_projection(mean,observations,lines):
    values=pd.to_numeric(observations,errors='coerce').dropna().to_numpy()
    if mean is None or len(values)<3:return {'status':'insufficient_data','mean':mean,'calibrated':False}
    avg=float(values.mean());var=float(values.var(ddof=1))
    alpha=max((var-avg)/max(avg**2,.01),0.)
    dist=nbinom(1/alpha,1/(1+alpha*mean)) if alpha>1e-6 else poisson(mean)
    return {'status':'estimate','mean':mean,'distribution':'negative_binomial' if alpha>1e-6 else 'poisson','dispersion':alpha,'calibrated':False,'interval_90':[int(dist.ppf(.05)),int(dist.ppf(.95))],
        'lines':{str(x):{'over':float(dist.sf(np.floor(x))),'under':float(dist.cdf(np.ceil(x)-1)),'push':float(dist.pmf(x)) if x==int(x) else 0.} for x in lines}}

def build_full_match_report(match_stats,home,away,competition='',fecha='',lam=DEFAULT_LAMBDA,model=None,cutoff=None,batch_context=None):
    if not fecha:raise ValueError('fecha and an explicit temporal cutoff are required')
    date=pd.Timestamp(fecha).normalize()
    cut=min(pd.Timestamp(cutoff).normalize() if cutoff else today_local(),date)
    if batch_context is not None and pd.Timestamp(batch_context['cutoff'])!=cut:raise ValueError('Batch context contains a different cutoff')
    past=batch_context['past'] if batch_context is not None else before(match_stats,cut);home=canonical_team(home);away=canonical_team(away)
    if home==away:raise ValueError('A team cannot play itself')
    if past.empty:return {'error':'No pre-cutoff observations'}
    settings=model_settings(cut)
    if model is None:model=AttackDefenceModel(ModelConfig(**settings['config'])).fit(results_from_stats(past),cut)
    if model.cutoff>cut or model.latest>=cut:raise ValueError('Model contains post-cutoff results')
    pred=model.predict(home,away,competition)
    raw=np.array([pred['p_home_win'],pred['p_draw'],pred['p_away_win']])
    # Domestic calibration is not transferred to Champions as if validated there.
    temp=settings['temperature'] if competition!='UEFA Champions League' else 1.
    z=np.log(np.maximum(raw,1e-12))/temp;z-=z.max();cal=np.exp(z);cal/=cal.sum()
    direct=past[past.league==competition]
    enough=all((direct.team==t).sum()>=3 for t in [home,away])
    descriptive=(direct if enough else past).copy()
    descriptive.attrs['report_season']=season_for(date)
    scope='competition_only' if enough else 'combined_competitions_estimate'
    hp=build_full_profiles(descriptive,home,lam);ap=build_full_profiles(descriptive,away,lam)
    hc=hp['local'] or hp['general'];ac=ap['visitante'] or ap['general']
    dh=hc['decay_weighted'];da=ac['decay_weighted']
    hh=head_to_head_ponderado(past,home,away);reverse=head_to_head_ponderado(past,away,home)
    cross={'goals':{'home':pred['lam_home'],'away':pred['lam_away'],'method':'attack-defence-v2'}}
    from count_model import refined_count_means
    refined=refined_count_means(past,home,away,competition,cut,cache=(batch_context or {}).get('counts',{}).get(competition))
    markets={};cc={}
    for stat in ['corners','cards','shots','sot','fouls']:
        h=a=None
        if dh is not None and da is not None:
            def shrink(d,key):
                avg=descriptive[key].mean();v=d[key];n=d['coverage'][key]
                effective=min(d['peso_efectivo'],n)
                return (v*effective+avg*5)/(effective+5) if v is not None and pd.notna(avg) else None
            vals=[shrink(dh,stat+'_for'),shrink(da,stat+'_against'),shrink(da,stat+'_for'),shrink(dh,stat+'_against')]
            h=(vals[0]+vals[1])/2 if all(v is not None for v in vals[:2]) else None
            a=(vals[2]+vals[3])/2 if all(v is not None for v in vals[2:]) else None
        if stat in refined:h=refined[stat]['home'];a=refined[stat]['away']
        cross[stat]={'home':h,'away':a,'method':refined[stat]['method'] if stat in refined else 'shrunk_descriptive_estimate','scope':scope,'calibrated':False}
        if stat in refined:cross[stat].update(config=refined[stat]['config'],mean_validated_until=refined[stat]['validated_until'])
        cc[stat+'_home']=h;cc[stat+'_away']=a;cc[stat+'_total']=h+a if h is not None and a is not None else None
        if stat in ['cards','corners']:
            g=descriptive[descriptive.is_home];totals=g[stat+'_for']+g[stat+'_against']
            lines=(2.5,3.5,4.5,5.5) if stat=='cards' else (7.5,8.5,9.5,10.5)
            markets[stat]=count_projection(cc[stat+'_total'],totals,lines)
            cc[stat+'_rango']='-'.join(map(str,markets[stat]['interval_90'])) if 'interval_90' in markets[stat] else 'sin datos'
    count_h=0 if dh is None else dh['partidos'];count_a=0 if da is None else da['partidos']
    eff_h=0 if dh is None else dh['peso_efectivo'];eff_a=0 if da is None else da['peso_efectivo']
    cc.update(partidos_home=count_h,partidos_away=count_a)
    warnings=[]
    if not enough:warnings.append('Estadísticas descriptivas combinan competiciones; no son promedios propios de esta copa.')
    if pred['unknown_teams']:warnings.append('Equipos sin historial: fuerza contraída al promedio, no evaluada específicamente.')
    if pred['competition_prior']:warnings.append('Competición sin historial: usa información previa de ligas domésticas.')
    sample=min(eff_h,eff_a)
    confidence={'nivel':'Muestra limitada' if sample<8 else 'Probabilidad estimada','calibrated':competition!='UEFA Champions League','sample_effective_home':eff_h,'sample_effective_away':eff_a,'note':'La probabilidad del favorito no mide certeza ni rentabilidad.'}
    p=(cal*100).tolist();favorite=[home,'Empate',away][int(cal.argmax())]
    trends=lambda ctx:{stat:detectar_tendencia(ctx['ventanas'],stat) for stat in ['goals_for','goals_against','shots_for','corners_for','cards_for']}
    g25=pred['goal_lines']['2.5'];over=g25['over']>=g25['under']
    from league_core import build_elo_ratings
    elo=batch_context['elo'] if batch_context is not None else build_elo_ratings(results_from_stats(past))
    out={'schema_version':2,'local':home,'visitante':away,'competition':competition,'fecha':str(date.date()),'cutoff':str(cut.date()),'generated_at':pd.Timestamp.now(tz='UTC').isoformat(),
        'model':model.metadata(),'dataset_id':match_stats.attrs.get('dataset_id'),'sources':sorted(past.source.unique()) if 'source' in past else [],'latest_observation':str(past.date.max().date()),'data_warnings':warnings,
        'quality':{'effective_sample_min':sample,'statistics_scope':scope,'champions_calibration_validated':False},
        'forma_home':hc['ventanas'],'forma_away':ac['ventanas'],'contexto_home':'local' if hp['local'] else 'general','contexto_away':'visitante' if ap['visitante'] else 'general',
        'cruces':cross,'cc_detalle':cc,'h2h_ida':hh,'h2h_vuelta':reverse,'h2h_total_partidos':hh['partidos'],'h2h_adjusts_goals':False,
        'tendencias_home':trends(hc),'tendencias_away':trends(ac),'lam_home':pred['lam_home'],'lam_away':pred['lam_away'],
        'p_home':p[0],'p_draw':p[1],'p_away':p[2],'raw_1x2':(raw*100).tolist(),'temperature':temp,'marcadores_top5':pred['marcadores_top5'],'marcador_top1':pred['marcadores_top5'][0],
        'btts':pred['btts']*100,'goal_lines':pred['goal_lines'],'count_markets':markets,
        'linea_goles':{'tipo':'Más de' if over else 'Menos de','linea':2.5,'confianza':100*g25['over' if over else 'under'],'calibrated':False},'linea_corners':None,'linea_tarjetas':None,
        'market_calibration':{'1x2':'domestic temperature calibration' if temp!=1 else 'raw model','btts_goals_scores':'raw distribution, separately uncalibrated','corners_cards':'dispersion estimates, not validated'},
        'elo_home':elo.get(home,1500.),'elo_away':elo.get(away,1500.),'elo_used_for_goals':False,'confianza':confidence,'datos_curiosos':[],
        'conclusion':f'Resultado más probable: {favorite} ({max(p):.1f}%). Goles esperados: {home} {pred["lam_home"]:.2f} — {away} {pred["lam_away"]:.2f}. Probabilidad estimada, no certeza.'}
    out['model']['count_refinements']=sorted(refined)
    if refined:out['model']['count_model_version']='venue-shrunk-count-v1'
    return clean_json(out)

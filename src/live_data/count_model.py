"""Venue-aware, shrunk count means. Configs are promoted by temporal evaluation."""
import json
from functools import lru_cache
import numpy as np
import pandas as pd
from paths import ARTIFACT_DIR

COUNT_METRICS=['corners','cards','shots','sot','fouls']
COLS=[f'{m}_{s}' for s in ['for','against'] for m in COUNT_METRICS]

def weighted_context(rows,half_life):
    values=rows.sort_values(['date','match_id'])[COLS].to_numpy(float);n=len(values)
    if not n:return None
    w=np.exp(-np.log(2)*np.arange(n-1,-1,-1)/half_life)[:,None];valid=np.isfinite(values);den=(valid*w).sum(axis=0)
    mean=np.divide(np.where(valid,values*w,0).sum(axis=0),den,out=np.full(len(COLS),np.nan),where=den>0)
    eff=np.divide(den**2,(valid*w*w).sum(axis=0),out=np.zeros(len(COLS)),where=den>0)
    return {'means':mean,'effective':eff,'coverage':valid.sum(axis=0),'legacy_effective':round(float(w.sum()**2/(w*w).sum()),1)}

def snapshot(past,cutoff,half_lives=(5,10,20)):
    if (past.date>=pd.Timestamp(cutoff)).any():raise ValueError('Count snapshot contains post-cutoff results')
    recent=past[past.date>=pd.Timestamp(cutoff)-pd.Timedelta(days=365)]
    priors={(lg,bool(home)):g[COLS].mean().to_numpy(float) for (lg,home),g in recent.groupby(['league','is_home'])}
    legacy={lg:g[COLS].mean().to_numpy(float) for lg,g in past.groupby('league')}
    contexts={half:{(lg,team,bool(home)):weighted_context(g,half) for (lg,team,home),g in past.groupby(['league','team','is_home'],sort=False)} for half in half_lives}
    return {'priors':priors,'legacy_priors':legacy,'contexts':contexts}

def predict_snapshot(cache,league,home,away,config):
    half=config.get('half_life_matches',5);h=cache['contexts'][half].get((league,home,True));a=cache['contexts'][half].get((league,away,False))
    if h is None or a is None:return None
    if config.get('method')=='legacy':
        prior=cache['legacy_priors'][league]
        def shrink(context):
            effective=np.minimum(context['legacy_effective'],context['coverage']);return (np.round(context['means'],3)*effective+prior*5)/(effective+5)
        hs,aas=shrink(h),shrink(a)
        return np.stack([(hs[:5]+aas[5:])/2,(aas[:5]+hs[5:])/2])
    hp=cache['priors'].get((league,True));ap=cache['priors'].get((league,False))
    if hp is None or ap is None:return None
    strength=config['prior_matches']
    def shrink(context,prior):
        eff=context['effective'];mean=np.where(np.isfinite(context['means']),context['means'],prior)
        return (mean*eff+prior*strength)/(eff+strength)
    hs,aas=shrink(h,hp),shrink(a,ap)
    if config['method']=='venue_average':return np.stack([(hs[:5]+aas[5:])/2,(aas[:5]+hs[5:])/2])
    baseh=(hp[:5]+ap[5:])/2;basea=(ap[:5]+hp[5:])/2
    return np.stack([hs[:5]*aas[5:]/np.maximum(baseh,.01),aas[:5]*hs[5:]/np.maximum(basea,.01)])

@lru_cache(maxsize=1)
def selected_count_settings():
    path=ARTIFACT_DIR/'count_model_selection.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None

def refined_count_means(past,home,away,competition,cutoff,cache=None):
    selection=selected_count_settings()
    if not selection or competition=='UEFA Champions League' or pd.Timestamp(cutoff)<pd.Timestamp(selection['active_from']):return {}
    promoted={k:v for k,v in selection['metrics'].items() if v['promoted']}
    if not promoted:return {}
    rows=past[past.league==competition]
    halves=sorted({v['config']['half_life_matches'] for v in promoted.values()})
    cache=snapshot(rows,cutoff,halves) if cache is None else cache;out={}
    for metric,setting in promoted.items():
        values=predict_snapshot(cache,competition,home,away,setting['config']);index=COUNT_METRICS.index(metric)
        if values is not None and np.isfinite(values[:,index]).all():out[metric]={'home':float(values[0,index]),'away':float(values[1,index]),'config':setting['config'],'method':'venue-shrunk-count-v1','validated_until':selection['validated_until']}
    return out

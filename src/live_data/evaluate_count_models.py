"""Monthly frozen count forecasts, selection and validation in distinct periods."""
import json
import numpy as np
import pandas as pd
from scipy.special import gammaln
from data_store import load_match_stats
from paths import ARTIFACT_DIR
from count_model import snapshot,predict_snapshot,COUNT_METRICS

def summarize(records,index,candidate):
    if not records:return {'matches':0}
    actual=np.array([r['actual'][:,index] for r in records]);forecast=np.array([r['predictions'][candidate][:,index] for r in records])
    valid=np.isfinite(actual).all(axis=1)&np.isfinite(forecast).all(axis=1);actual=actual[valid];forecast=np.maximum(forecast[valid],.01)
    return {'matches':len(actual),'mae_per_team':float(np.abs(actual-forecast).mean()),'mae_total':float(np.abs(actual.sum(axis=1)-forecast.sum(axis=1)).mean()),
            'poisson_nll_per_team':float((forecast-actual*np.log(forecast)+gammaln(actual+1)).mean()),'predicted_total':float(forecast.sum(axis=1).mean()),'actual_total':float(actual.sum(axis=1).mean())}

def main():
    stats=load_match_stats();stats=stats[stats.league!='UEFA Champions League']
    configs=[{'method':'legacy','half_life_matches':5}]+[{'method':method,'half_life_matches':half,'prior_matches':prior} for method in ['venue_average','venue_ratio'] for half in [5,10,20] for prior in [5,15,30]]
    records={'selection':[],'validation':[],'current':[]}
    fixtures=stats[stats.is_home&(stats.date>='2024-08-01')&(stats.date<'2026-10-18')].sort_values(['date','match_id'])
    for month,g in fixtures.groupby(fixtures.date.dt.to_period('M')):
        cutoff=month.start_time
        phase='selection' if pd.Timestamp('2024-08-01')<=cutoff<pd.Timestamp('2025-03-01') else 'validation' if pd.Timestamp('2025-08-01')<=cutoff<pd.Timestamp('2026-07-01') else 'current' if cutoff>=pd.Timestamp('2026-08-01') else None
        if phase is None:continue
        cache=snapshot(stats[stats.date<cutoff],cutoff)
        for r in g.itertuples():
            preds=[predict_snapshot(cache,r.league,r.team,r.opponent,c) for c in configs]
            if any(p is None for p in preds):continue
            actual=np.array([[getattr(r,m+'_for') for m in COUNT_METRICS],[getattr(r,m+'_against') for m in COUNT_METRICS]],float)
            records[phase].append({'actual':actual,'predictions':preds})
        print(f'Count backtest {month}: {len(g)} fixtures',flush=True)
    metrics={}
    for i,metric in enumerate(COUNT_METRICS):
        selection=[summarize(records['selection'],i,c) for c in range(len(configs))]
        chosen=min(range(len(configs)),key=lambda c:selection[c]['mae_per_team'])
        base=summarize(records['validation'],i,0);candidate=summarize(records['validation'],i,chosen)
        promoted=chosen!=0 and candidate['matches']>=100 and candidate['mae_per_team']<base['mae_per_team'] and candidate['mae_total']<=base['mae_total']*1.02 and candidate['poisson_nll_per_team']<=base['poisson_nll_per_team']
        metrics[metric]={'config':configs[chosen],'promoted':promoted,'selection':{'baseline':selection[0],'candidate':selection[chosen]},'validation':{'baseline':base,'candidate':candidate},
                         'current_diagnostic':{'baseline':summarize(records['current'],i,0),'candidate':summarize(records['current'],i,chosen)}}
    report={'version':'venue-shrunk-count-v1','active_from':'2026-10-19','selected_until':'2025-03-01','validated_until':'2026-07-01',
        'protocol':'Monthly frozen fits. Select Aug 2024-Feb 2025 by per-team MAE; gate Aug 2025-Jun 2026 on improved per-team MAE and Poisson NLL, with total MAE <=102% baseline. Current season through Oct 17 is diagnostic only. Oct 18 is excluded. Historical results are retrospective.',
        'metrics':metrics}
    (ARTIFACT_DIR/'count_model_selection.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True);return report

if __name__=='__main__':main()

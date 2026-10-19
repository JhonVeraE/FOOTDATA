"""Temporal model selection, held-out calibration and walk-forward evaluation.

Run from any folder: python project/src/live_data/evaluate_models.py
Fits are frozen at each month's beginning; all comparison models use the same
pre-month history. No test results select parameters or calibration settings.
"""
import json
from dataclasses import asdict
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import skellam
from data_store import load_match_stats, results_from_stats, before
from goal_model import AttackDefenceModel, ModelConfig
from paths import ARTIFACT_DIR

def probabilities(lh,la):return np.array([skellam.sf(0,lh,la),skellam.pmf(0,lh,la),skellam.cdf(-1,lh,la)])

def legacy_probs(stats,home,away):
    def weighted(g,col):
        values=g[col].to_numpy(float);w=np.exp(-np.log(2)/5*np.arange(len(g)-1,-1,-1))
        return round(float(np.dot(values,w)/w.sum()),3)
    h=stats[(stats.team==home)&stats.is_home].sort_values('date');a=stats[(stats.team==away)&~stats.is_home].sort_values('date')
    if h.empty:h=stats[stats.team==home].sort_values('date')
    if a.empty:a=stats[stats.team==away].sort_values('date')
    if h.empty or a.empty:return None
    lh=round((weighted(h,'goals_for')+weighted(a,'goals_against'))/2,2)
    la=round((weighted(a,'goals_for')+weighted(h,'goals_against'))/2,2)
    hh=stats[(stats.team==home)&(stats.opponent==away)].sort_values('date').tail(5)
    if len(hh)>=2:
        lh=round(.9*lh+.1*round(weighted(hh,'goals_for'),2),2)
        la=round(.9*la+.1*round(weighted(hh,'goals_against'),2),2)
    return probabilities(max(lh,.05),max(la,.05))

def temperature_probs(p,temperature=1.):
    z=np.log(np.maximum(p,1e-12))/temperature;z-=z.max(axis=-1,keepdims=True)
    q=np.exp(z);return q/q.sum(axis=-1,keepdims=True)

def metrics(rows,key='p'):
    p=np.array([r[key] for r in rows]);y=np.array([r['outcome'] for r in rows]);truth=np.eye(3)[y]
    # Reliability by class/bin, with counts so tiny bins are never disguised as evidence.
    reliability={}
    for j,label in enumerate(['home','draw','away']):
        bins=[]
        for low in np.arange(0,1,.1):
            mask=(p[:,j]>=low)&(p[:,j]<low+.1+1e-12)
            if mask.any():bins.append({'range':[round(low,1),round(low+.1,1)],'n':int(mask.sum()),'predicted':float(p[mask,j].mean()),'observed':float(truth[mask,j].mean())})
        reliability[label]=bins
    return {'matches':len(rows),'log_loss':float(-np.log(np.maximum(p[np.arange(len(y)),y],1e-12)).mean()),'brier_sum_3':float(np.square(p-truth).sum(axis=1).mean()),'accuracy':float((p.argmax(axis=1)==y).mean()),'reliability':reliability}

def walk_forward(stats,results,start,end,config,comparisons=False):
    fixtures=results[(results.date>=start)&(results.date<end)].sort_values(['date','match_id'])
    rows=[]
    for month,g in fixtures.groupby(fixtures.date.dt.to_period('M'),sort=True):
        cutoff=month.start_time;train=before(results,cutoff);past=before(stats,cutoff)
        model=AttackDefenceModel(config).fit(train,cutoff)
        for r in g.itertuples():
            pred=model.predict(r.home_team,r.away_team,r.tournament)
            outcome=0 if r.home_score>r.away_score else 1 if r.home_score==r.away_score else 2
            row={'match_id':r.match_id,'date':str(r.date.date()),'competition':r.tournament,'cutoff':str(cutoff.date()),'outcome':outcome,'p':[pred['p_home_win'],pred['p_draw'],pred['p_away_win']],'lam_home':pred['lam_home'],'lam_away':pred['lam_away'],'goals_home':r.home_score,'goals_away':r.away_score,'rho':model.rho,'btts':pred['btts'],'over25':pred['goal_lines']['2.5']['over']}
            if comparisons:
                prev=train[(train.tournament==r.tournament)&(train.date>=cutoff-pd.Timedelta(days=365))]
                if prev.empty:prev=train
                counts=np.array([(prev.home_score>prev.away_score).sum(),(prev.home_score==prev.away_score).sum(),(prev.home_score<prev.away_score).sum()])
                row['baseline']=((counts+1)/(len(prev)+3)).tolist()
                old=legacy_probs(past,r.home_team,r.away_team)
                row['legacy']=None if old is None else old.tolist()
            rows.append(row)
        print(f'{start} {config}: {month}: {len(g)} matches',flush=True)
    return rows

def main():
    stats=load_match_stats();results=results_from_stats(stats)
    # Domestic holdouts have enough history for all candidates. Champions is reported separately.
    domestic=results[results.tournament!='UEFA Champions League'].copy()
    ds=stats[stats.league!='UEFA Champions League'].copy()
    candidates=[ModelConfig(365,10,True),ModelConfig(180,10,True),ModelConfig(365,3,True),ModelConfig(730,10,False)]
    validation=[]
    for c in candidates:
        rows=walk_forward(ds,domestic,'2024-08-01','2025-03-01',c)
        validation.append({'config':asdict(c),'metrics':metrics(rows)})
    selected=min(validation,key=lambda x:x['metrics']['log_loss'])
    config=ModelConfig(**selected['config'])
    calibration=walk_forward(ds,domestic,'2025-03-01','2025-07-01',config)
    p=np.array([r['p'] for r in calibration]);y=np.array([r['outcome'] for r in calibration])
    def loss(t):return float(-np.log(temperature_probs(p,t)[np.arange(len(y)),y]).mean())
    opt=minimize_scalar(loss,bounds=(.7,1.8),method='bounded')
    temp=float(opt.x) if opt.fun<loss(1.) else 1.
    held=walk_forward(ds,domestic,'2025-08-01','2026-07-01',config,True)
    current=walk_forward(stats,results,'2026-08-01','2026-10-18',config,True)
    for r in held+current:r['calibrated']=temperature_probs(np.array(r['p']),temp if r['competition']!='UEFA Champions League' else 1.).tolist()
    def summarize(rows):
        common=[r for r in rows if r['legacy'] is not None]
        out={'new_raw':metrics(rows),'new_calibrated':metrics(rows,'calibrated'),'league_baseline':metrics(rows,'baseline'),'legacy_common_matches':len(common),'legacy':metrics(common,'legacy'),'new_on_common':metrics(common,'calibrated')}
        out['by_league']={lg:{'new':metrics([r for r in rows if r['competition']==lg],'calibrated'),'legacy':metrics([r for r in common if r['competition']==lg],'legacy') if any(r['competition']==lg for r in common) else None} for lg in sorted({r['competition'] for r in rows})}
        # Paired bootstrap descriptive uncertainty on per-fixture log-loss difference.
        pa=np.array([r['calibrated'][r['outcome']] for r in common]);pb=np.array([r['legacy'][r['outcome']] for r in common])
        delta=-np.log(pa)+np.log(pb);rng=np.random.default_rng(42)
        means=[float(rng.choice(delta,len(delta),replace=True).mean()) for _ in range(2000)]
        out['paired_logloss_new_minus_legacy']={'mean':float(delta.mean()),'bootstrap_95':np.quantile(means,[.025,.975]).tolist(),'caution':'Fixture bootstrap; serial dependence is not modeled.'}
        out['goal_mae_per_team']=float(np.mean([(abs(r['lam_home']-r['goals_home'])+abs(r['lam_away']-r['goals_away']))/2 for r in rows]))
        out['raw_goal_markets']={}
        for market in ['btts','over25']:
            p=np.array([r[market] for r in rows])
            y=np.array([int(r['goals_home']>0 and r['goals_away']>0) if market=='btts' else int(r['goals_home']+r['goals_away']>2.5) for r in rows])
            q=np.clip(p,1e-12,1-1e-12)
            out['raw_goal_markets'][market]={'brier':float(np.square(p-y).mean()),'log_loss':float(-(y*np.log(q)+(1-y)*np.log1p(-q)).mean()),'calibrated':False,'observed_rate':float(y.mean()),'predicted_rate':float(p.mean())}
        return out
    # Deployment gate is fixed before examining test scores; test only decides promotion.
    held_summary=summarize(held);current_summary=summarize(current)
    promoted=held_summary['new_on_common']['log_loss']<held_summary['legacy']['log_loss']
    selection={'model_version':'attack-defence-v2','config':asdict(config),'temperature':temp,'calibration_until':'2025-07-01','selected_on':'2024-08-01 to 2025-03-01','calibrated_on':'2025-03-01 to 2025-07-01','promoted':promoted,'selection_metric':'log_loss','dataset_id':stats.attrs['dataset_id']}
    artifact={'protocol':'Monthly frozen fits with strictly earlier dates. Candidate selection and calibration use separate 2024/25 periods. 2025/26 and 2026/27 are subsequent evaluations, never parameter-selection periods. The earlier review already inspected 500 of the 2025/26 fixtures; results here are retrospective, not a prospective claim. Current season includes Champions reported separately; domestic holdout contains no Champions training history.','selection':selection,'candidates':validation,'calibration':{'raw':metrics(calibration),'temperature':temp,'log_loss_raw':loss(1.),'log_loss_adjusted':loss(temp)},'holdout_2025_26':held_summary,'current_2026_27':current_summary,'predictions':held+current}
    ARTIFACT_DIR.mkdir(parents=True,exist_ok=True)
    (ARTIFACT_DIR/'model_selection.json').write_text(json.dumps(selection,indent=2),encoding='utf-8')
    (ARTIFACT_DIR/'evaluation.json').write_text(json.dumps(artifact,indent=2),encoding='utf-8')
    print(json.dumps({'selection':selection,'holdout_new':held_summary['new_calibrated']['log_loss'],'holdout_legacy':held_summary['legacy']['log_loss'],'current_new':current_summary['new_calibrated']['log_loss'],'current_legacy':current_summary['legacy']['log_loss']},indent=2))

if __name__=='__main__':main()

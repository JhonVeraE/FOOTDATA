"""Retrospective temporal check of small goal-rate corrections; never fit to Oct 18."""
import json
import numpy as np
from scipy.special import gammaln
from goal_model import market_summary
from paths import ARTIFACT_DIR

def evaluate(rows,factors):
    probs=[];btts=[];overs=[];nll=[];mae=[]
    for r in rows:
        f=factors.get(r['competition'],factors.get('all',[1.,1.]))
        lh=r['lam_home']*f[0];la=r['lam_away']*f[1];yh=r['goals_home'];ya=r['goals_away']
        p=market_summary(lh,la,r['rho']);probs.append([p['p_home_win'],p['p_draw'],p['p_away_win']])
        btts.append(p['btts']);overs.append(p['goal_lines']['2.5']['over'])
        nll.append(lh-yh*np.log(lh)+gammaln(yh+1)+la-ya*np.log(la)+gammaln(ya+1));mae.append(abs(lh+la-yh-ya))
    y=np.array([r['outcome'] for r in rows]);p=np.array(probs);temp=1.0170313276970937
    z=np.log(np.maximum(p,1e-12))/temp;z-=z.max(axis=1,keepdims=True);p=np.exp(z);p/=p.sum(axis=1,keepdims=True)
    def binary_loss(values,truth):
        q=np.clip(values,1e-12,1-1e-12);return float(-np.mean(truth*np.log(q)+(1-truth)*np.log1p(-q)))
    return {'matches':len(rows),'goal_poisson_nll':float(np.mean(nll)),'goal_total_mae':float(np.mean(mae)),
        'log_loss_1x2':float(-np.mean(np.log(p[np.arange(len(y)),y]))),
        'btts_log_loss':binary_loss(np.array(btts),np.array([r['goals_home']>0 and r['goals_away']>0 for r in rows])),
        'over25_log_loss':binary_loss(np.array(overs),np.array([r['goals_home']+r['goals_away']>2.5 for r in rows]))}

def fitted(rows,split=False):
    if split:return [float((sum(r['goals_home'] for r in rows)+50)/(sum(r['lam_home'] for r in rows)+50)),float((sum(r['goals_away'] for r in rows)+50)/(sum(r['lam_away'] for r in rows)+50))]
    scale=(sum(r['goals_home']+r['goals_away'] for r in rows)+100)/(sum(r['lam_home']+r['lam_away'] for r in rows)+100)
    return [float(scale),float(scale)]

def main():
    archive=json.loads((ARTIFACT_DIR/'evaluation.json').read_text(encoding='utf-8'))
    rows=[r for r in archive['predictions'] if r['competition']!='UEFA Champions League' and r['date']<'2026-10-18']
    train=[r for r in rows if '2025-08-01'<=r['date']<'2026-01-01'];held=[r for r in rows if '2026-01-01'<=r['date']<'2026-07-01'];current=[r for r in rows if r['date']>='2026-08-01']
    candidates={'unchanged':{},'global_rate':{'all':fitted(train)},'venue_rates':{'all':fitted(train,True)},'league_rates':{lg:fitted([r for r in train if r['competition']==lg]) for lg in sorted({r['competition'] for r in train})}}
    training={name:evaluate(train,f) for name,f in candidates.items()};chosen=min(training,key=lambda n:training[n]['goal_poisson_nll'])
    base=evaluate(held,{});selected=evaluate(held,candidates[chosen])
    # Fixed gate. Never choose a replacement candidate by looking at the holdout.
    promoted=chosen!='unchanged' and selected['goal_poisson_nll']<base['goal_poisson_nll'] and selected['over25_log_loss']<base['over25_log_loss'] and selected['log_loss_1x2']<=base['log_loss_1x2']+.002 and selected['btts_log_loss']<=base['btts_log_loss']+.002
    report={'protocol':'Frozen monthly historical forecasts. Fit rate corrections Aug-Dec 2025; choose by Poisson NLL; gate on Jan-Jun 2026; report Aug-Oct 17 2026 without tuning. Retrospective evaluation; Oct 18 excluded.',
        'fitted_until':'2026-01-01','validated_until':'2026-07-01','active_from':'2026-10-19','selected_candidate':chosen,'promoted':promoted,
        'factors':candidates[chosen] if promoted else {},'candidate_training':training,'validation':{'baseline':base,'candidate':selected},
        'current_diagnostic':{'baseline':evaluate(current,{}),'candidate':evaluate(current,candidates[chosen])}}
    (ARTIFACT_DIR/'goal_refinement.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2),flush=True)
    return report

if __name__=='__main__':main()

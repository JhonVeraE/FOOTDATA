"""Model vs market (football-data.co.uk average pre-match odds via xgabora mirror).

Fixtures: model walk-forward predictions (monthly frozen fits) for 2025/26 and 2026/27.
Blend weight alpha (log-linear pooling, p ~ market^a * model^(1-a)) is fitted on
Aug-Dec 2025 only and tested on Jan 2026 onward. ROI uses average odds, flat 1 unit,
and is descriptive only (no claim of profitability).
"""
import json, sys
import numpy as np, pandas as pd
from scipy.optimize import minimize_scalar

P = pd.read_pickle('/home/claude/experiments/pf.pkl')
M = pd.read_pickle('/home/claude/experiments/odds.pkl')
M = M.rename(columns={'HomeTeam': 'home_team', 'AwayTeam': 'away_team'})
D = P.merge(M[['date', 'tournament', 'home_team', 'away_team', 'OddHome', 'OddDraw', 'OddAway', 'MaxHome', 'MaxDraw', 'MaxAway', 'Over25', 'Under25', 'MaxOver25', 'MaxUnder25', 'FTHome', 'FTAway']],
            on=['date', 'tournament', 'home_team', 'away_team'], how='inner')
assert ((D.FTHome == D.gh) & (D.FTAway == D.ga)).mean() > .99, 'score mismatch in join'
D = D[(D.FTHome == D.gh) & (D.FTAway == D.ga)].dropna(subset=['OddHome', 'OddDraw', 'OddAway'])
out = {'protocol': __doc__, 'matched_fixtures': {}}


def market(df):
    q = 1 / df[['OddHome', 'OddDraw', 'OddAway']].to_numpy(float)
    return q / q.sum(1, keepdims=True), q.sum(1) - 1


def pool(pm, pk, a):
    z = a * np.log(pm) + (1 - a) * np.log(pk); z -= z.max(1, keepdims=True)
    e = np.exp(z); return e / e.sum(1, keepdims=True)


def ll(p, y): return float(-np.log(np.maximum(p[np.arange(len(y)), y], 1e-12)).mean())


for w in ['1.0', '0.7']:
    d = D[D.w == w].sort_values('date').reset_index(drop=True)
    pm, margin = market(d); pk = np.array(d.p.tolist()); y = d.y.to_numpy()
    fit = (d.date < '2026-01-01').to_numpy(); test = ~fit
    a = minimize_scalar(lambda a: ll(pool(pm[fit], pk[fit], a), y[fit]), bounds=(0, 1), method='bounded').x
    pb = pool(pm, pk, a)
    res = {'n_fit': int(fit.sum()), 'n_test': int(test.sum()), 'mean_bookmaker_margin': float(margin.mean()),
           'alpha_market_weight': float(a),
           'test_logloss': {'model': ll(pk[test], y[test]), 'market': ll(pm[test], y[test]), 'blend': ll(pb[test], y[test])},
           'test_accuracy': {'model': float((pk[test].argmax(1) == y[test]).mean()), 'market': float((pm[test].argmax(1) == y[test]).mean())}}
    # paired bootstrap blend vs market on test
    lb = -np.log(pb[test][np.arange(test.sum()), y[test]]); lm = -np.log(pm[test][np.arange(test.sum()), y[test]])
    dd = lb - lm; rng = np.random.default_rng(3); bs = [rng.choice(dd, len(dd)).mean() for _ in range(3000)]
    res['blend_minus_market_test'] = {'mean': float(dd.mean()), 'ci95': np.quantile(bs, [.025, .975]).tolist()}
    # Over 2.5 goals: model vs market
    o = d.dropna(subset=['Over25', 'Under25'])
    qo = 1 / o.Over25.to_numpy(); qu = 1 / o.Under25.to_numpy(); po_m = qo / (qo + qu)
    yo = ((o.gh + o.ga) > 2).to_numpy().astype(int); po_k = np.clip(o.o25.to_numpy(), 1e-9, 1 - 1e-9)
    bl = lambda p: float(-(yo * np.log(p) + (1 - yo) * np.log(1 - p)).mean())
    res['over25_logloss_all'] = {'n': len(o), 'model': bl(po_k), 'market': bl(po_m)}
    # Descriptive value test: bet when model prob * avg odds > threshold, on TEST only
    roi = {}
    odds = d[['OddHome', 'OddDraw', 'OddAway']].to_numpy(float); best = d[['MaxHome', 'MaxDraw', 'MaxAway']].to_numpy(float)
    for thr in [1.0, 1.05, 1.10, 1.20]:
        for name, src in [('model', pk), ('blend', pb)]:
            ev = src * odds; pick = ev.argmax(1); sel = test & (ev.max(1) > thr)
            for price_name, price in [('avg', odds), ('max', best)]:
                pay = np.where(pick[sel] == y[sel], price[sel, pick[sel]], 0) - 1
                roi[f'{name}_ev>{thr}_{price_name}odds'] = {'bets': int(sel.sum()), 'roi': float(pay.mean()) if sel.any() else None,
                                                           'ci95': np.quantile([np.random.default_rng(i).choice(pay, len(pay)).mean() for i in range(1000)], [.025, .975]).tolist() if sel.sum() > 20 else None}
    res['value_bets_1x2_test'] = roi
    out[f'shot_weight_{w}'] = res
print(json.dumps(out, indent=1, default=float))
json.dump(out, open('/home/claude/experiments/market_result.json', 'w'), indent=1, default=float)

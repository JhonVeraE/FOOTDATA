"""Experiment: attack/defence Poisson fitted to a blend of goals and a shot-based goal proxy.

Protocol (same as evaluate_models.py):
  * monthly frozen fits, training data strictly before the month's first day;
  * blend weight selected on 2024-08-01..2025-03-01 (domestic) by 1X2 log-loss;
  * evaluated untouched on 2025-08-01..2026-07-01 (domestic holdout) and
    2026-08-01..2026-10-27 (current season, incl. Champions).
The shot proxy uses per-competition conversion rates estimated ONLY from training rows:
  proxy = c_sot * SOT + c_off * (shots - SOT).  Missing shots -> proxy falls back to goals.
Dixon-Coles rho is always estimated from real goals.
"""
import json, sys, time
from pathlib import Path
import numpy as np, pandas as pd
from scipy.optimize import minimize, minimize_scalar
sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_store import load_match_stats, results_from_stats, before
from goal_model import market_summary

HALF_LIFE, REG = 365., 3.
TEMP = 1.0170313276970937  # deployed domestic temperature, not re-tuned here


def conversion(train):
    out = {}
    for comp, g in train.groupby('tournament'):
        g = g.dropna(subset=['shots_for', 'shots_against', 'sot_for', 'sot_against'])
        if len(g) < 50:
            continue
        goals = g.home_score.sum() + g.away_score.sum()
        sot = g.sot_for.sum() + g.sot_against.sum()
        off = (g.shots_for - g.sot_for).sum() + (g.shots_against - g.sot_against).sum()
        # least squares through origin: goals ~ a*sot + b*off (aggregate rows)
        X = np.c_[np.r_[g.sot_for, g.sot_against], np.r_[g.shots_for - g.sot_for, g.shots_against - g.sot_against]]
        y = np.r_[g.home_score, g.away_score]
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        coef = np.clip(coef, 0, None)
        out[comp] = coef
    return out


def fit(train, cutoff, w):
    df = train.dropna(subset=['home_team', 'away_team', 'home_score', 'away_score']).sort_values(['date', 'match_id'])
    cutoff = pd.Timestamp(cutoff).normalize()
    teams = {x: i for i, x in enumerate(sorted(set(df.home_team) | set(df.away_team)))}
    comps = {x: i for i, x in enumerate(sorted(df.tournament.unique()))}
    n, k = len(teams), len(comps)
    h = df.home_team.map(teams).to_numpy(); a = df.away_team.map(teams).to_numpy(); c = df.tournament.map(comps).to_numpy()
    gh = df.home_score.to_numpy(float); ga = df.away_score.to_numpy(float)
    yh, ya = gh.copy(), ga.copy()
    if w < 1:
        conv = conversion(df)
        coef = np.array([conv.get(t, [np.nan, np.nan]) for t in df.tournament])
        ph = coef[:, 0] * df.sot_for.to_numpy(float) + coef[:, 1] * (df.shots_for - df.sot_for).to_numpy(float)
        pa = coef[:, 0] * df.sot_against.to_numpy(float) + coef[:, 1] * (df.shots_against - df.sot_against).to_numpy(float)
        ok = np.isfinite(ph) & np.isfinite(pa)
        yh = np.where(ok, w * gh + (1 - w) * ph, gh); ya = np.where(ok, w * ga + (1 - w) * pa, ga)
    weights = np.exp(-np.log(2) * (cutoff - df.date).dt.days.to_numpy() / HALF_LIFE)
    prior_mu = np.log(max(np.average(ya, weights=weights), .1)); prior_home = np.log(max(np.average(yh, weights=weights), .1)) - prior_mu
    x0 = np.r_[np.zeros(2 * n), np.full(k, prior_mu), np.full(k, prior_home)]

    def objective(x):
        eh = x[2*n+c] + x[2*n+k+c] + x[h] + x[n+a]; ea = x[2*n+c] + x[a] + x[n+h]
        lh = np.exp(eh); la = np.exp(ea)
        loss = np.sum(weights*(lh-yh*eh+la-ya*ea)) + REG*np.dot(x[:2*n], x[:2*n])/2
        loss += 5*np.square(x[2*n:2*n+k]-prior_mu).sum()/2 + 10*np.square(x[2*n+k:]-prior_home).sum()/2
        dh = weights*(lh-yh); da = weights*(la-ya)
        grad = np.r_[np.bincount(h, dh, minlength=n)+np.bincount(a, da, minlength=n)+REG*x[:n],
                     np.bincount(a, dh, minlength=n)+np.bincount(h, da, minlength=n)+REG*x[n:2*n],
                     np.bincount(c, dh+da, minlength=k)+5*(x[2*n:2*n+k]-prior_mu),
                     np.bincount(c, dh, minlength=k)+10*(x[2*n+k:]-prior_home)]
        return loss, grad
    opt = minimize(objective, x0, method='L-BFGS-B', jac=True,
                   bounds=[(-2., 2.)]*(2*n)+[(-1.5, 1.5)]*k+[(-.5, 1.)]*k, options={'maxiter': 400, 'ftol': 1e-10, 'gtol': 1e-5})
    th = opt.x
    lh = np.exp(th[2*n+c]+th[2*n+k+c]+th[h]+th[n+a]); la = np.exp(th[2*n+c]+th[a]+th[n+h])
    lo = max(-.25, float(np.max(np.r_[-1/lh, -1/la]))+1e-8); hi = min(.25, float(np.min(1/(lh*la)))-1e-8)

    def cl(rho):
        tau = np.ones(len(df)); m = (gh == 0) & (ga == 0); tau[m] = 1-(lh*la*rho)[m]
        m = (gh == 0) & (ga == 1); tau[m] = 1+(lh*rho)[m]
        m = (gh == 1) & (ga == 0); tau[m] = 1+(la*rho)[m]
        tau[(gh == 1) & (ga == 1)] = 1-rho
        return -float(np.dot(weights, np.log(tau)))+25*rho*rho
    rho = float(minimize_scalar(cl, bounds=(lo, hi), method='bounded').x) if lo < hi else 0.
    return dict(th=th, teams=teams, comps=comps, n=n, k=k, rho=rho)


def lambdas(m, home, away, comp):
    n, k, th = m['n'], m['k'], m['th']
    ci = m['comps'].get(comp)
    mu = th[2*n+ci] if ci is not None else float(np.mean(th[2*n:2*n+k]))
    adv = th[2*n+k+ci] if ci is not None else float(np.mean(th[2*n+k:]))
    s = lambda t, d=False: th[m['teams'][t]+(n if d else 0)] if t in m['teams'] else 0.
    return float(np.exp(mu+adv+s(home)+s(away, True))), float(np.exp(mu+s(away)+s(home, True)))


def temp(p, t):
    z = np.log(np.maximum(p, 1e-12))/t; z -= z.max(); q = np.exp(z); return q/q.sum()


def walk(results, start, end, w):
    fx = results[(results.date >= start) & (results.date < end)].sort_values(['date', 'match_id'])
    rows = []
    for month, g in fx.groupby(fx.date.dt.to_period('M')):
        cut = month.start_time
        m = fit(before(results, cut), cut, w)
        for r in g.itertuples():
            lh, la = lambdas(m, r.home_team, r.away_team, r.tournament)
            s = market_summary(lh, la, m['rho'])
            p = np.array([s['p_home_win'], s['p_draw'], s['p_away_win']])
            if r.tournament != 'UEFA Champions League':
                p = temp(p, TEMP)
            y = 0 if r.home_score > r.away_score else 1 if r.home_score == r.away_score else 2
            rows.append(dict(match_id=r.match_id, date=str(r.date.date()), comp=r.tournament, y=y, p=p.tolist(),
                             btts=s['btts'], o25=s['goal_lines']['2.5']['over'], lh=lh, la=la,
                             gh=int(r.home_score), ga=int(r.away_score)))
    return rows


def summary(rows):
    p = np.array([r['p'] for r in rows]); y = np.array([r['y'] for r in rows])
    ll = -np.log(np.maximum(p[np.arange(len(y)), y], 1e-12))
    bt = np.array([int(r['gh'] > 0 and r['ga'] > 0) for r in rows]); pb = np.clip([r['btts'] for r in rows], 1e-9, 1-1e-9)
    ov = np.array([int(r['gh']+r['ga'] > 2) for r in rows]); po = np.clip([r['o25'] for r in rows], 1e-9, 1-1e-9)
    bl = lambda yy, pp: float(-(yy*np.log(pp)+(1-yy)*np.log(1-pp)).mean())
    return dict(n=len(rows), logloss_1x2=float(ll.mean()), acc=float((p.argmax(1) == y).mean()),
                btts_ll=bl(bt, pb), btts_pred=float(np.mean(pb)), btts_obs=float(bt.mean()),
                o25_ll=bl(ov, po), goal_mae=float(np.mean([(abs(r['lh']-r['gh'])+abs(r['la']-r['ga']))/2 for r in rows])))


if __name__ == '__main__':
    from paths import ARTIFACT_DIR
    out = ARTIFACT_DIR / 'goal_shots_selection.json'
    stats = load_match_stats(); results = results_from_stats(stats)
    dom = results[results.tournament != 'UEFA Champions League'].copy()
    weights = [1.0, 0.7, 0.5, 0.3]
    res = {'protocol': __doc__, 'dataset_id': stats.attrs['dataset_id'], 'selection': {}, 'holdout': {}, 'current': {}, 'per_fixture': {}}
    for w in weights:
        t = time.time(); rows = walk(dom, '2024-08-01', '2025-03-01', w)
        res['selection'][str(w)] = summary(rows); print('sel', w, res['selection'][str(w)], round(time.time()-t), flush=True)
    best = min(weights, key=lambda w: res['selection'][str(w)]['logloss_1x2'])
    res['selected_weight'] = best
    for w in sorted({1.0, best}):
        h = walk(dom, '2025-08-01', '2026-07-01', w); cur = walk(results, '2026-08-01', '2026-10-28', w)
        res['holdout'][str(w)] = summary(h); res['current'][str(w)] = summary(cur)
        res['per_fixture'][str(w)] = {'holdout': h, 'current': cur}
        print('hold', w, res['holdout'][str(w)], '\ncur', w, res['current'][str(w)], flush=True)
    if best != 1.0:
        def bl(y, p): p = min(max(p, 1e-9), 1-1e-9); return -(y*np.log(p)+(1-y)*np.log(1-p))
        loss = {'1x2': lambda x: -np.log(x['p'][x['y']]), 'btts': lambda x: bl(int(x['gh'] > 0 and x['ga'] > 0), x['btts']),
                'over25': lambda x: bl(int(x['gh']+x['ga'] > 2), x['o25'])}
        res['paired_deltas'] = {}
        for per in ['holdout', 'current']:
            A = res['per_fixture'][str(best)][per]; B = res['per_fixture']['1.0'][per]; res['paired_deltas'][per] = {}
            for name, f in loss.items():
                d = np.array([f(x)-f(y) for x, y in zip(A, B)]); rng = np.random.default_rng(1)
                bs = [rng.choice(d, len(d)).mean() for _ in range(3000)]
                res['paired_deltas'][per][name] = {'mean': float(d.mean()), 'ci95': np.quantile(bs, [.025, .975]).tolist()}
        a = np.array([-np.log(r['p'][r['y']]) for r in res['per_fixture'][str(best)]['holdout']])
        b = np.array([-np.log(r['p'][r['y']]) for r in res['per_fixture']['1.0']['holdout']])
        d = a-b; rng = np.random.default_rng(42)
        bs = [rng.choice(d, len(d)).mean() for _ in range(2000)]
        res['paired_holdout_delta'] = {'mean': float(d.mean()), 'ci95': np.quantile(bs, [.025, .975]).tolist()}
        print('delta', res['paired_holdout_delta'])
    res.pop('per_fixture')  # summaries + paired deltas only; rerun to reproduce fixtures
    out.write_text(json.dumps(res, indent=1), encoding='utf-8')

"""Compare fijas selection rules on the walk-forward candidate cache (backtest_fijas.py).

Design period: 2025-09..2026-05.  Holdout: 2026-08..2026-10 (never used to choose rules).
Odds are the model's own fair odds (1/p); `yield_margin` applies a typical 6% bookmaker
margin to them.  This is a proxy for price quality, not a profitability claim.
"""
import glob, json, os, sys
from collections import defaultdict
import numpy as np
from goal_model import score_distribution
from recommendations import outcome_mask, stance, PRIMARY_MARKETS, COUNT_KINDS

BT = os.environ.get('FD_BACKTEST_DIR', '/root/bt')


def load():
    rows = []
    for p in sorted(glob.glob(f'{BT}/candidates_*.json')):rows += json.load(open(p))
    return rows


def coherent(c, chosen, matrix, h, a):
    m = outcome_mask(c, h, a)
    for o in chosen:
        n = outcome_mask(o, h, a)
        if m is not None and n is not None:
            pa, pb, pab = matrix[m].sum(), matrix[n].sum(), matrix[m & n].sum()
            if pab < 1e-6 or pab - pa * pb < -.01:return False
            continue
        s, t = stance(c, matrix), stance(o, matrix)
        if any(x * y < 0 for x, y in zip(s, t)):return False
    return True


def supported_old(c):
    ctx = c['ctx']
    return c['ev_n'] >= 5 and all(x[1] >= 3 and x[0] > x[1] / 2 for x in ctx) and c['gap'] <= .30 and 1 / c['p'] >= 1.18


def recent_ok(c):return all(x[3] >= 3 and x[2] >= 2 for x in c['ctx'])


def pattern(c):
    """Share of each team's venue-specific recent matches where the selection held; min over teams."""
    return min((x[0] / x[1]) if x[1] else 0 for x in c['ctx'])


def full(c):return all(x[1] >= 5 and x[0] == x[1] for x in c['ctx'])


def trivial(c):
    """Markets that only pay bookmaker-minimum prices or are not offered as fijas."""
    if c['kind'] == 'goals' and c['scope'] in ('home', 'away') and c['side'] == 'under' and c['line'] >= 2.5:return True
    if c['kind'] == 'goals' and c['scope'] == 'total' and c['side'] == 'under' and c['line'] >= 4.5:return True
    if c['kind'] == 'handicap' and c['line'] is not None and c['line'] >= 2.5:return True
    if c['kind'] == 'result_goals' and c.get('direction') == 'under' and c['line'] >= 3.5 and c['side'] in ('1X', 'X2'):return False
    return False


OLD_LEVELS = [('Conservadora', .78, .88, .82), ('Normal', .63, .78, .70), ('Arriesgada', .50, .63, .59)]


def select_old(match):
    lam, rho = match['lam'], match['rho']; matrix = score_distribution(lam[0], lam[1], rho); h, a = np.indices(matrix.shape)
    used, chosen, out = set(), [], []
    for name, lo, hi, target in OLD_LEVELS:
        pool = [c for c in match['candidates'] if lo <= c['p'] < hi and c['kind'] not in used and supported_old(c) and (name != 'Conservadora' or recent_ok(c)) and coherent(c, chosen, matrix, h, a)]
        prim = [c for c in pool if c['kind'] in PRIMARY_MARKETS] or pool
        best = min(prim, key=lambda c: abs(c['p'] - target) + .30 * c['gap'] + .015 * (c['kind'] in COUNT_KINDS), default=None)
        out.append((name, best))
        if best:chosen.append(best);used.add(best['kind'])
    return out


def make_new(levels, min_pattern, prefer_full=True, exclude_trivial=True, primary_first=True, allow_counts=True):
    def select(match):
        lam, rho = match['lam'], match['rho']; matrix = score_distribution(lam[0], lam[1], rho); h, a = np.indices(matrix.shape)
        used, chosen, out = set(), [], []
        for (name, omin, omax), mp in zip(levels, min_pattern):
            pool = []
            for c in match['candidates']:
                odds = 1 / c['p']
                if not (omin <= odds < omax) or c['kind'] in used or c['kind'] == 'cards':continue
                if exclude_trivial and trivial(c):continue
                if not allow_counts and c['kind'] in COUNT_KINDS:continue
                if c['ev_n'] < 5 or any(x[1] < 4 for x in c['ctx']) or pattern(c) < mp:continue
                if not coherent(c, chosen, matrix, h, a):continue
                pool.append(c)
            if primary_first:
                prim = [c for c in pool if c['kind'] in PRIMARY_MARKETS]
                pool = prim or pool
            key = lambda c: (-(full(c) if prefer_full else 0), -pattern(c), -(c['ev_hits'] / c['ev_n'] - c['p']), c['p'])
            best = min(pool, key=key, default=None)
            out.append((name, best))
            if best:chosen.append(best);used.add(best['kind'])
        return out
    return select


def evaluate(rows, select):
    agg = defaultdict(lambda: {'n': 0, 'won': 0, 'odds': 0., 'ret': 0., 'p': 0.})
    matches_with = 0
    for m in rows:
        picks = select(m)
        if any(p for _, p in picks):matches_with += 1
        for name, c in picks:
            if not c:continue
            s = agg[name]; o = 1 / c['p']; s['n'] += 1; s['won'] += c['hit']; s['odds'] += o; s['p'] += c['p']
            s['ret'] += (o * .94 if c['hit'] else 0) - 1
    res = {k: {'n': v['n'], 'acierto': round(v['won'] / v['n'], 3) if v['n'] else None, 'p_modelo': round(v['p'] / v['n'], 3) if v['n'] else None,
               'cuota_media': round(v['odds'] / v['n'], 2) if v['n'] else None, 'yield_margin': round(v['ret'] / v['n'], 3) if v['n'] else None} for k, v in agg.items()}
    res['partidos_con_fijas'] = matches_with
    return res


if __name__ == '__main__':
    rows = load()
    design = [r for r in rows if r['date'] < '2026-07-01']; hold = [r for r in rows if r['date'] >= '2026-07-01']
    print('partidos', len(design), len(hold))
    variants = {'actual_v6': select_old}
    for tag, levels, mp in [
        ('A_cuotas', [('Conservadora', 1.30, 1.60), ('Normal', 1.60, 2.00), ('Arriesgada', 2.00, 3.20)], [.8, .6, .6]),
        ('B_cuotas_patron', [('Conservadora', 1.30, 1.60), ('Normal', 1.60, 2.00), ('Arriesgada', 2.00, 3.20)], [1.0, .8, .6]),
        ('C_cuotas_patron_full', [('Conservadora', 1.30, 1.60), ('Normal', 1.60, 2.00), ('Arriesgada', 2.00, 3.20)], [1.0, 1.0, .8]),
        ('D_bajo', [('Conservadora', 1.25, 1.50), ('Normal', 1.50, 1.90), ('Arriesgada', 1.90, 3.00)], [1.0, .8, .6]),
    ]:
        variants[tag] = make_new(levels, mp)
    for name, f in variants.items():
        print(name, 'DISEÑO', json.dumps(evaluate(design, f), ensure_ascii=False))
        print(name, 'HOLDOUT', json.dumps(evaluate(hold, f), ensure_ascii=False))

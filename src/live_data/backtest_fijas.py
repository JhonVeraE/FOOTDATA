"""Walk-forward backtest of the fijas shortlist (FOOTDATA).

For every domestic league match in the requested months, the goal model and every
descriptive input are frozen at the first day of that month (strictly earlier
results only).  All candidate markets are generated exactly as for publication,
then settled against the verified final statistics.  The cache lets selection
rules be compared without recomputing reports.  No market odds are invented:
`fair_odds` is the model's own 1/p and is labelled as such.
"""
import argparse, json, time
from pathlib import Path
import numpy as np
import pandas as pd
from data_store import load_match_stats, results_from_stats, before
from full_report import build_full_match_report, model_settings
from goal_model import AttackDefenceModel, ModelConfig, score_distribution
from league_core import build_elo_ratings
from count_model import snapshot, selected_count_settings
from recommendations import historical_context, candidates, event_values
from paths import ARTIFACT_DIR

LEAGUES = ['La Liga', 'Premier League', 'Bundesliga', 'Serie A', 'Ligue 1']
import os
OUT = Path(os.environ.get('FD_BACKTEST_DIR', ARTIFACT_DIR / 'backtest'))
METRICS = ['goals', 'shots', 'sot', 'fouls', 'corners']


def settle(c, row):
    metric = c['kind'] if c['kind'] in METRICS else 'goals'
    if pd.isna(row.get(metric + '_for')) or pd.isna(row.get(metric + '_against')):return None
    if c['kind'] == 'cards':return None
    return bool(event_values(pd.DataFrame([row]), c, True)[0])


def month_cache(stats, start, first=0, count=None):
    cut = pd.Timestamp(start); end = cut + pd.offsets.MonthBegin(1)
    settings = model_settings(cut)
    model = AttackDefenceModel(ModelConfig(**settings['config'])).fit(results_from_stats(stats), cut)
    past = before(stats, cut); sel = selected_count_settings(); counts = {}
    if sel and cut >= pd.Timestamp(sel['active_from']):
        halves = sorted({v['config']['half_life_matches'] for v in sel['metrics'].values() if v['promoted']})
        for lg in LEAGUES:counts[lg] = snapshot(past[past.league == lg], cut, halves)
    ctx = {'past': past, 'cutoff': cut, 'elo': build_elo_ratings(results_from_stats(past)), 'counts': counts}
    games = stats[(stats.date >= cut) & (stats.date < end) & stats.is_home & stats.league.isin(LEAGUES)].sort_values(['date', 'match_id'])
    games = games.iloc[first:first + count] if count else games.iloc[first:]
    rows = []
    for _, g in games.iterrows():
        rep = build_full_match_report(stats, g.team, g.opponent, competition=g.league, fecha=str(g.date.date()), cutoff=cut, model=model, batch_context=ctx)
        if 'error' in rep:continue
        rep.update(fixture_id=g.match_id, kickoff_utc=f'{g.date.date()}T15:00:00+00:00', generated_at=cut.isoformat())
        contexts = historical_context(stats, rep)
        disp = stats[(stats.date < cut) & (stats.date >= cut - pd.Timedelta(days=365)) & (stats.league == g.league)]
        opts = candidates(rep, contexts, disp, None, cut, None, None)
        actual = {k: g[k] for k in g.index if k.endswith('_for') or k.endswith('_against')}
        out = []
        for c in opts:
            hit = settle(c, actual)
            if hit is None:continue
            ev = c['evidence']
            out.append({'id': c['id'], 'kind': c['kind'], 'scope': c['scope'], 'side': c['side'], 'line': c['line'], 'direction': c.get('direction'),
                        'label': c['label'], 'p': round(c['probability'], 4), 'hit': hit, 'ev_hits': ev['hits'], 'ev_n': ev['matches'],
                        'ctx': [[v['hits'], v['matches'], v['recent_hits'], v['recent_matches'], v['current_hit_streak']] for v in ev['contexts']],
                        'gap': round(c['support_gap'], 4)})
        rows.append({'match_id': g.match_id, 'date': str(g.date.date()), 'league': g.league, 'home': g.team, 'away': g.opponent,
                     'score': [int(g.goals_for), int(g.goals_against)], 'lam': [rep['lam_home'], rep['lam_away']], 'rho': rep['model']['rho'],
                     'sample': rep.get('quality', {}).get('effective_sample_min', 0), 'candidates': out})
    return rows


def main(month, first=0, count=None):
    OUT.mkdir(parents=True, exist_ok=True); stats = load_match_stats()
    path = OUT / f'candidates_{month}_{first:04d}.json'
    t = time.time(); rows = month_cache(stats, month + '-01', first, count)
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    print(month, first, len(rows), 'partidos', round(time.time() - t), 's', flush=True)
    return len(rows)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('month'); p.add_argument('--first', type=int, default=0); p.add_argument('--count', type=int)
    a = p.parse_args(); main(a.month, a.first, a.count)

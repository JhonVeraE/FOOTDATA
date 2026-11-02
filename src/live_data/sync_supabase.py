"""Upload match results, statistics and settled fijas to the private Supabase tables.

Needs SUPABASE_SECRET_KEY (environment or .env).  The key never goes to the web:
the browser only reads these tables as an administrator (RLS in supabase_results.sql).
Failures are reported and never interrupt the daily pipeline.
"""
import argparse, json, math
import pandas as pd
import requests
from data_store import load_match_stats, canonical_team
from paths import ARTIFACT_DIR, DATA_DIR
from settings import secret

URL = 'https://mexmotdyzrzqesczhpjv.supabase.co'
METRICS = ['shots', 'sot', 'corners', 'fouls', 'cards']


def clean(v):
    if v is None:return None
    if isinstance(v, float) and math.isnan(v):return None
    if hasattr(v, 'item'):v = v.item()
    return int(v) if isinstance(v, float) and v.is_integer() else v


def upsert(table, rows, key, conflict, batch=500):
    headers = {'apikey': key, 'Content-Type': 'application/json', 'Prefer': 'resolution=merge-duplicates,return=minimal'}
    for i in range(0, len(rows), batch):
        r = requests.post(f'{URL}/rest/v1/{table}?on_conflict={conflict}', headers=headers, data=json.dumps(rows[i:i + batch], ensure_ascii=False, default=str), timeout=60)
        if r.status_code >= 300:raise RuntimeError(f'{table}: HTTP {r.status_code} {r.text[:300]}')
    return len(rows)


def fixture_map():
    p = DATA_DIR / 'matches_footballdata.csv'
    if not p.exists():return {}
    cal = pd.read_csv(p, dtype={'match_id': str})
    return {(str(r.date)[:10], canonical_team(r.home_team), canonical_team(r.away_team)): r.match_id for r in cal.itertuples()}


def match_rows(since=None):
    stats = load_match_stats(); fx = fixture_map()
    home = stats[stats.is_home]
    if since:home = home[home.date >= pd.Timestamp(since)]
    rows = []
    for r in home.itertuples():
        day = str(r.date.date())
        rows.append({'match_id': r.match_id, 'fixture_id': fx.get((day, r.team, r.opponent)), 'date': day, 'league': r.league,
                     'season': clean(getattr(r, 'season', None)), 'home': r.team, 'away': r.opponent,
                     'home_score': clean(r.goals_for), 'away_score': clean(r.goals_against),
                     'stats': {m: [clean(getattr(r, f'{m}_for')), clean(getattr(r, f'{m}_against'))] for m in METRICS},
                     'source': str(r.source)})
    return rows


def review_rows(since=None):
    forecasts, picks, days = {}, [], []
    base = ARTIFACT_DIR / 'daily_reviews'
    if not base.exists():return forecasts, picks, days
    for d in sorted(base.iterdir()):
        if not d.is_dir() or (since and d.name < since):continue
        rv = d / 'review.json'; rr = d / 'recommendation_review.json'
        if rv.exists():
            review = json.loads(rv.read_text(encoding='utf-8'))
            for m in review.get('matches', []):
                forecasts[str(m['fixture_id'])] = {k: m.get(k) for k in ['probabilities', 'predicted_score', 'actual_score', 'hit_1x2', 'hit_exact', 'btts_probability', 'hit_btts', 'log_loss', 'goal_lines', 'kickoff_utc', 'source_url']}
        if rr.exists():
            rec = json.loads(rr.read_text(encoding='utf-8'))
            for t in rec.get('tiers', []):
                picks.append({'date': rec['date'], 'fixture_id': str(t['fixture_id']), 'tier': t['tier'], 'selection_id': t['selection_id'], 'match_label': t.get('match'),
                              'market': t.get('market'), 'label': t.get('label'), 'probability': t.get('probability'),
                              'status': t['status'] if t['status'] in ('won', 'lost', 'unverified', 'pending') else 'unverified',
                              'metric': t.get('actual_metric'), 'actual_home': t.get('actual_home'), 'actual_away': t.get('actual_away'), 'reviewed_at': rec.get('reviewed_at')})
            days.append({'date': rec['date'], 'reviewed_at': rec.get('reviewed_at'),
                         'summary': {k: rec.get(k) for k in ['tier_summary', 'unique_summary', 'by_tier', 'parlays', 'analysis']}})
    return forecasts, picks, days


MARKER = ARTIFACT_DIR / 'auto' / 'supabase_sync.json'


def main(since=None, dry=False, full=False):
    key = secret('SUPABASE_SECRET_KEY')
    if since is None and not full and MARKER.exists():
        # After the first complete upload only the last three weeks change.
        since = (pd.Timestamp.now(tz='America/Lima') - pd.Timedelta(days=21)).strftime('%Y-%m-%d')
    rows = match_rows(since); forecasts, picks, days = review_rows(since)
    by_fixture = {r['fixture_id']: r for r in rows if r['fixture_id']}
    for fid, f in forecasts.items():
        if fid in by_fixture:by_fixture[fid]['forecast'] = f;by_fixture[fid]['source_url'] = f.get('source_url')
    for r in rows:r.setdefault('forecast', None);r.setdefault('source_url', None)
    report = {'matches': len(rows), 'forecasts': sum(1 for r in rows if r['forecast']), 'picks': len(picks), 'days': len(days)}
    if dry or not key:
        report['status'] = 'dry_run' if dry else 'skipped_no_key'
        print(json.dumps(report, ensure_ascii=False));return report
    upsert('match_results', rows, key, 'match_id')
    upsert('pick_results', picks, key, 'date,fixture_id,tier,selection_id')
    upsert('daily_reviews', days, key, 'date')
    report['status'] = 'synced'; report['since'] = since
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(json.dumps({**report, 'at': pd.Timestamp.now(tz='UTC').isoformat()}, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False)); return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--since'); p.add_argument('--dry-run', action='store_true'); p.add_argument('--full', action='store_true'); a = p.parse_args(); main(a.since, a.dry_run, a.full)

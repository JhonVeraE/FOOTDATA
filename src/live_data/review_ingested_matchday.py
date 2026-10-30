"""Evaluate saved pre-match forecasts using validated ESPN ingestion records."""
import argparse, hashlib, json, math
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
from paths import ARTIFACT_DIR, WEB_DIR
from review_matchday import METRICS, save, outcome
from review_recommendations import main as review_picks


def main(capture_dir, date, output=None):
    capture = Path(capture_dir)
    archive = ARTIFACT_DIR / 'daily_reviews' / date
    paths = [archive / 'ingestion.json', archive / 'domestic' / 'ingestion.json']
    ingestions = [json.loads(path.read_text(encoding='utf-8')) for path in paths if path.exists()]
    records = [r for ingestion in ingestions for r in ingestion['matches']]
    deferred = [r for ingestion in ingestions for r in ingestion.get('deferred', [])]
    pending = [r for ingestion in ingestions for r in ingestion.get('pending', [])]
    # Brought forward: played and settled on an earlier Lima date; excluded here, never re-settled.
    advanced = [r for ingestion in ingestions for r in ingestion.get('advanced', [])]
    frozen = json.loads((capture / 'predictions_before_results.json').read_text(encoding='utf-8'))
    record_ids = {r['fixture_id'] for r in records}
    forecasts = {str(m['fixture_id']): m for m in frozen['matches']
                 if m['fecha'] == date or str(m['fixture_id']) in record_ids}
    deferred_ids = {r['fixture_id'] for r in deferred}
    pending_ids = {r['fixture_id'] for r in pending}
    advanced_ids = {r['fixture_id'] for r in advanced}
    if (len(records) != len(record_ids) or len(deferred) != len(deferred_ids)
            or len(pending)!=len(pending_ids) or record_ids & deferred_ids
            or (record_ids|deferred_ids)&pending_ids
            or advanced_ids & (record_ids | deferred_ids | pending_ids)
            or set(forecasts) != record_ids | deferred_ids | pending_ids | advanced_ids):
        raise ValueError('Incomplete or duplicate verified matchday')
    for r in pending:
        m=forecasts[r['fixture_id']]
        if ((r['home'],r['away'])!=(m['local'],m['visitante']) or r['date']!=date or not r.get('source_url')):
            raise ValueError('Invalid pending fixture')
    for r in advanced:
        m = forecasts[r['fixture_id']]
        if ((r['home'], r['away']) != (m['local'], m['visitante']) or not r.get('source_url')
                or pd.Timestamp(r['settled_on']) >= pd.Timestamp(date)):
            raise ValueError('Invalid brought-forward fixture')
    for r in deferred:
        m = forecasts[r['fixture_id']]
        if ((r['home'], r['away']) != (m['local'], m['visitante'])
                or not r.get('source_url') or pd.Timestamp(r['new_date']) <= pd.Timestamp(date)):
            raise ValueError('Invalid documented postponement')
    if not records:
        if forecasts:raise ValueError('No final matches available to evaluate')
        result = {'date':date,'summary':{'matches':0},'matches':[],
                  'reviewed_at':datetime.now(timezone.utc).isoformat(),
                  'note':'No hubo partidos de las cinco ligas o Champions en esta fecha.'}
        save(archive/'review.json',result);save(WEB_DIR/'data'/f'review_{date}.json',result)
        print(json.dumps(result,ensure_ascii=False));return result
    rows = []
    for r in records:
        m = forecasts[r['fixture_id']]
        if pd.Timestamp(m['generated_at']) >= pd.Timestamp(m['kickoff_utc']):
            raise ValueError('Forecast is not pre-match')
        if (r['home'], r['away']) != (m['local'], m['visitante']):
            raise ValueError('Wrong forecast identity')
        metrics = r['metrics']; goals = metrics['goals']
        p = [m[k] / 100 for k in ['p_home', 'p_draw', 'p_away']]
        actual = outcome(*goals); predicted = max(range(3), key=lambda i: p[i])
        statistics = []
        for key in METRICS:
            forecast = [m['cruces'][key]['home'], m['cruces'][key]['away']]
            interval = m.get('count_markets', {}).get(key, {}).get('interval_90')
            total = sum(metrics[key])
            statistics.append({'metric': key, 'forecast': forecast, 'actual': metrics[key],
                'predicted_total': sum(forecast), 'actual_total': total,
                'absolute_error_total': abs(total - sum(forecast)), 'interval_90': interval,
                'inside_interval': interval[0] <= total <= interval[1] if interval else None})
        rows.append({'fixture_id': r['fixture_id'], 'date': date, 'league': r['league'],
            'home': r['home'], 'away': r['away'], 'generated_at': m['generated_at'],
            'kickoff_utc': r['kickoff_utc'], 'forecast_original_date':m['fecha'],
            'forecast_original_kickoff_utc':m['kickoff_utc'],
            'schedule_change':r.get('schedule_change'), 'probabilities': p, 'actual_goals': goals,
            'actual_outcome': actual, 'predicted_outcome': predicted, 'hit_1x2': predicted == actual,
            'predicted_score': m['marcador_top1'][0], 'actual_score': f'{goals[0]}-{goals[1]}',
            'hit_exact': m['marcador_top1'][0] == f'{goals[0]}-{goals[1]}',
            'btts_probability': m['btts']/100, 'hit_btts': (m['btts'] >= 50) == all(goals),
            'brier': sum((p[i] - int(i == actual))**2 for i in range(3)),
            'log_loss': -math.log(max(p[actual], 1e-12)),
            'goal_lines': [{'line': float(line), 'hit': (prob['over'] >= .5) == (sum(goals) > float(line))}
                           for line, prob in m['goal_lines'].items()],
            'statistics': statistics, 'source_url': r['source_url']})
    summary = {'matches': len(rows), **{key: sum(r[field] for r in rows)
        for key, field in [('hits_1x2', 'hit_1x2'), ('hits_exact', 'hit_exact'), ('hits_btts', 'hit_btts')]},
        'mean_absolute_errors': {key: sum(next(s for s in r['statistics'] if s['metric'] == key)['absolute_error_total']
                                        for r in rows)/len(rows) for key in METRICS}}
    review = {'date': date, 'reviewed_at': datetime.now(timezone.utc).isoformat(), 'summary': summary,
              'matches': rows, 'deferred': deferred, 'pending':pending, 'advanced':advanced,
              'original_predictions_sha256': hashlib.sha256((capture/'predictions_before_results.json').read_bytes()).hexdigest()}
    for path in [capture/'review.json', archive/'review.json', WEB_DIR/'data'/f'review_{date}.json']:
        save(path, review)
    result = review_picks(capture, date, output)
    print(json.dumps({'forecast_summary': summary, 'parlays': result['parlays']}, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--capture-dir', required=True)
    p.add_argument('--date', required=True); p.add_argument('--output')
    a = p.parse_args(); main(a.capture_dir, a.date, a.output)

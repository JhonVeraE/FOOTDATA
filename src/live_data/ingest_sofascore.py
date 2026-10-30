"""Import verified Sofascore full-match statistics (period ALL) for one Lima date.

Input: a captures JSON (saved under data/artifacts/sofascore/<date>/captures.json) with,
per match: fixture_id, sofascore_event_id, kickoff_utc, status, score, statistics
(shots, sot, fouls, corners, yellow, red), incidents summary and an independent score
check (ESPN). Rules: final status only, all six metrics present, independent score must
match, team identity comes from the frozen forecast / calendar (no fuzzy matching),
cards = yellow + red from the statistics table (base definition), red omitted by the
table counts as 0 only when the incidents list has no red card.
Reuses daily_update for freezing, calendar, settlement files and post-processing.
"""
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from data_store import validate_stats, season_for
from paths import ARTIFACT_DIR, DATA_DIR, WEB_DIR
from daily_update import (freeze_forecasts, update_calendar, build_ingestion, rows_for, existing_rows,
                          dump, read, CHAMPIONS)

METRICS = ['goals', 'shots', 'sot', 'fouls', 'corners', 'cards']


def record_from_capture(c, day, calendar, names):
    fid = str(c['fixture_id'])
    cal = calendar[calendar.match_id.astype(str) == fid]
    if len(cal) != 1:raise ValueError(f'{fid}: calendar row not unique')
    row = cal.iloc[0]
    if c['status'] != 'finished':raise ValueError(f'{fid}: not finished')
    s = c['statistics']
    for k in ['shots', 'sot', 'fouls', 'corners']:
        if s.get(k) is None or None in s[k]:raise ValueError(f'{fid}: missing {k}')
    yellow = s.get('yellow') or [0, 0]
    if s.get('yellow') is None and c.get('incident_cards_players', 0) != 0:raise ValueError(f'{fid}: yellow missing but cards in incidents')
    red = s.get('red') or [0, 0]
    if s.get('red') is None and c.get('incident_red_cards', 0) != 0:raise ValueError(f'{fid}: red missing but red in incidents')
    goals = list(c['score'])
    if c.get('independent_score') != goals:raise ValueError(f'{fid}: independent score mismatch')
    home, away = names[fid]
    league = row.competition
    metrics = {'goals': goals, 'shots': s['shots'], 'sot': s['sot'], 'fouls': s['fouls'], 'corners': s['corners'],
               'cards': [yellow[0] + red[0], yellow[1] + red[1]]}
    for k in METRICS:
        if any(int(v) != v or v < 0 for v in metrics[k]):raise ValueError(f'{fid}: invalid {k}')
    if metrics['sot'][0] > metrics['shots'][0] or metrics['sot'][1] > metrics['shots'][1]:raise ValueError(f'{fid}: sot > shots')
    url = f"https://www.sofascore.com/football/match/{c['slug']}/{c['custom_id']}#id:{c['sofascore_event_id']},tab:statistics"
    return {'sofascore_event_id': str(c['sofascore_event_id']), 'espn_event_id': c.get('espn_event_id'),
            'kickoff_utc': c['kickoff_utc'], 'home': home, 'away': away, 'metrics': metrics, 'yellow': yellow, 'red': red,
            'source_url': url, 'match_id': f'{league}_{season_for(day)}_sofascore_{c["sofascore_event_id"]}', 'fixture_id': fid,
            'date': day, 'round': int(row.matchday) if pd.notna(row.matchday) else None, 'league': league, 'provider': 'Sofascore',
            'notes': c.get('notes'),
            'score_verification': {'fixture_id': fid, 'date': day, 'home': home, 'away': away, 'goals': goals,
                                   'status': 'verified', 'source': c.get('independent_source', 'ESPN'),
                                   'source_url': c.get('independent_url')}}


def import_rows(recs, data_dir=DATA_DIR):
    added = []
    for dataset, group in [('match_stats_actualseason', [r for r in recs if r['league'] != CHAMPIONS]),
                           ('match_stats_champions_actualseason', [r for r in recs if r['league'] == CHAMPIONS])]:
        if not group:continue
        csv_path = data_dir/f'{dataset}.csv';manifest_path = data_dir/f'{dataset}.sources.json'
        old = pd.read_csv(csv_path);fresh = []
        for rec in group:
            if len(existing_rows(old, rec)):continue  # idempotent: never add twice
            fresh.extend(rows_for(rec));added.append(rec)
        if not fresh:continue
        combined = pd.concat([old, pd.DataFrame(fresh)], ignore_index=True)[old.columns]
        check = combined.copy();check['date'] = pd.to_datetime(check.date)
        check['is_home'] = check.is_home.astype(str).str.lower().map({'true': True, 'false': False})
        validate_stats(check)
        if combined.duplicated(['date', 'league', 'team', 'opponent']).any():raise ValueError('Duplicate natural fixture')
        manifest = read(manifest_path)
        for rec in [r for r in added if r in group]:
            manifest['sources'].append({'match_id': rec['match_id'], 'fixture_id': rec['fixture_id'],
                'sofascore_event_id': rec['sofascore_event_id'], 'espn_event_id': rec['espn_event_id'], 'date': rec['date'],
                'league': rec['league'], 'round': rec['round'], 'home': rec['home'], 'away': rec['away'],
                'yellow_home': rec['yellow'][0], 'yellow_away': rec['yellow'][1], 'red_home': rec['red'][0], 'red_away': rec['red'][1],
                'url': rec['source_url'], 'provider': 'Sofascore', 'score_verification': 'ESPN', 'imported_by': 'ingest_sofascore',
                **({'notes': rec['notes']} if rec.get('notes') else {})})
        manifest.update(as_of=max(str(combined.date.max()), str(manifest.get('as_of', ''))),
                        matches=int(combined.match_id.nunique()), rows=len(combined))
        tmp = csv_path.with_suffix('.csv.tmp');combined.to_csv(tmp, index=False, lineterminator='\r\n');tmp.replace(csv_path)
        dump(manifest_path, manifest)
    return added


def main(captures_path, day, post=True):
    captures = read(Path(captures_path))
    report = {'date': day, 'run_at': datetime.now(timezone.utc).isoformat(), 'frozen': freeze_forecasts(day)}
    calendar = pd.read_csv(DATA_DIR/'matches_footballdata.csv')
    frozen = read(ARTIFACT_DIR/'daily_reviews'/day/'predictions_before_results.json')
    names = {str(m['fixture_id']): (m['local'], m['visitante']) for m in frozen['matches']}
    recs = [record_from_capture(c, day, calendar, names) for c in captures['matches']]
    added = import_rows(recs)
    report['added_matches'] = [r['match_id'] for r in added]
    changed, issues = update_calendar(recs, [])
    report.update(calendar_changed=changed, calendar_issues=issues)
    calendar = pd.read_csv(DATA_DIR/'matches_footballdata.csv')
    record, status = build_ingestion(day, {r['fixture_id']: r for r in recs}, {}, calendar)
    report['ingestion'] = status
    if record is not None:
        record['provider'] = 'Sofascore full-match statistics (ALL); scores independently checked with ESPN'
        record['added_rows_this_run'] = 2 * len(added)
        dump(ARTIFACT_DIR/'daily_reviews'/day/'ingestion.json', record);dump(WEB_DIR/'data'/f'actuals_{day}.json', record)
    if post:
        from review_ingested_matchday import main as review
        out = review(ARTIFACT_DIR/'daily_reviews'/day, day)
        report['review'] = {'tier_summary': out['tier_summary'], 'unique_summary': out['unique_summary']}
        from score_archive import main as score
        score()
        from build_team_dashboard import main as teams
        teams(refresh=False)
    dump(Path(captures_path).parent/'ingest_report.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser();p.add_argument('--captures', required=True);p.add_argument('--date', required=True)
    a = p.parse_args();main(a.captures, a.date)

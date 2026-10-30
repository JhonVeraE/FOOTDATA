"""Unattended daily update: ESPN finals -> verified rows -> settlement -> web.

Rules enforced here (see CONTEXTO_COMPLETO):
* Forecasts are frozen per Lima date from the append-only archive, choosing the
  latest publication generated before that date's first kickoff. Frozen files
  are never overwritten.
* Only STATUS_FULL_TIME events with every required boxscore count are imported.
  Anything else (in play, postponed, missing stat, unknown team, score
  disagreement, no calendar fixture) is reported as pending with a reason.
* A second source (football-data.org) must agree on the final score when it is
  reachable; if it is not, the record is flagged ``espn_only`` and the ESPN
  scoreboard score must equal the boxscore header score.
* Imports are idempotent: a match already present (same match_id, or same
  league/team/opponent within one day) is never appended again. If the stored
  values differ from ESPN (e.g. an earlier Sofascore capture) the stored row is
  kept and the difference is reported.
* Nulls never become zeros; two reciprocal rows per match; existing CSV
  contract and ``<League>_<season>_espn_<event>`` identifiers.
"""
import argparse, hashlib, json, os, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from data_store import canonical_team, season_for, today_local, validate_stats
from ingest_champions_matchday import parse_event, ESPN_NAMES
from ingest_verified_range import ESPN_ALIASES, LEAGUES
from paths import DATA_DIR, ARTIFACT_DIR, WEB_DIR
from settings import secret

LIMA = ZoneInfo('America/Lima')
FD_CODES = {'La Liga':'PD','Premier League':'PL','Bundesliga':'BL1','Serie A':'SA',
            'Ligue 1':'FL1','UEFA Champions League':'CL'}
CHAMPIONS = 'UEFA Champions League'
REQUIRED = ['totalShots','shotsOnTarget','foulsCommitted','wonCorners','yellowCards','redCards']
METRIC_COLS = [f'{m}_{s}' for m in ['goals','shots','sot','fouls','corners','cards'] for s in ['for','against']]
ESPN_STATUS = {'STATUS_SCHEDULED':'SCHEDULED','STATUS_FIRST_HALF':'IN_PLAY','STATUS_SECOND_HALF':'IN_PLAY',
               'STATUS_HALFTIME':'PAUSED','STATUS_IN_PROGRESS':'IN_PLAY','STATUS_POSTPONED':'POSTPONED',
               'STATUS_SUSPENDED':'SUSPENDED','STATUS_DELAYED':'SCHEDULED','STATUS_CANCELED':'CANCELLED',
               'STATUS_ABANDONED':'SUSPENDED'}
KEEP_SUMMARY = ['header','boxscore','gameInfo','format','meta']


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    tmp.replace(path)


def dump_raw(path, value):
    """Compact provider capture; rewritten only when the provider content changed."""
    data = json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    if path.exists() and path.read_text(encoding='utf-8') == data:return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp');tmp.write_text(data, encoding='utf-8');tmp.replace(path)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def team_name(name):
    name = ESPN_NAMES.get(name, name)
    return canonical_team(ESPN_ALIASES.get(name, name))


# ---------------------------------------------------------------- sources
class OnlineSource:
    """Public ESPN endpoints plus football-data.org when a key is configured."""
    def __init__(self, raw_dir, key=None):
        import requests
        self.session = requests.Session();self.session.headers['User-Agent'] = 'FOOTDATA/1.0'
        self.raw_dir = raw_dir;self.key = key;self.errors = []

    def _get(self, url, headers=None):
        for attempt in range(3):
            try:
                r = self.session.get(url, headers=headers or {}, timeout=30)
                if r.status_code == 429:time.sleep(20);continue
                r.raise_for_status();return r.json()
            except Exception as exc:  # network, HTTP or JSON error
                last = type(exc).__name__;time.sleep(2 * (attempt + 1))
        self.errors.append({'url': url.split('?')[0], 'error': last});return None

    def scoreboard(self, day, code):
        data = self._get(f'https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/scoreboard?dates={day.replace("-","")}&limit=100')
        if data is not None and data.get('events'):dump_raw(self.raw_dir/day/f'{code}_scoreboard.json', data)
        return data

    def summary(self, day, code, event_id):
        data = self._get(f'https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/summary?event={event_id}')
        if data is not None:
            full = json.dumps(data, ensure_ascii=False, sort_keys=True).encode('utf-8')
            kept = {k: data[k] for k in KEEP_SUMMARY if k in data}
            kept['_footdata'] = {'trimmed_from_full_response_sha256': hashlib.sha256(full).hexdigest(),
                                 'kept_sections': KEEP_SUMMARY,
                                 'url': f'https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/summary?event={event_id}'}
            dump_raw(self.raw_dir/day/f'espn_{event_id}.json', kept)
        return data

    def football_data(self, start, end):
        if not self.key:return None
        url = f'https://api.football-data.org/v4/matches?dateFrom={start}&dateTo={end}'
        data = self._get(url, {'X-Auth-Token': self.key})
        if data is not None:dump_raw(self.raw_dir/f'football_data_{start}_{end}.json', data)
        return data


class OfflineSource:
    """Saved captures laid out as <dir>/<date>/<code>_scoreboard.json and espn_<id>.json."""
    def __init__(self, source_dir):
        self.dir = Path(source_dir);self.errors = []

    def scoreboard(self, day, code):
        p = self.dir/day/f'{code}_scoreboard.json'
        return read(p) if p.exists() else None

    def summary(self, day, code, event_id):
        for p in [self.dir/day/f'espn_{event_id}.json', *self.dir.glob(f'*/espn_{event_id}.json')]:
            if p.exists():return read(p)
        return None

    def football_data(self, start, end):
        p = self.dir/'football_data_matches_range.json'
        if p.exists():return read(p)
        saved = sorted(self.dir.glob('football_data_*.json'))  # layout written by OnlineSource
        return read(saved[-1]) if saved else None


# ---------------------------------------------------------------- freezing
def freeze_forecasts(day, artifact_dir=ARTIFACT_DIR):
    """Freeze, once, the latest archived publication made before ``day``'s first kickoff."""
    target = artifact_dir/'daily_reviews'/day
    pred_path, fijas_path = target/'predictions_before_results.json', target/'fijas_before_results.json'
    if pred_path.exists() and fijas_path.exists():return 'already_frozen'
    best = None
    for path in sorted((artifact_dir/'prediction_archive').glob('*.json')):
        archive = read(path)
        games = [m for m in archive['matches'] if m['fecha'] == day]
        if not games:continue
        generated = pd.Timestamp(archive['run']['generated_at'])
        if generated >= min(pd.Timestamp(m['kickoff_utc']) for m in games):continue
        if best is None or generated > best[0]:best = (generated, path, archive)
    if best is None:return 'no_forecasts'
    generated, path, archive = best
    fijas = None
    for rpath in sorted((artifact_dir/'recommendation_archive').glob('*.json')):
        r = read(rpath)
        if (r.get('prediction_run_generated_at') == archive['run']['generated_at']
                and r.get('dataset_id') == archive['run']['dataset_id']):fijas = rpath
    if fijas is None:return 'missing_matching_fijas'
    target.mkdir(parents=True, exist_ok=True)
    if not pred_path.exists():pred_path.write_bytes(path.read_bytes())
    if not fijas_path.exists():fijas_path.write_bytes(fijas.read_bytes())
    return f'frozen_from:{path.name}'


# ---------------------------------------------------------------- parsing
def collect_events(source, days):
    """Unique events per competition, assigned to their Lima date."""
    events = {}
    probe = sorted(set(days) | {str((pd.Timestamp(days[-1]) + timedelta(days=1)).date())})
    for day in probe:
        for code, league in LEAGUES.items():
            board = source.scoreboard(day, code)
            for event in (board or {}).get('events', []):
                lima_day = str(pd.Timestamp(event['date']).tz_convert(LIMA).date())
                if lima_day in days:events[str(event['id'])] = (lima_day, code, league, event)
    return events


def provider_index(fd):
    if not fd:return {}
    return {str(m['id']): m for m in fd.get('matches', []) if m['competition']['code'] in FD_CODES.values()}


def find_fixture(calendar, league, home, away, day):
    c = calendar[(calendar.competition == league) & (calendar._home == home) & (calendar._away == away)]
    c = c[(pd.to_datetime(c.date) - pd.Timestamp(day)).abs() <= pd.Timedelta(days=3)]
    return c.iloc[0] if len(c) == 1 else None


def evaluate_event(lima_day, code, league, event, source, calendar, fd, known_teams):
    """Return ('final', record) or ('pending', info)."""
    comp = event['competitions'][0]
    sides = {c['homeAway']: c for c in comp['competitors']}
    info = {'espn_event_id': str(event['id']), 'date': lima_day, 'league': league,
            'kickoff_utc': event['date'], 'espn_status': event['status']['type']['name'],
            'source_url': (event.get('links') or [{}])[0].get('href')}
    try:home, away = team_name(sides['home']['team']['displayName']), team_name(sides['away']['team']['displayName'])
    except (KeyError, ValueError):return 'pending', {**info, 'reason': 'Identidad de equipos incompleta en ESPN.'}
    info.update(home=home, away=away)
    unknown = [t for t in (home, away) if t not in known_teams]
    fixture = find_fixture(calendar, league, home, away, lima_day)
    if fixture is not None:info['fixture_id'] = str(fixture.match_id)
    if unknown:return 'pending', {**info, 'reason': f'Equipo no reconocido: {", ".join(unknown)}. Añadir alias explícito.'}
    if fixture is None:return 'pending', {**info, 'reason': 'Sin partido equivalente en el calendario de football-data.'}
    status = event['status']['type']
    if not status.get('completed') or status.get('name') != 'STATUS_FULL_TIME':
        return 'pending', {**info, 'provider_status': ESPN_STATUS.get(status.get('name'), 'SCHEDULED' if not status.get('completed') else 'UNVERIFIED'),
                           'reason': 'Encuentro sin final reglamentario confirmado al corte de la consulta; no se liquida ni se añade marcador.'}
    detail = source.summary(lima_day, code, event['id'])
    if detail is None:return 'pending', {**info, 'reason': 'No se pudo descargar el boxscore final.'}
    try:
        stats = {x['homeAway']: {s['name'] for s in x['statistics']} for x in detail['boxscore']['teams']}
        missing = sorted({k for side in ('home', 'away') for k in REQUIRED if k not in stats.get(side, set())})
        if missing:return 'pending', {**info, 'reason': f'Boxscore incompleto: faltan {", ".join(missing)}.'}
        rec = parse_event(event, detail, lima_day)
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        return 'pending', {**info, 'reason': f'Boxscore no válido: {exc}'}
    rec['home'], rec['away'] = home, away
    board_goals = [int(float(sides['home']['score'])), int(float(sides['away']['score']))]
    if board_goals != rec['metrics']['goals']:
        return 'pending', {**info, 'reason': 'El marcador del scoreboard y del boxscore de ESPN no coinciden.'}
    fdm = fd.get(info['fixture_id']) if fd else None
    if fd and fdm is None:
        verification = {'status': 'espn_only', 'reason': 'football-data no devolvió el partido en el rango consultado.'}
    elif fdm is not None:
        if fdm['status'] != 'FINISHED':
            return 'pending', {**info, 'provider_status': fdm['status'],
                               'reason': 'La segunda fuente aún no confirma el final; se reintenta en la próxima ejecución.'}
        full = fdm['score']['fullTime']
        if [full['home'], full['away']] != rec['metrics']['goals']:
            return 'pending', {**info, 'reason': f'Marcador discrepante: ESPN {rec["metrics"]["goals"]} y football-data {[full["home"], full["away"]]}.'}
        verification = {'status': 'verified', 'source': 'football-data.org',
                        'source_url': f'https://api.football-data.org/v4/matches/{info["fixture_id"]}'}
    else:
        verification = {'status': 'espn_only', 'reason': 'unverified_second_source: football-data no disponible (sin clave o sin red).'}
    season = season_for(lima_day)
    rec.update(match_id=f'{league}_{season}_espn_{rec["espn_event_id"]}', fixture_id=info['fixture_id'],
               date=lima_day, league=league, round=int(fixture.matchday) if pd.notna(fixture.matchday) else None,
               provider='ESPN',
               score_verification={'fixture_id': info['fixture_id'], 'date': lima_day, 'home': home, 'away': away,
                                   'goals': rec['metrics']['goals'], **verification,
                                   'source_url': verification.get('source_url', rec['source_url'])})
    return 'final', rec


# ---------------------------------------------------------------- import
def rows_for(rec):
    out = []
    for side in [0, 1]:
        row = {'match_id': rec['match_id'], 'date': rec['date'], 'league': rec['league'], 'is_home': side == 0,
               'team': [rec['home'], rec['away']][side], 'opponent': [rec['home'], rec['away']][1 - side]}
        for metric, value in rec['metrics'].items():
            row[metric + '_for'] = value[side];row[metric + '_against'] = value[1 - side]
        out.append(row)
    return out


def existing_rows(frame, rec):
    same_id = frame[frame.match_id == rec['match_id']]
    if len(same_id):return same_id
    near = (pd.to_datetime(frame.date) - pd.Timestamp(rec['date'])).abs() <= pd.Timedelta(days=1)
    return frame[near & (frame.league == rec['league']) &
                 (((frame.team == rec['home']) & (frame.opponent == rec['away'])) |
                  ((frame.team == rec['away']) & (frame.opponent == rec['home'])))]


def import_finals(finals, data_dir=DATA_DIR, apply=True):
    """Append new verified finals; return (added, already_present, conflicts)."""
    added, present, conflicts = [], [], []
    for dataset, recs in [('match_stats_actualseason', [r for r in finals if r['league'] != CHAMPIONS]),
                          ('match_stats_champions_actualseason', [r for r in finals if r['league'] == CHAMPIONS])]:
        if not recs:continue
        csv_path = data_dir/f'{dataset}.csv';manifest_path = data_dir/f'{dataset}.sources.json'
        old = pd.read_csv(csv_path);fresh = []
        for rec in recs:
            prev = existing_rows(old, rec)
            if len(prev):
                home = prev[prev.team == rec['home']]
                stored = {c.rsplit('_', 1)[0]: [int(home.iloc[0][f'{c.rsplit("_",1)[0]}_for']),
                                                int(home.iloc[0][f'{c.rsplit("_",1)[0]}_against'])]
                          for c in METRIC_COLS} if len(home) == 1 and len(prev) == 2 else None
                if stored is None:
                    conflicts.append({'match_id': rec['match_id'], 'reason': 'Filas existentes incompletas o duplicadas; no se toca.'});continue
                diffs = {k: {'stored': stored[k], 'espn': rec['metrics'][k]} for k in rec['metrics'] if stored[k] != rec['metrics'][k]}
                rec['stored_match_id'] = str(prev.iloc[0].match_id)
                rec['metrics'] = stored  # the canonical base value is the one we settle with
                (conflicts if diffs else present).append({'match_id': rec['stored_match_id'], 'fixture_id': rec['fixture_id'],
                    **({'differences_vs_espn': diffs, 'reason': 'Valor almacenado (otra fuente) conservado; diferencia registrada.'} if diffs else {})})
                continue
            fresh.extend(rows_for(rec));added.append(rec)
        if not fresh:continue
        combined = pd.concat([old, pd.DataFrame(fresh)], ignore_index=True)[old.columns]
        check = combined.copy();check['date'] = pd.to_datetime(check.date)
        check['is_home'] = check.is_home.astype(str).str.lower().map({'true': True, 'false': False})
        validate_stats(check)
        if combined.duplicated(['date', 'league', 'team', 'opponent']).any():raise ValueError('Duplicate natural fixture')
        if not apply:continue
        manifest = read(manifest_path)
        for rec in [r for r in added if r in recs]:
            if any(s['match_id'] == rec['match_id'] for s in manifest['sources']):continue
            code = next(c for c, l in LEAGUES.items() if l == rec['league'])
            manifest['sources'].append({'match_id': rec['match_id'], 'fixture_id': rec['fixture_id'],
                'espn_event_id': rec['espn_event_id'], 'date': rec['date'], 'league': rec['league'], 'round': rec['round'],
                'home': rec['home'], 'away': rec['away'], 'yellow_home': rec['yellow'][0], 'yellow_away': rec['yellow'][1],
                'red_home': rec['red'][0], 'red_away': rec['red'][1], 'url': rec['source_url'], 'provider': 'ESPN',
                'statistics_endpoint': f'https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/summary?event={rec["espn_event_id"]}',
                'score_verification': rec['score_verification'].get('status'), 'imported_by': 'daily_update'})
        manifest.update(as_of=max(str(combined.date.max()), str(manifest.get('as_of', ''))),
                        matches=int(combined.match_id.nunique()), rows=len(combined), date_max=str(combined.date.max()))
        if 'coverage' in manifest:
            manifest['coverage'] = [{'league': name, 'matches': int(g.match_id.nunique()), 'rows': len(g),
                'round_counts': {str(k): sum(s.get('league') == name and s.get('round') == k for s in manifest['sources'])
                                 for k in sorted({s['round'] for s in manifest['sources'] if s.get('league') == name and s.get('round') is not None})}}
                for name, g in combined.groupby('league')]
        tmp = csv_path.with_suffix('.csv.tmp');combined.to_csv(tmp, index=False);tmp.replace(csv_path)
        dump(manifest_path, manifest)
    return added, present, conflicts


def update_calendar(finals, pendings, data_dir=DATA_DIR):
    path = data_dir/'matches_footballdata.csv';cal = pd.read_csv(path);changed = False;issues = []
    for rec in finals:
        mask = cal.match_id.astype(str).eq(rec['fixture_id'])
        if mask.sum() != 1:issues.append({'fixture_id': rec['fixture_id'], 'reason': 'Calendario sin fila única'});continue
        row = cal[mask].iloc[0];goals = rec['metrics']['goals']
        if row.status == 'FINISHED' and pd.notna(row.home_score) and [int(row.home_score), int(row.away_score)] != goals:
            issues.append({'fixture_id': rec['fixture_id'], 'reason': 'Calendario ya tenía otro marcador final; no se cambia.'});continue
        stamp = pd.Timestamp(rec['kickoff_utc']).tz_convert('UTC')
        new = ['FINISHED', float(goals[0]), float(goals[1]), str(stamp.date()), stamp.strftime('%H:%M')]
        old = [row.status, row.home_score, row.away_score, str(row.date), str(row.kickoff_time_utc)]
        if old != new:
            cal.loc[mask, ['status', 'home_score', 'away_score', 'date', 'kickoff_time_utc']] = new;changed = True
    for p in pendings:
        if 'fixture_id' not in p or p.get('provider_status') not in ('POSTPONED', 'SUSPENDED', 'CANCELLED'):continue
        mask = cal.match_id.astype(str).eq(p['fixture_id'])
        if mask.sum() == 1 and cal.loc[mask, 'status'].iloc[0] in ('SCHEDULED', 'TIMED'):
            cal.loc[mask, 'status'] = p['provider_status'];changed = True
    if changed:
        tmp = path.with_suffix('.csv.tmp');cal.to_csv(tmp, index=False);tmp.replace(path)
    return changed, issues


# ---------------------------------------------------------------- settlement
def comparable(record):
    """Ingestion content without volatile timestamps, used to avoid churn."""
    return json.dumps({k: record.get(k) for k in ['matches', 'deferred', 'pending', 'advanced']}, sort_keys=True, ensure_ascii=False)


def build_ingestion(day, finals_by_fixture, pendings_by_fixture, calendar, artifact_dir=ARTIFACT_DIR):
    archive = artifact_dir/'daily_reviews'/day
    frozen_path = archive/'predictions_before_results.json'
    if not frozen_path.exists():return None, 'sin pronósticos congelados'
    frozen = read(frozen_path)
    forecasts = {str(m['fixture_id']): m for m in frozen['matches'] if m['fecha'] == day}
    if not forecasts:return None, 'sin pronósticos para la fecha'
    path = archive/'ingestion.json'
    previous = read(path) if path.exists() else None
    kept = {r['fixture_id']: r for r in (previous or {}).get('matches', [])}
    old_pending = {r['fixture_id']: r for r in (previous or {}).get('pending', [])}
    old_deferred = {r['fixture_id']: r for r in (previous or {}).get('deferred', [])}
    matches, deferred, pending, advanced = [], [], [], []
    settled_before = {}
    for other in sorted((artifact_dir/'daily_reviews').glob('*/ingestion.json')):
        if other.parent.name >= day:continue
        for r in read(other).get('matches', []):settled_before[r['fixture_id']] = (other.parent.name, r)
    for fid, m in forecasts.items():
        if fid in kept:matches.append(kept[fid]);continue
        if fid in settled_before:
            on, prior = settled_before[fid]
            advanced.append({'fixture_id': fid, 'home': m['local'], 'away': m['visitante'], 'original_date': day,
                             'original_kickoff_utc': m['kickoff_utc'], 'settled_on': on, 'kickoff_utc': prior.get('kickoff_utc'),
                             'reason': f'Adelantado y jugado el {on}; se liquidó en esa fecha con las selecciones originales.',
                             'source_url': prior.get('source_url')})
            continue
        rec = finals_by_fixture.get(fid)
        cal = calendar[calendar.match_id.astype(str) == fid]
        if rec is not None:
            if rec['date'] == day:
                matches.append({k: v for k, v in rec.items() if k != 'additional_statistics'});continue
            if rec['date'] > day:
                deferred.append({'fixture_id': fid, 'home': m['local'], 'away': m['visitante'], 'original_date': day,
                                 'original_kickoff_utc': m['kickoff_utc'], 'new_date': rec['date'], 'new_kickoff_utc': rec['kickoff_utc'],
                                 'reason': f'Trasladado al {rec["date"]}; se evalúa en esa fecha.', 'source_url': rec['source_url']})
                continue
            advanced.append({'fixture_id': fid, 'home': m['local'], 'away': m['visitante'], 'original_date': day,
                             'original_kickoff_utc': m['kickoff_utc'], 'settled_on': rec['date'], 'kickoff_utc': rec['kickoff_utc'],
                             'reason': f'Adelantado y jugado el {rec["date"]}; se liquida en esa fecha.', 'source_url': rec['source_url']})
            continue
        if len(cal) == 1 and str(cal.iloc[0].date) > day and cal.iloc[0].status in ('SCHEDULED', 'TIMED'):
            deferred.append({'fixture_id': fid, 'home': m['local'], 'away': m['visitante'], 'original_date': day,
                             'original_kickoff_utc': m['kickoff_utc'], 'new_date': str(cal.iloc[0].date),
                             'new_kickoff_utc': f'{cal.iloc[0].date}T{cal.iloc[0].kickoff_time_utc}:00Z',
                             'reason': 'Reprogramado según el calendario del proveedor; no se liquida en esta fecha.',
                             'source_url': f'https://api.football-data.org/v4/matches/{fid}'})
            continue
        if fid in old_deferred:deferred.append(old_deferred[fid]);continue
        if fid in old_pending:pending.append(old_pending[fid]);continue  # unchanged state: no churn
        p = pendings_by_fixture.get(fid, {})
        pending.append({'fixture_id': fid, 'date': day, 'home': m['local'], 'away': m['visitante'],
                        'espn_event_id': p.get('espn_event_id'),
                        'provider_status': p.get('provider_status') or (cal.iloc[0].status if len(cal) == 1 else 'UNKNOWN'),
                        'reason': p.get('reason', 'Sin boxscore final verificado al corte de la consulta; no se liquida.'),
                        'source_url': p.get('source_url') or f'https://api.football-data.org/v4/matches/{fid}'})
    # Brought forward from a later forecast date: settle here with the original pre-match pick.
    listed = {r['fixture_id'] for r in matches}
    for fid, rec in finals_by_fixture.items():
        m = next((x for x in frozen['matches'] if str(x['fixture_id']) == fid), None)
        if (m is None or fid in forecasts or fid in listed or rec['date'] != day
                or pd.Timestamp(m['generated_at']) >= pd.Timestamp(rec['kickoff_utc'])):continue
        matches.append({**{k: v for k, v in rec.items() if k != 'additional_statistics'},
                        'schedule_change': {'from_date': m['fecha'], 'from_kickoff_utc': m['kickoff_utc'],
                                            'to_date': day, 'to_kickoff_utc': rec['kickoff_utc'], 'direction': 'adelantado'}})
    record = {'date': day, 'ingested_at': datetime.now(timezone.utc).isoformat(),
              'provider': 'ESPN final boxscores (automatic daily update); scores cross-checked with football-data.org when reachable',
              'matches': matches, 'deferred': deferred, 'pending': pending, 'advanced': advanced,
              'added_rows_this_run': 0, 'scope': list(LEAGUES.values()), 'automation': 'daily_update'}
    if previous is not None and comparable(previous) == comparable(record):return None, 'sin cambios'
    if previous is not None:
        record['provider'] = previous.get('provider', record['provider'])
        record.setdefault('updates', list(previous.get('updates', []))).append(
            {'at': record['ingested_at'], 'action': 'daily_update merged new finals/pending state'})
    return record, 'actualizado'


# ---------------------------------------------------------------- main
def window(days, end=None):
    end = pd.Timestamp(end) if end else today_local()
    return [str((end - pd.Timedelta(days=i)).date()) for i in range(days, -1, -1)]


def main(days=3, end=None, source_dir=None, apply=True, post=True, data_dir=DATA_DIR,
         artifact_dir=ARTIFACT_DIR, web_dir=WEB_DIR, sofascore_dir=None):
    run_at = datetime.now(timezone.utc)
    dates = window(days, end)
    run_dir = artifact_dir/'auto'/str(run_at.astimezone(LIMA).date())
    key = secret('FOOTBALL_DATA_KEY')
    source = OfflineSource(source_dir) if source_dir else OnlineSource(artifact_dir/'auto'/'raw', key)
    report = {'run_at': run_at.isoformat(), 'dates': dates, 'mode': 'offline' if source_dir else 'online',
              'football_data_key': bool(key) if not source_dir else None, 'apply': apply}
    if apply:report['frozen'] = {d: freeze_forecasts(d, artifact_dir) for d in dates}
    calendar = pd.read_csv(data_dir/'matches_footballdata.csv')
    calendar['_home'] = calendar.home_team.map(canonical_team);calendar['_away'] = calendar.away_team.map(canonical_team)
    known = set(calendar._home) | set(calendar._away)
    for name in ['match_stats_actualseason', 'match_stats_champions_actualseason', 'match_stats_4ligas']:
        p = data_dir/f'{name}.csv'
        if p.exists():known |= set(pd.read_csv(p, usecols=['team']).team.map(canonical_team))
    fd = provider_index(source.football_data(dates[0], str((pd.Timestamp(dates[-1]) + timedelta(days=1)).date())))
    events = collect_events(source, dates)
    failed_boards = [e for e in getattr(source, 'errors', []) if e['url'].endswith('/scoreboard')]
    report['healthy'] = len(failed_boards) < len(LEAGUES) * (len(dates) + 1)
    if not report['healthy']:
        report['error'] = 'ESPN no respondió en ningún scoreboard; no se modifica nada.'
        dump(run_dir/'run_report.json', report);print(report['error']);return report
    finals, pendings = [], []
    for eid, (day, code, league, event) in sorted(events.items(), key=lambda x: (x[1][0], x[1][2], x[0])):
        kind, item = evaluate_event(day, code, league, event, source, calendar, fd, known)
        (finals if kind == 'final' else pendings).append(item)
    added, present, conflicts = import_finals(finals, data_dir, apply)
    report.update(events=len(events), finals=len(finals), added_matches=[r['match_id'] for r in added],
                  added_rows=2 * len(added), already_present=present, source_differences=conflicts,
                  pending=pendings, source_errors=getattr(source, 'errors', []),
                  espn_only=[r['match_id'] for r in finals if r['score_verification'].get('status') == 'espn_only'])
    if sofascore_dir:
        from sofascore_capture import compare_directory
        report['sofascore_cross_check'] = compare_directory(sofascore_dir, finals)
    if not apply:
        return report
    cal_changed, cal_issues = update_calendar(finals, pendings, data_dir)
    report.update(calendar_changed=cal_changed, calendar_issues=cal_issues)
    calendar = pd.read_csv(data_dir/'matches_footballdata.csv')
    by_fixture = {r['fixture_id']: r for r in finals}
    pend_fixture = {p['fixture_id']: p for p in pendings if 'fixture_id' in p}
    reviews = {}
    for day in dates:
        record, status = build_ingestion(day, by_fixture, pend_fixture, calendar, artifact_dir)
        reviews[day] = {'ingestion': status}
        if record is None:continue
        if not record['matches'] and not (artifact_dir/'daily_reviews'/day/'ingestion.json').exists():
            reviews[day] = {'ingestion': 'sin finales todavía'};continue
        record['added_rows_this_run'] = 2 * sum(r['date'] == day for r in added)
        archive = artifact_dir/'daily_reviews'/day
        dump(archive/'ingestion.json', record);dump(web_dir/'data'/f'actuals_{day}.json', record)
        if not post or not record['matches']:continue
        try:
            from review_ingested_matchday import main as review
            out = review(archive, day)
            reviews[day]['review'] = {'tier_summary': out['tier_summary'], 'unique_summary': out['unique_summary']}
        except Exception as exc:
            reviews[day]['review_error'] = f'{type(exc).__name__}: {exc}'
    report['reviews'] = reviews
    if post:
        try:
            from score_archive import main as score;s = score();report['prospective'] = {k: s[k] for k in ['scored_matches', 'accuracy', 'log_loss']}
        except Exception as exc:report['prospective_error'] = f'{type(exc).__name__}: {exc}'
        try:
            from build_team_dashboard import main as teams
            t = teams(refresh=bool(key) and not source_dir);report['standings_refresh'] = t.get('refresh_report')
        except Exception as exc:report['teams_error'] = f'{type(exc).__name__}: {exc}'
    dump(run_dir/'run_report.json', report)
    print(json.dumps({k: report[k] for k in ['dates', 'events', 'finals', 'added_rows', 'espn_only']} |
                     {'pending': len(pendings), 'source_differences': len(conflicts), 'reviews': reviews}, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--days', type=int, default=3, help='Lima dates before the end date to (re)check')
    p.add_argument('--end', help='Last Lima date (default: today)')
    p.add_argument('--source-dir', help='Run offline from saved ESPN/football-data JSON')
    p.add_argument('--dry-run', action='store_true', help='Validate and report without writing')
    p.add_argument('--sofascore-dir', help='Optional saved Sofascore captures to cross-check')
    a = p.parse_args()
    main(a.days, a.end, a.source_dir, apply=not a.dry_run, sofascore_dir=a.sofascore_dir)

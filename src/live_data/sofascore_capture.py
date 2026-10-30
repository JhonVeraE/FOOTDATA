"""Manual Sofascore cross-check (optional; Sofascore blocks unattended clients).

A capture is the JSON of three public endpoints saved together:
    {"fixture_id": "558551",
     "event": <GET /api/v1/event/{id}>,
     "statistics": <GET /api/v1/event/{id}/statistics>,
     "incidents": <GET /api/v1/event/{id}/incidents>}
Only the full-match period ('ALL') is used. Sofascore omits card categories that
are zero, so a missing red/yellow count is confirmed from the incidents
timeline; without incidents the capture is rejected instead of assuming zero.
"""
import json
from pathlib import Path

KEYS = {'shots': 'totalShotsOnGoal', 'sot': 'shotsOnGoal', 'fouls': 'fouls', 'corners': 'cornerKicks'}


def _count(value):
    n = float(value)
    if n < 0 or not n.is_integer():raise ValueError('Invalid count')
    return int(n)


def parse_capture(capture):
    event = capture['event'].get('event', capture['event'])
    if event['status']['type'] != 'finished':raise ValueError('Sofascore event not finished')
    periods = {p['period']: p for p in capture['statistics']['statistics']}
    if 'ALL' not in periods:raise ValueError('Missing full-match statistics')
    items = {}
    for group in periods['ALL']['groups']:
        for item in group['statisticsItems']:items.setdefault(item['key'], [item['homeValue'], item['awayValue']])
    metrics = {'goals': [_count(event['homeScore']['current']), _count(event['awayScore']['current'])]}
    for metric, key in KEYS.items():
        if key not in items:raise ValueError(f'Missing statistic {key}')
        metrics[metric] = [_count(v) for v in items[key]]
    cards = {}
    incidents = capture.get('incidents')
    for kind, classes in [('yellowCards', {'yellow'}), ('redCards', {'red', 'yellowRed'})]:
        if kind in items:cards[kind] = [_count(v) for v in items[kind]];continue
        if incidents is None:raise ValueError(f'{kind} omitted and no incidents to confirm it')
        rows = [i for i in incidents['incidents'] if i.get('incidentType') == 'card' and i.get('incidentClass') in classes]
        cards[kind] = [sum(bool(i['isHome']) for i in rows), sum(not i['isHome'] for i in rows)]
    metrics['cards'] = [cards['yellowCards'][i] + cards['redCards'][i] for i in (0, 1)]
    if any(metrics['sot'][i] > metrics['shots'][i] for i in (0, 1)):raise ValueError('Shots on target exceed shots')
    return {'sofascore_event_id': str(event.get('id')), 'home': event['homeTeam']['name'], 'away': event['awayTeam']['name'],
            'metrics': metrics, 'yellow': cards['yellowCards'], 'red': cards['redCards']}


def compare(espn_metrics, sofascore_metrics):
    """Metrics present in both sources whose home/away values differ."""
    return {k: {'espn': espn_metrics[k], 'sofascore': sofascore_metrics[k]}
            for k in espn_metrics if k in sofascore_metrics and espn_metrics[k] != sofascore_metrics[k]}


def compare_directory(directory, finals):
    """Compare saved captures (one JSON per fixture) with the ESPN finals of a run."""
    by_fixture = {r['fixture_id']: r for r in finals}
    out = []
    for path in sorted(Path(directory).glob('*.json')):
        capture = json.loads(path.read_text(encoding='utf-8'))
        fid = str(capture.get('fixture_id', ''))
        if fid not in by_fixture:continue
        try:
            parsed = parse_capture(capture)
            out.append({'fixture_id': fid, 'file': path.name, 'differences': compare(by_fixture[fid]['metrics'], parsed['metrics'])})
        except (KeyError, ValueError, TypeError) as exc:
            out.append({'fixture_id': fid, 'file': path.name, 'error': str(exc)})
    return out

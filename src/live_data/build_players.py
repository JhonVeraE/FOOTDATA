"""Construye web/data/players.json a partir de las capturas de SofaScore (data/artifacts/players_raw/<liga>/).

No necesita red: la captura se hace desde el navegador de la PC. Por ahora LaLiga (prueba).
"""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'data' / 'artifacts' / 'players_raw'
OUT = ROOT / 'web' / 'data' / 'players.json'
LEAGUES = {'esp.1': ('La Liga', {
    'Athletic Club': 'Ath Bilbao', 'Atlético Madrid': 'Ath Madrid', 'Celta Vigo': 'Celta', 'Deportivo Alavés': 'Alaves',
    'Deportivo de A Coruña': 'La Coruna', 'Elche': 'Elche', 'Espanyol': 'Espanol', 'FC Barcelona': 'Barcelona', 'Getafe': 'Getafe',
    'Levante UD': 'Levante', 'Málaga CF': 'Malaga', 'Osasuna': 'Osasuna', 'Rayo Vallecano': 'Vallecano', 'Real Betis': 'Betis',
    'Real Madrid': 'Real Madrid', 'Real Racing Club': 'Santander', 'Real Sociedad': 'Sociedad', 'Sevilla': 'Sevilla',
    'Valencia': 'Valencia', 'Villarreal': 'Villarreal'})}
POS = {'G': 'Portero', 'D': 'Defensa', 'M': 'Mediocampista', 'F': 'Delantero'}
FIELDS = ['apps', 'starts', 'min', 'goals', 'pen', 'assists', 'shots', 'sot', 'yc', 'rc', 'fouls', 'xg']


def per90(v, minutes):
    return round(v * 90 / minutes, 2) if minutes and v is not None else None


def build():
    out = {'generated_at': datetime.now(timezone.utc).isoformat(), 'source': 'SofaScore (estadísticas públicas)', 'competitions': {}}
    for code, (comp, names) in LEAGUES.items():
        stats_path, squads_path = RAW / code / 'sofascore_stats.json', RAW / code / 'sofascore_squads.json'
        if not stats_path.exists():continue
        raw = json.loads(stats_path.read_text(encoding='utf-8'))
        squads = json.loads(squads_path.read_text(encoding='utf-8')) if squads_path.exists() else {}
        teams, unknown = {}, set()
        for p in raw['players']:
            team = names.get(p['team'])
            if not team:unknown.add(p['team']);continue
            sq = squads.get(str(p['id']), {})
            row = {'id': p['id'], 'name': p['name'], 'pos': POS.get(sq.get('pos'), None), 'jersey': sq.get('jersey'),
                   'age': sq.get('age'), 'country': sq.get('country')}
            for k in FIELDS:row[k] = p.get(k) if p.get(k) is not None else 0
            row['xg'] = round(row['xg'] or 0, 2)
            row['cards'] = row['yc'] + row['rc']
            minutes = row['min']
            row['p90'] = {k: per90(row[k], minutes) for k in ['goals', 'shots', 'sot', 'cards', 'fouls', 'assists', 'xg']}
            row['sot_rate'] = round(row['sot'] / row['shots'], 2) if row['shots'] else None
            teams.setdefault(team, []).append(row)
        for t in teams.values():t.sort(key=lambda r: (-r['min'], r['name']))
        out['competitions'][comp] = {'season': raw.get('season'), 'observed_at': raw.get('observed_at'), 'players': sum(map(len, teams.values())),
                                     'teams': teams, 'unmapped_teams': sorted(unknown)}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return out


if __name__ == '__main__':
    o = build()
    for c, d in o['competitions'].items():print(c, d['players'], 'jugadores', len(d['teams']), 'equipos', 'sin mapear:', d['unmapped_teams'])

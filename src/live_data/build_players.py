"""Construye web/data/players.json a partir de las capturas de SofaScore (data/artifacts/players_raw/<liga>/).

No necesita red: la captura se hace desde el navegador de la PC. Por ahora LaLiga (prueba).
"""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'data' / 'artifacts' / 'players_raw'
OUT = ROOT / 'web' / 'data' / 'players.json'
NAMES = {
    # LaLiga
    'Athletic Club': 'Ath Bilbao', 'Atlético Madrid': 'Ath Madrid', 'Celta Vigo': 'Celta', 'Deportivo Alavés': 'Alaves',
    'Deportivo de A Coruña': 'La Coruna', 'Espanyol': 'Espanol', 'FC Barcelona': 'Barcelona', 'Levante UD': 'Levante',
    'Málaga CF': 'Malaga', 'Rayo Vallecano': 'Vallecano', 'Real Betis': 'Betis', 'Real Racing Club': 'Santander',
    'Real Sociedad': 'Sociedad',
    # Premier League
    'Brighton & Hove Albion': 'Brighton', 'Coventry City': 'Coventry', 'Hull City': 'Hull', 'Ipswich Town': 'Ipswich',
    'Leeds United': 'Leeds', 'Liverpool FC': 'Liverpool', 'Manchester City': 'Man City', 'Manchester United': 'Man United',
    'Newcastle United': 'Newcastle', 'Nottingham Forest': "Nott'm Forest", 'Tottenham Hotspur': 'Tottenham',
    # Serie A
    'AC Milan': 'Milan', 'AS Roma': 'Roma', 'SSC Napoli': 'Napoli',
    # Bundesliga
    '1. FC Köln': 'FC Koln', '1. FC Union Berlin': 'Union Berlin', '1. FSV Mainz 05': 'Mainz', 'Bayer 04 Leverkusen': 'Leverkusen',
    "Borussia M'gladbach": "M'gladbach", 'Borussia Dortmund': 'Dortmund', 'Eintracht Frankfurt': 'Frankfurt', 'FC Augsburg': 'Augsburg', 'FC Bayern München': 'Bayern Munich',
    'FC Schalke 04': 'Schalke 04', 'Hamburger SV': 'Hamburg', 'SC Freiburg': 'Freiburg', 'SC Paderborn 07': 'Paderborn',
    'SV 07 Elversberg': 'Elversberg', 'SV Werder Bremen': 'Werder Bremen', 'TSG Hoffenheim': 'Hoffenheim', 'VfB Stuttgart': 'Stuttgart',
    # Ligue 1
    'AJ Auxerre': 'Auxerre', 'AS Monaco': 'Monaco', 'LOSC Lille': 'Lille', 'OGC Nice': 'Nice', 'Olympique Lyonnais': 'Lyon',
    'Olympique de Marseille': 'Marseille', 'Paris Saint-Germain': 'Paris SG', 'RC Lens': 'Lens', 'RC Strasbourg': 'Strasbourg',
    'Stade Brestois': 'Brest', 'Stade Rennais': 'Rennes',
    # Champions (resto)
    'Bodø/Glimt': 'Bodo/Glimt', 'PSV Eindhoven': 'PSV', 'SK Slavia Praha': 'Slavia Praha', 'ŠK Slovan Bratislava': 'Slovan Bratislava',
}
LEAGUES = {'esp.1': 'La Liga', 'eng.1': 'Premier League', 'ita.1': 'Serie A', 'ger.1': 'Bundesliga', 'fra.1': 'Ligue 1',
           'uefa.champions': 'UEFA Champions League'}
POS = {'G': 'Portero', 'D': 'Defensa', 'M': 'Mediocampista', 'F': 'Delantero'}
FIELDS = ['apps', 'starts', 'min', 'goals', 'pen', 'assists', 'shots', 'sot', 'yc', 'rc', 'fouls', 'xg']


def per90(v, minutes):
    return round(v * 90 / minutes, 2) if minutes and v is not None else None


def build():
    out = {'generated_at': datetime.now(timezone.utc).isoformat(), 'source': 'SofaScore (estadísticas públicas)', 'competitions': {}}
    known = json.loads((ROOT / 'web' / 'data' / 'teams.json').read_text(encoding='utf-8'))['competitions']
    for code, comp in LEAGUES.items():
        single, stats_path, squads_path = RAW / code / 'sofascore.json', RAW / code / 'sofascore_stats.json', RAW / code / 'sofascore_squads.json'
        if single.exists():
            raw = json.loads(single.read_text(encoding='utf-8'));squads = raw.get('squads', {})
        elif stats_path.exists():
            raw = json.loads(stats_path.read_text(encoding='utf-8'))
            squads = json.loads(squads_path.read_text(encoding='utf-8')) if squads_path.exists() else {}
        else:continue
        ours = {t['team'] for t in known.get(comp, {}).get('teams', [])}
        names = {n: NAMES.get(n, n) for n in {p['team'] for p in raw['players']}}
        names = {k: v for k, v in names.items() if v in ours}
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
        out['competitions'][comp] = {'season': raw.get('season_name', raw.get('season')), 'observed_at': raw.get('observed_at'), 'players': sum(map(len, teams.values())),
                                     'teams': teams, 'unmapped_teams': sorted(unknown)}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return out


if __name__ == '__main__':
    o = build()
    for c, d in o['competitions'].items():print(c, d['players'], 'jugadores', len(d['teams']), 'equipos', 'sin mapear:', d['unmapped_teams'])

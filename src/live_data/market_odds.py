"""Public pre-match market odds (football-data.co.uk) used as an agreement check.

The average bookmaker price is better informed than the goal model on 1X2 and
over/under 2.5 (retrospective 2025/26 test, data/artifacts/market_agreement_audit.json).
The check never changes model probabilities; it only removes a pick when the
de-margined market probability is below the pick's tier floor.

Source: https://www.football-data.co.uk/fixtures.csv (upcoming domestic fixtures,
updated by the site before each round). No Champions League prices there.
"""
import io
import json
from datetime import datetime, timezone
import pandas as pd
from data_store import canonical_team
from paths import ARTIFACT_DIR, DATA_DIR

URL = 'https://www.football-data.co.uk/fixtures.csv'
LIVE = DATA_DIR / 'market_odds.json'
DIVISIONS = {'E0': 'Premier League', 'SP1': 'La Liga', 'D1': 'Bundesliga', 'I1': 'Serie A', 'F1': 'Ligue 1'}
# Average market first; Bet365 only when the average is absent.
PRICE_SETS = [('AvgH', 'AvgD', 'AvgA', 'Avg>2.5', 'Avg<2.5', 'average'),
              ('B365H', 'B365D', 'B365A', 'B365>2.5', 'B365<2.5', 'bet365')]
MAX_AGE = pd.Timedelta(days=5)


def parse_fixtures(text, retrieved_at):
    df = pd.read_csv(io.StringIO(text.lstrip('﻿')))
    df = df[df.Div.isin(DIVISIONS)].copy()
    out = []
    for r in df.itertuples(index=False, name=None):
        row = dict(zip(df.columns, r))
        prices = None
        for h, d, a, o, u, name in PRICE_SETS:
            if all(c in row and pd.notna(row[c]) and float(row[c]) > 1 for c in (h, d, a)):
                prices = dict(home=float(row[h]), draw=float(row[d]), away=float(row[a]), price_set=name,
                              over25=float(row[o]) if o in row and pd.notna(row[o]) else None,
                              under25=float(row[u]) if u in row and pd.notna(row[u]) else None)
                break
        if prices is None:
            continue
        date = pd.to_datetime(row['Date'], dayfirst=True).date().isoformat()
        out.append({'date': date, 'time_uk': row.get('Time'), 'league': DIVISIONS[row['Div']],
                    'home': canonical_team(row['HomeTeam']), 'away': canonical_team(row['AwayTeam']),
                    **prices, 'retrieved_at': retrieved_at, 'source': URL})
    return out


def fetch_market_odds(timeout=30):
    """Download, archive raw CSV and write data/live/market_odds.json. Returns records or None offline."""
    import requests
    now = datetime.now(timezone.utc).isoformat()
    try:
        response = requests.get(URL, timeout=timeout, headers={'User-Agent': 'FOOTDATA research'})
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f'Market odds unavailable: {exc}')
        return None
    text = response.content.decode('utf-8-sig', errors='replace')
    archive = ARTIFACT_DIR / 'market_odds'
    archive.mkdir(parents=True, exist_ok=True)
    stamp = now.replace(':', '').replace('-', '')[:15]
    (archive / f'fixtures_{stamp}.csv').write_text(text, encoding='utf-8')
    records = parse_fixtures(text, now)
    LIVE.write_text(json.dumps({'retrieved_at': now, 'source': URL, 'records': records}, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'Market odds: {len(records)} domestic fixtures')
    return records


def load_market(as_of=None):
    if not LIVE.exists():
        return {}
    data = json.loads(LIVE.read_text(encoding='utf-8'))
    clock = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp.now(tz='UTC')
    if clock.tzinfo is None:
        clock = clock.tz_localize('UTC')
    out = {}
    for r in data.get('records', []):
        seen = pd.Timestamp(r['retrieved_at'])
        if seen > clock or clock - seen > MAX_AGE:
            continue  # never use prices observed after publication, nor stale ones
        out[(r['date'], r['league'], r['home'], r['away'])] = r
    return out


def implied(record):
    """De-margined probabilities (proportional normalisation)."""
    q = [1 / record['home'], 1 / record['draw'], 1 / record['away']]
    s = sum(q)
    p = {'home': q[0] / s, 'draw': q[1] / s, 'away': q[2] / s}
    out = {'result': p, 'double_chance': {'1X': p['home'] + p['draw'], 'X2': p['away'] + p['draw'], '12': p['home'] + p['away']}}
    if record.get('over25') and record.get('under25'):
        o, u = 1 / record['over25'], 1 / record['under25']
        out['goals_2.5'] = {'over': o / (o + u), 'under': u / (o + u)}
    out['margin_1x2'] = s - 1
    return out


def market_probability(item, market):
    """Market probability for the same selection, or None when not derivable."""
    if not market:
        return None
    kind, side, line, scope = item['kind'], item['side'], item['line'], item['scope']
    if kind == 'result':
        return market['result'].get(side)
    if kind == 'double_chance':
        return market['double_chance'].get(side)
    if kind == 'goals' and scope == 'total' and line == 2.5 and 'goals_2.5' in market:
        return market['goals_2.5'].get(side)
    return None


def lookup(market_index, report):
    date = pd.Timestamp(report['kickoff_utc']).tz_convert('Europe/London').date().isoformat() if pd.Timestamp(report['kickoff_utc']).tzinfo else str(report['fecha'])
    for d in {date, str(report.get('fecha'))}:
        key = (d, report['competition'], canonical_team(report['local']), canonical_team(report['visitante']))
        if key in market_index:
            return market_index[key]
    return None


# ------------------------------------------------------------------ Betano Perú
# Visible pre-match prices captured from betano.pe (data/artifacts/betano_visible/<date>/betano_compact.json).
# Compact row: [league, betano_id, home, away, start_utc, [1,X,2], [o1.5,u1.5,o2.5,u2.5,o3.5,u3.5,o4.5,u4.5],
#               [btts_yes,btts_no], [home o0.5,u0.5,o1.5,u1.5], [away o0.5,u0.5,o1.5,u1.5],
#               European handicap rows for home handicap k in (-2,-1,+1,+2): [home, draw, away] or null]
BETANO_LEAGUES = {'PL': 'Premier League', 'PD': 'La Liga', 'BL': 'Bundesliga', 'SA': 'Serie A', 'FL': 'Ligue 1',
                  'CL': 'UEFA Champions League'}
# Explicit, reviewed name map (no fuzzy matching). Unknown names are skipped and reported.
BETANO_NAMES = {
    'Chelsea FC': 'Chelsea', 'Manchester United': 'Man United', 'AFC Bournemouth': 'Bournemouth', 'Leeds United': 'Leeds',
    'Brentford FC': 'Brentford', 'Nottingham Forest': "Nott'm Forest", 'Coventry City': 'Coventry', 'Sunderland': 'Sunderland',
    'Hull City': 'Hull', 'Ipswich Town': 'Ipswich', 'Manchester City': 'Man City', 'Brighton & Hove Albion': 'Brighton',
    'Tottenham Hotspur': 'Tottenham', 'Crystal Palace FC': 'Crystal Palace', 'Aston Villa': 'Aston Villa', 'Fulham': 'Fulham',
    'Liverpool FC': 'Liverpool', 'Arsenal FC': 'Arsenal', 'Newcastle United': 'Newcastle', 'Everton FC': 'Everton',
    'Levante UD': 'Levante', 'Atlético Madrid': 'Ath Madrid', 'Rayo Vallecano': 'Vallecano', 'RC Celta de Vigo': 'Celta',
    'Real Betis Balompié': 'Betis', 'Málaga CF': 'Malaga', 'FC Barcelona': 'Barcelona', 'Deportivo Alavés': 'Alaves',
    'Getafe CF': 'Getafe', 'Sevilla FC': 'Sevilla', 'Racing Santander': 'Santander', 'Real Madrid': 'Real Madrid',
    'Elche CF': 'Elche', 'Valencia CF': 'Valencia', 'Athletic Bilbao': 'Ath Bilbao', 'Real Sociedad': 'Sociedad',
    'Deportivo de A Coruña': 'La Coruna', 'CA Osasuna': 'Osasuna', 'Villarreal CF': 'Villarreal', 'RCD Espanyol': 'Espanol',
    'Bologna FC': 'Bologna', 'AC Monza': 'Monza', 'Udinese Calcio': 'Udinese', 'AS Roma': 'Roma', 'AC Milan': 'Milan',
    'Inter de Milán': 'Inter', 'Como 1907': 'Como', 'Venezia FC': 'Venezia', 'Frosinone': 'Frosinone', 'Torino FC': 'Torino',
    'SS Lazio': 'Lazio', 'Cagliari Calcio': 'Cagliari', 'US Lecce': 'Lecce', 'Genoa CFC': 'Genoa', 'Juventus FC': 'Juventus',
    'SSC Napoli': 'Napoli', 'US Sassuolo Calcio': 'Sassuolo', 'AC Fiorentina': 'Fiorentina', 'Atalanta': 'Atalanta',
    'Parma Calcio 1913': 'Parma',
    'Bayer 04 Leverkusen': 'Leverkusen', 'VfB Stuttgart': 'Stuttgart', 'Borussia Monchengladbach': "M'gladbach",
    'SC Paderborn 07': 'Paderborn', 'FC Augsburg': 'Augsburg', 'SC Friburgo': 'Freiburg', 'FC Schalke 04': 'Schalke 04',
    'RB Leipzig': 'RB Leipzig', 'Werder Bremen': 'Werder Bremen', 'TSG 1899 Hoffenheim': 'Hoffenheim',
    'FC Bayern Munchen': 'Bayern Munich', 'Borussia Dortmund': 'Dortmund', '1. FC Union Berlin': 'Union Berlin',
    '1. FC Köln': 'FC Koln', 'Eintracht Frankfurt': 'Frankfurt', 'Hamburger SV': 'Hamburg',
    'ES Troyes AC': 'Troyes', 'Le Mans UC 72': 'Le Mans', 'RC Strasbourg': 'Strasbourg', 'AJ Auxerre': 'Auxerre',
    'Olympique Lyonnais': 'Lyon', 'Angers SCO': 'Angers', 'Paris FC': 'Paris FC', 'AS Mónaco': 'Monaco',
    'Olympique Marseille': 'Marseille', 'Toulouse FC': 'Toulouse', 'FC Lorient': 'Lorient', 'Stade Brestois 29': 'Brest',
    'FC Shakhtar Donetsk': 'Shakhtar Donetsk', 'Sporting CP': 'Sporting CP', 'Galatasaray SK': 'Galatasaray',
    'Lille OSC': 'Lille', 'FK Bodo/Glimt': 'Bodo/Glimt', 'Feyenoord Rotterdam': 'Feyenoord', 'Linzer ASK': 'LASK',
    'SK Slovan Bratislava': 'Slovan Bratislava', 'Paris Saint-Germain': 'Paris SG', 'AEK Atenas': 'AEK Athens',
    'Fenerbahce SK': 'Fenerbahçe', 'PSV Eindhoven': 'PSV', 'Club Brugge KV': 'Club Brugge KV', 'RC Lens': 'Lens',
    'SK Slavia Praha': 'Slavia Praha', 'Viking FK': 'Viking FK', 'FC Sabah': 'Sabah FK', 'FC Porto': 'FC Porto',
}
BETANO_NAMES.update({'FSV Mainz 05': 'Mainz', 'Le Havre AC': 'Le Havre', 'OGC Niza': 'Nice', 'Stade Rennais FC': 'Rennes',
                     'SV Elversberg': 'Elversberg'})
BETANO_MAX_AGE = pd.Timedelta(days=3)
# Full capture (betano_full.json): every line Betano shows for result, goals and the count markets.
BETANO_COUNT_TITLES = {'Más/Menos Córners': 'corners', 'Remates totales': 'shots', 'Tiros al Arco': 'sot',
                       'Total de Faltas Cometidas': 'fouls', 'Tarjetas Totales Más/Menos': 'cards'}
BETANO_SCOPE = {'T': 'total', 'H': 'home', 'A': 'away'}


def _ou(rows):
    table = {}
    for name, line, price in rows or []:
        if line is None:continue
        pair = table.setdefault(f'{float(line):g}', [None, None])
        pair[0 if name.startswith('Más') else 1] = price
    return table


def _full_record(e, path, observed_at):
    m = e['m']
    res = {r[0]: r[2] for r in m.get('T|Resultado del partido', [])}
    result = [res.get('1'), res.get('X'), res.get('2')] if res else None
    names = {'1X': '1X', 'X1': '1X', '12': '12', '21': '12', 'X2': 'X2', '2X': 'X2',
             f"{e['home']} o Empate": '1X', f"{e['home']} o {e['away']}": '12', f"{e['away']} o Empate": 'X2'}
    dc = {names[r[0]]: r[2] for r in m.get('T|Doble oportunidad', []) if r[0] in names}
    bt = {r[0]: r[2] for r in m.get('T|Ambos equipos anotan', [])}
    counts = {}
    for key, rows in m.items():
        sc, title = key.split('|', 1)
        if title in BETANO_COUNT_TITLES:counts[(BETANO_COUNT_TITLES[title], BETANO_SCOPE[sc])] = _ou(rows)
    rg = {}
    for key, rows in m.items():
        for prefix, kind in [('T|Resultado del partido con Más/Menos (', 'r'), ('T|Doble Oportunidad con Más/Menos (', 'dc')]:
            if key.startswith(prefix):
                line = key[len(prefix):-1]
                for name, _, price in rows:rg[(kind, line, name)] = price
    return {'source': 'Betano Perú', 'betano_id': e['id'], 'kickoff_utc': e['t'][:19] + 'Z', 'observed_at': observed_at,
            'result': result if result and None not in result else None, 'goals': _ou(m.get('T|Goles totales Más/Menos')),
            'btts': [bt.get('Sí'), bt.get('No')] if bt else None, 'home_goals': {}, 'away_goals': {}, 'euro_handicap': {},
            'double_chance': dc, 'counts': counts, 'result_goals': rg, 'home_name': e['home'], 'away_name': e['away'], 'capture': str(path.relative_to(ARTIFACT_DIR))}


def _pairs(values):
    return [values[i:i + 2] for i in range(0, len(values or []), 2)]


def load_betano(as_of=None, root=None):
    """Latest Betano capture observed before ``as_of`` (and not older than 3 days)."""
    root = root or ARTIFACT_DIR / 'betano_visible'
    clock = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp.now(tz='UTC')
    if clock.tzinfo is None:clock = clock.tz_localize('UTC')
    best = None
    for path in sorted(root.glob('*/betano_full.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        seen = pd.Timestamp(data['observed_at'])
        if seen <= clock and clock - seen <= BETANO_MAX_AGE and (best is None or seen > best[0]):best = (seen, path, data)
    if best is not None:
        seen, path, data = best
        index, unknown = {}, []
        for e in data['events']:
            league = BETANO_LEAGUES.get({'BL1': 'BL', 'FL1': 'FL'}.get(e['lg'], e['lg']))
            home = BETANO_NAMES.get(e['home']);away = BETANO_NAMES.get(e['away'])
            if not (league and home and away):unknown.append([e['home'], e['away']]);continue
            index[(league, canonical_team(home), canonical_team(away))] = _full_record(e, path, data['observed_at'])
        return index, {'status': 'loaded', 'format': 'full', 'observed_at': data['observed_at'], 'fixtures': len(index),
                       'unmapped': unknown, 'capture': str(path.relative_to(ARTIFACT_DIR))}
    for path in sorted(root.glob('*/betano_compact.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        seen = pd.Timestamp(data['observed_at'])
        if seen <= clock and clock - seen <= BETANO_MAX_AGE and (best is None or seen > best[0]):best = (seen, path, data)
    if best is None:return {}, {'status': 'no_capture'}
    seen, path, data = best
    index, unknown = {}, []
    for r in data['rows']:
        league = BETANO_LEAGUES.get(r[0]);home = BETANO_NAMES.get(r[2]);away = BETANO_NAMES.get(r[3])
        if not (league and home and away):unknown.append(r[2:4]);continue
        index[(league, canonical_team(home), canonical_team(away))] = {
            'source': 'Betano Perú', 'betano_id': r[1], 'kickoff_utc': r[4] + ':00Z', 'observed_at': data['observed_at'],
            'result': r[5], 'goals': dict(zip(['1.5', '2.5', '3.5', '4.5'], _pairs(r[6]))), 'btts': r[7],
            'home_goals': dict(zip(['0.5', '1.5'], _pairs(r[8]))), 'away_goals': dict(zip(['0.5', '1.5'], _pairs(r[9]))),
            'euro_handicap': dict(zip([-2, -1, 1, 2], r[10])), 'capture': str(path.relative_to(ARTIFACT_DIR))}
    return index, {'status': 'loaded', 'observed_at': data['observed_at'], 'fixtures': len(index), 'unmapped': unknown,
                   'capture': str(path.relative_to(ARTIFACT_DIR))}


def _norm(prices):
    if not prices or any(p is None or p <= 1 for p in prices):return None
    q = [1 / p for p in prices];s = sum(q)
    return [x / s for x in q]


def betano_quote(item, rec):
    """(de-margined probability, raw Betano price, Betano market description) for the same bet, or None."""
    if not rec:return None
    kind, side, line, scope = item['kind'], item['side'], item['line'], item['scope']
    if kind in ('result', 'double_chance'):
        p = _norm(rec['result'])
        if p is None:return None
        idx = {'home': 0, 'draw': 1, 'away': 2}
        if kind == 'result':
            return p[idx[side]], rec['result'][idx[side]], 'Resultado del partido'
        dc = {'1X': p[0] + p[1], 'X2': p[1] + p[2], '12': p[0] + p[2]}[side]
        real = (rec.get('double_chance') or {}).get(side)
        return dc, real, 'Doble oportunidad' if real else 'Doble oportunidad (probabilidad derivada del 1X2)'
    if kind in BETANO_COUNT_TITLES.values():
        table = (rec.get('counts') or {}).get((kind, scope))
        if table is None:return None
        pair = table.get(f'{line:g}') if line is not None else None
        i = 0 if side == 'over' else 1
        if not pair or pair[i] is None:return (None, None, 'NO_LINE')
        p = _norm(pair)
        title = [t for t, k in BETANO_COUNT_TITLES.items() if k == kind][0]
        return (None if p is None else p[i]), pair[i], title
    if kind == 'result_goals' and rec.get('result_goals'):
        direction = item.get('direction')
        word = 'Más' if direction == 'over' else 'Menos'
        h, a = rec.get('home_name'), rec.get('away_name')
        want = {'home': ('r', f'{h} y {word} {line:g}'), 'away': ('r', f'{a} y {word} {line:g}'), 'draw': ('r', f'Empate y {word} {line:g}'),
                '1X': ('dc', f'{h} o Empate y {word} {line:g}'), 'X2': ('dc', f'{a} o Empate y {word} {line:g}')}.get(side)
        if want is None:return None
        price_ = rec['result_goals'].get((want[0], f'{line:g}', want[1]))
        if price_:return None, price_, 'Resultado/Doble oportunidad con Más/Menos'
        return None
    if kind == 'goals':
        table = rec['goals'] if scope == 'total' else rec['home_goals'] if scope == 'home' else rec['away_goals']
        pair = table.get(f'{line:g}') if line is not None else None
        p = _norm(pair)
        if p is None:return None
        i = 0 if side == 'over' else 1
        market = 'Goles totales Más/Menos' if scope == 'total' else 'Goles del equipo Más/Menos'
        return p[i], pair[i], market
    if kind == 'btts':
        p = _norm(rec['btts'])
        if p is None:return None
        i = 0 if side == 'yes' else 1
        return p[i], rec['btts'][i], 'Ambos equipos anotan'
    if kind == 'handicap' and line is not None:
        # Asian half line == one outcome of a European 3-way row (home handicap k):
        # home line h -> row k=h+0.5, 'home'; away line h -> row k=-(h+0.5), 'away'.
        k = int(line + .5) if side == 'home' else int(-(line + .5))
        row = rec['euro_handicap'].get(k)
        p = _norm(row)
        if p is None:return None
        i = 0 if side == 'home' else 2
        sign = f'{k:+d}'
        return p[i], row[i], f'Hándicap Resultado del Partido (europeo), línea local {sign}, opción {"local" if i == 0 else "visitante"}'
    return None

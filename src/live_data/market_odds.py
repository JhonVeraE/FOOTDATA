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

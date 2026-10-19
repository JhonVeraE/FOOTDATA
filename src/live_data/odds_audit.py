"""Match saved, visible bookmaker markets to frozen recommendations.

No network access or bet placement. Asian and three-way handicaps are distinct.
Missing quotes remain missing; probabilities and selections are never changed.
"""
import re
from datetime import datetime, timedelta, timezone


def norm(value):
    return ' '.join(value.casefold().split())


def fixture_identity(target, page):
    teams = target['betano']['text'].splitlines()
    if len(teams) != 2 or not page.get('heading') or norm(page['heading'][0]) != norm(' '.join(teams)):
        return False
    months = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre']
    date = re.search(r'(\d{1,2}) (\w+) (\d{4}) (\d{2}):(\d{2})', page.get('top', ''), re.I)
    if not date or date[2].lower() not in months:
        return False
    actual = datetime(int(date[3]), months.index(date[2].lower())+1, int(date[1]), int(date[4]), int(date[5]), tzinfo=timezone(timedelta(hours=-5)))
    return actual == datetime.fromisoformat(target['kickoff_utc'])


def market_identity(title, teams):
    title = title.splitlines()[0]
    direct = {'Resultado del partido': ('result','total'), 'Doble oportunidad': ('double_chance','total'), 'Ambos equipos anotan': ('btts','total'), 'Goles totales Más/Menos': ('goals','total'), 'Más/Menos Córners': ('corners','total'), 'Remates totales': ('shots','total'), 'Tiros al Arco': ('sot','total'), 'Total de Faltas Cometidas': ('fouls','total')}
    if title in direct:
        return (*direct[title], None)
    for scope, team in zip(('home','away'), teams):
        for suffix, kind in [(' - Goles totales Más/Menos','goals'), (' Más/Menos Córners','corners'), (' Remates totales','shots'), (' Tiros al Arco','sot'), (' Total de Faltas Cometidas','fouls')]:
            if title == team+suffix:
                return kind, scope, None
    if title == 'Hándicap Asiático (Resultado actual 0 - 0)':
        return 'handicap','team',None
    combined = re.fullmatch(r'(Resultado del partido|Doble Oportunidad) con Más/Menos \(([0-9.]+)\)', title)
    if combined:
        return 'result_goals', 'total', float(combined[2])
    return None


def parse_market(market, teams):
    identity = market_identity(market['title'], teams)
    if not identity:
        return []
    kind, scope, fixed_line = identity
    dc = {teams[0]+' o Empate':'1X', teams[1]+' o Empate':'X2', teams[0]+' o '+teams[1]:'12'}
    result = {'1':'home','X':'draw','2':'away',teams[0]:'home',teams[1]:'away','Empate':'draw'}
    records = []
    for selection in market['selections']:
        quote = re.fullmatch(r'Bet on (.+) with odds ([0-9.]+)\.', selection.get('aria') or '')
        if not quote or float(quote[2]) <= 1:
            continue
        label = quote[1]; line = None; extra = ''; item_scope = scope
        if kind in ('goals','corners','shots','sot','fouls'):
            match = re.fullmatch(r'(Más de|Menos) ([0-9.]+)', label)
            if not match: continue
            side = 'over' if match[1]=='Más de' else 'under'; line = float(match[2])
        elif kind == 'result': side = result.get(label)
        elif kind == 'double_chance': side = dc.get(label)
        elif kind == 'btts': side = {'Sí':'yes','No':'no'}.get(label)
        elif kind == 'handicap':
            match = re.fullmatch(r'(.+) ([+-][0-9.]+)',label)
            if not match or match[1] not in teams: continue
            item_scope = 'total'; side = 'home' if match[1]==teams[0] else 'away'; line = float(match[2])
        else:
            match = re.fullmatch(r'(.+) y (Más|Menos) ([0-9.]+)', label)
            if not match or float(match[3])!=fixed_line: continue
            side = dc.get(match[1]) or result.get(match[1]); line = fixed_line; extra = 'over' if match[2]=='Más' else 'under'
        if side is None: continue
        records.append({'kind':kind,'scope':item_scope,'side':side,'line':line,'extra':extra,'odds':float(quote[2]),'bookmaker_market':market['title'],'bookmaker_selection':label})
    return records


def candidate_key(candidate):
    # Production IDs retain the extra joint-goals direction as their final field.
    extra = candidate['id'].split(':')[-1] if candidate['kind']=='result_goals' else ''
    return candidate['kind'],candidate['scope'],candidate['side'],candidate.get('line'),extra


def quote_key(quote):
    return tuple(quote[k] for k in ('kind','scope','side','line','extra'))


def audit_fixture(target, page):
    valid = fixture_identity(target, page)
    quotes = {}
    if valid:
        for market in page['markets']:
            for quote in parse_market(market,target['betano']['text'].splitlines()):
                key = quote_key(quote)
                if key in quotes and quotes[key]['odds'] != quote['odds']:
                    raise ValueError(f'Conflicting duplicate market: {target["fixture_id"]} {key}')
                quotes[key] = quote
    output = []
    for c in target['selections']:
        q = quotes.get(candidate_key(c))
        row = {'fixture_id':target['fixture_id'],'candidate_id':c['id'],'home':target['home'],'away':target['away'],'kickoff_utc':target['kickoff_utc'],'label':c['label'],'minimum_odds':c['minimum_odds'],'observed_at':page.get('observed_at'),'source_url':page.get('url'),'identity_verified':valid}
        row['status'] = ('above_reference' if q['odds']>=c['minimum_odds'] else 'below_reference') if q else ('exact_quote_not_found' if valid else 'fixture_mismatch')
        if q: row.update(q)
        output.append(row)
    return output

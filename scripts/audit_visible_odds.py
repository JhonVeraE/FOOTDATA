"""Publish an odds audit from saved browser-visible pages and frozen selections."""
import argparse
import copy
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from live_data.odds_audit import audit_fixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--targets', type=Path, required=True)
    parser.add_argument('--frozen', type=Path, required=True)
    parser.add_argument('--pages', type=Path, required=True)
    args = parser.parse_args()
    targets = json.loads(args.targets.read_text(encoding='utf-8'))
    frozen = json.loads(args.frozen.read_text(encoding='utf-8'))
    rows = []
    for target in targets:
        page_path = args.pages/(target['fixture_id']+'.json')
        if not page_path.exists():
            raise ValueError(f'Missing browser capture: {target["fixture_id"]}')
        rows.extend(audit_fixture(target,json.loads(page_path.read_text(encoding='utf-8'))))
    counts = Counter(row['status'] for row in rows)
    audit = {'schema_version':1,'generated_at':datetime.now(timezone.utc).isoformat(),'prediction_run_generated_at':frozen['prediction_run_generated_at'],'dataset_id':frozen['dataset_id'],'bookmaker':'Betano','fixtures':len(targets),'selections':len(rows),'counts':dict(counts),'first_observed_at':min(row['observed_at'] for row in rows),'last_observed_at':max(row['observed_at'] for row in rows),'note':'Cuotas capturadas en páginas públicas. No son precios en vivo. No se colocaron apuestas. Selecciones y probabilidades originales conservadas.','records':rows}
    lookup = {(r['fixture_id'],r['candidate_id']):r for r in rows}
    decorated = copy.deepcopy(frozen)

    def decorate(selection):
        if not selection: return
        row = lookup[(str(selection['fixture_id']),selection['id'])]
        selection.pop('observed_quote',None)
        selection['odds_audit'] = row
        selection['price_status'] = row['status']
        if 'odds' in row:
            selection['observed_quote'] = {**row,'bookmaker':'Betano','complete_market_snapshot':False}

    for match in decorated['matches']:
        for tier in match['tiers']: decorate(tier['selection'])
        for market in match['markets']: decorate(market['selection'])
        decorate(match['parlay_selection'])
    for day in decorated['days']:
        for parlay in day['parlays']:
            for leg in parlay.get('legs',[]): decorate(leg['selection'])
    decorated['odds_audit'] = {k:v for k,v in audit.items() if k!='records'}
    # Keep the exact source predictions alongside their independent price audit.
    for path,data in [(ROOT/'data/artifacts/betano_audit_targets.json',targets),(ROOT/'data/artifacts/recommendations_before_odds_audit.json',frozen),(ROOT/'data/artifacts/betano_odds_audit.json',audit),(ROOT/'web/data/odds_audit.json',audit),(ROOT/'data/artifacts/recommendations.json',decorated),(ROOT/'web/data/fijas.json',decorated)]:
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    quotes = [{**r,'bookmaker':'Betano','complete_market_snapshot':False} for r in rows if 'odds' in r]
    (ROOT/'data/artifacts/betano_odds.json').write_text(json.dumps({'schema_version':1,'source':'Visible public Betano pages; frozen audit; no bets placed','records':quotes},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in audit.items() if k not in ('records','note')},ensure_ascii=False))


if __name__=='__main__': main()

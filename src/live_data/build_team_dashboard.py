"""Publish season-only team statistics and dated provider standings snapshots.

No prediction/model changes. Missing counts are never replaced by zero.
Run with --refresh-standings to refresh the six free provider table endpoints.
"""
import argparse
import json
from datetime import datetime, timezone

import pandas as pd
import requests

from data_store import load_match_stats, load_calendar, canonical_team, season_for, today_local
from paths import DATA_DIR, ARTIFACT_DIR, WEB_DIR
from settings import secret

LEAGUES={'La Liga':'PD','Premier League':'PL','Bundesliga':'BL1','Serie A':'SA','Ligue 1':'FL1','UEFA Champions League':'CL'}
METRICS=['goals','shots','sot','corners','cards','fouls']


def write_json(path, payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    tmp.replace(path)


def summarize(rows):
    count=len(rows)
    wins=int((rows.goals_for>rows.goals_against).sum())
    draws=int((rows.goals_for==rows.goals_against).sum())
    result={'played':count,'won':wins,'draw':draws,'lost':count-wins-draws,'points':wins*3+draws,'metrics':{}}
    for metric in METRICS:
        result['metrics'][metric]={}
        for side in ['for','against']:
            values=rows[f'{metric}_{side}'].dropna()
            result['metrics'][metric][side]={
                'total':int(values.sum()) if len(values) else None,
                'average':round(float(values.mean()),4) if len(values) else None,
                'observations':len(values),
            }
    return result


def table_rows(rows):
    """Fallback ranking is explicitly non-official; no league tiebreak claims."""
    records=[]
    for team,g in rows.groupby('team'):
        r=summarize(g)
        gf=int(g.goals_for.sum());ga=int(g.goals_against.sum())
        records.append({'team':team,'played':r['played'],'won':r['won'],'draw':r['draw'],'lost':r['lost'],
                        'points':r['points'],'goals_for':gf,'goals_against':ga,'goal_difference':gf-ga})
    records.sort(key=lambda r:(-r['points'],-r['goal_difference'],-r['goals_for'],r['team']))
    for i,r in enumerate(records,1):r['position']=i
    return records


def provider_rows(payload, identity):
    groups={}
    for standing in payload.get('standings',[]):
        # Champions uses one league stage; never mix knockout groups with it.
        if standing.get('stage') not in (None,'REGULAR_SEASON','LEAGUE_STAGE'):continue
        scope={'TOTAL':'all','HOME':'home','AWAY':'away'}.get(standing.get('type'))
        if scope is None:continue
        out=[]
        for item in standing.get('table',[]):
            team=item['team']
            out.append({'team':identity.get(team['id'],canonical_team(team['name'])),
                'position':item['position'],'played':item['playedGames'],'won':item['won'],
                'draw':item['draw'],'lost':item['lost'],'points':item['points'],
                'goals_for':item['goalsFor'],'goals_against':item['goalsAgainst'],
                'goal_difference':item['goalDifference']})
        if out:groups[scope]=out
    if not groups.get('all'):raise ValueError('No overall standings table')
    return groups


def refresh_standings(season, identity):
    token=secret('FOOTBALL_DATA_KEY')
    report=[]
    if not token:return [{'status':'retained_cache','reason':'Missing configured provider token'}]
    for league,code in LEAGUES.items():
        try:
            response=requests.get(f'https://api.football-data.org/v4/competitions/{code}/standings',
                headers={'X-Auth-Token':token},params={'season':int(season[:4])},timeout=25)
            if response.status_code!=200:raise ValueError(f'Provider HTTP {response.status_code}')
            data=response.json()
            if str(data.get('season',{}).get('startDate',''))[:4]!=season[:4]:raise ValueError('Unexpected season')
            tables=provider_rows(data,identity)
            if len({r['team'] for r in tables['all']})!=len(tables['all']):raise ValueError('Duplicate team identities')
            snapshot={'season':season,'updated_at':datetime.now(timezone.utc).isoformat(),
                      'source':'football-data.org','source_url':f'https://api.football-data.org/v4/competitions/{code}/standings',
                      'tables':tables,'current_matchday':data['season'].get('currentMatchday')}
            write_json(ARTIFACT_DIR/'team_standings'/f'{code}.json',snapshot)
            report.append({'competition':league,'status':'refreshed','teams':len(tables['all'])})
        except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
            # Never output credential-bearing request headers or provider response bodies.
            report.append({'competition':league,'status':'retained_cache','reason':type(exc).__name__})
    return report


def main(refresh=False,stats=None):
    stats=load_match_stats() if stats is None else stats
    dataset_id=stats.attrs['dataset_id'];season=season_for(today_local());stats=stats[stats.season==season].copy()
    assets=json.loads((WEB_DIR/'data/assets.json').read_text(encoding='utf-8'))
    identity={v['provider_id']:k for k,v in assets['teams'].items() if 'provider_id' in v}
    report=refresh_standings(season,identity) if refresh else []
    calendar=load_calendar(stats)
    competitions={}
    for league,code in LEAGUES.items():
        rows=stats[stats.league==league]
        roster=set(rows.team)
        if not calendar.empty:
            fixtures=calendar[(calendar.competition==league)&(calendar.date.map(season_for)==season)]
            roster.update(fixtures.home_team);roster.update(fixtures.away_team)
        cache=ARTIFACT_DIR/'team_standings'/f'{code}.json'
        snapshot=json.loads(cache.read_text(encoding='utf-8')) if cache.exists() else None
        if snapshot and snapshot.get('season')!=season:snapshot=None
        if snapshot:roster.update(r['team'] for r in snapshot['tables']['all'])
        teams=[]
        for team in sorted(roster):
            g=rows[rows.team==team]
            teams.append({'team':team,'last_stats_date':None if g.empty else str(g.date.max().date()),
                          'splits':{'all':summarize(g),'home':summarize(g[g.is_home]),'away':summarize(g[~g.is_home])}})
        local_tables={'all':table_rows(rows),'home':table_rows(rows[rows.is_home]),'away':table_rows(rows[~rows.is_home])}
        competitions[league]={'teams':teams,'statistics_through':None if rows.empty else str(rows.date.max().date()),
            'statistics_matches':int(rows.match_id.nunique()),'standings':snapshot,'recorded_tables':local_tables}
    payload={'schema_version':1,'season':season,'generated_at':datetime.now(timezone.utc).isoformat(),
             'dataset_id':dataset_id,'competitions':competitions,'refresh_report':report}
    write_json(WEB_DIR/'data/teams.json',payload)
    print(json.dumps({'season':season,'leagues':{k:len(v['teams']) for k,v in competitions.items()},'refresh':report},ensure_ascii=False))
    return payload


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--refresh-standings',action='store_true')
    main(parser.parse_args().refresh_standings)

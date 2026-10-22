"""Import a complete Champions matchday from saved public ESPN final statistics.

No network calls, training or prediction regeneration. Keep raw captures and
provider identities; validate the entire batch before updating any live file.
"""
import argparse, hashlib, json, shutil
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
from data_store import canonical_team,validate_stats
from paths import DATA_DIR,ARTIFACT_DIR,WEB_DIR
from review_matchday import save

LEAGUE='UEFA Champions League'
ESPN_NAMES={'Fenerbahce':'Fenerbahçe','Slavia Prague':'Slavia Praha',
 'Borussia Dortmund':'Dortmund','AS Roma':'Roma','PSV Eindhoven':'PSV',
 'Internazionale':'Inter','VfB Stuttgart':'Stuttgart','Atlético Madrid':'Ath Madrid'}
FIELDS={'shots':'totalShots','sot':'shotsOnTarget','fouls':'foulsCommitted','corners':'wonCorners'}
def identity(name):return canonical_team(ESPN_NAMES.get(name,name))
def count(value):
    n=float(value)
    if n<0 or not n.is_integer():raise ValueError('Invalid final count')
    return int(n)
def parse_event(event,detail,date):
    if str(detail['header']['id'])!=str(event['id']):raise ValueError('Wrong ESPN event')
    competition=detail['header']['competitions'][0]
    if not competition['status']['type']['completed'] or competition['status']['type']['name']!='STATUS_FULL_TIME':raise ValueError('Not a full-time final')
    when=pd.Timestamp(competition['date'])
    if str(when.tz_convert('America/Lima').date())!=date:raise ValueError('Wrong match date')
    sides={x['homeAway']:x for x in competition['competitors']}
    stats={x['homeAway']:x for x in detail['boxscore']['teams']}
    if set(sides)!=set(stats) or set(sides)!={'home','away'}:raise ValueError('Invalid home/away pair')
    metrics={'goals':[]};cards=[];extra={};teams=[]
    for side in ['home','away']:
        h=sides[side];s=stats[side]
        if str(h['team']['id'])!=str(s['team']['id']):raise ValueError('Stats team mismatch')
        teams.append(identity(h['team']['displayName']))
        values={x['name']:x['displayValue'] for x in s['statistics']}
        metrics['goals'].append(count(h['score']))
        for metric,key in FIELDS.items():metrics.setdefault(metric,[]).append(count(values[key]))
        yellow,red=count(values['yellowCards']),count(values['redCards'])
        cards.append((yellow,red));extra[side]=s['statistics']
    metrics['cards']=[y+r for y,r in cards]
    # Own goals can legitimately make goals exceed the team's shots on target.
    if any(metrics['sot'][i]>metrics['shots'][i] for i in [0,1]):raise ValueError('Shots on target exceed total shots')
    return {'espn_event_id':str(event['id']),'kickoff_utc':competition['date'],'home':teams[0],'away':teams[1],
      'metrics':metrics,'yellow': [c[0] for c in cards],'red':[c[1] for c in cards],
      'additional_statistics':extra,'source_url':event['links'][0]['href']}

def main(capture_dir,date,league=LEAGUE):
    capture=Path(capture_dir);archive=ARTIFACT_DIR/'daily_reviews'/date
    domestic=league!=LEAGUE
    if domestic:archive=archive/'domestic'
    code='PD' if league=='La Liga' else 'CL'
    scoreboard_name='esp.1_scoreboard.json' if domestic else 'espn_scoreboard_raw.json'
    dataset='match_stats_actualseason' if domestic else 'match_stats_champions_actualseason'
    scoreboard=json.loads((capture/scoreboard_name).read_text(encoding='utf-8'))
    provider=json.loads((capture/'football_data_matches_range.json').read_text(encoding='utf-8'))
    forecasts=json.loads((capture/'predictions_before_results.json').read_text(encoding='utf-8'))
    expected={m['fixture_id']:m for m in forecasts['matches'] if m['competition']==league and m['fecha']==date}
    api={str(m['id']):m for m in provider['matches'] if m['competition']['code']==code and str(pd.Timestamp(m['utcDate']).tz_convert('America/Lima').date())==date}
    if not expected or set(api)!=set(expected):raise ValueError('Date coverage differs between calendar and frozen forecast')
    pairs={(m['local'],m['visitante']):m for m in expected.values()}
    records=[];seen=set();rows=[];sources=[]
    hashes={n:hashlib.sha256((WEB_DIR/'data'/n).read_bytes()).hexdigest() for n in ['predictions.json','fijas.json']}
    for event in scoreboard['events']:
        detail=json.loads((capture/f"espn_{event['id']}.json").read_text(encoding='utf-8'))
        rec=parse_event(event,detail,date);key=(rec['home'],rec['away'])
        if key not in pairs:raise ValueError(f'Unexpected teams: {key}')
        m=pairs[key];fid=m['fixture_id'];final=api[fid]
        if fid in seen:raise ValueError('Duplicate match')
        seen.add(fid)
        if pd.Timestamp(rec['kickoff_utc'])!=pd.Timestamp(m['kickoff_utc']):raise ValueError('Conflicting kickoff')
        goals=final['score']['fullTime']
        if final['status']!='FINISHED' or rec['metrics']['goals']!=[goals['home'],goals['away']]:raise ValueError('Conflicting final score')
        rec.update(fixture_id=fid,date=date,round=m['jornada'],league=league)
        mid=f"{league}_2026/27_espn_{rec['espn_event_id']}";rec['match_id']=mid
        for side in [0,1]:
            row={'match_id':mid,'date':date,'league':league,'is_home':side==0,'team':key[side],'opponent':key[1-side]}
            for metric,value in rec['metrics'].items():row[metric+'_for']=value[side];row[metric+'_against']=value[1-side]
            rows.append(row)
        sources.append({'match_id':mid,'fixture_id':fid,'espn_event_id':rec['espn_event_id'],'date':date,'league':league,'round':rec['round'],
          'home':key[0],'away':key[1],'yellow_home':rec['yellow'][0],'yellow_away':rec['yellow'][1],
          'red_home':rec['red'][0],'red_away':rec['red'][1],'url':rec['source_url'],'provider':'ESPN',
          'statistics_endpoint':f"https://site.api.espn.com/apis/site/v2/sports/soccer/{'esp.1' if domestic else 'uefa.champions'}/summary?event={rec['espn_event_id']}"})
        records.append(rec)
    if seen!=set(expected):raise ValueError('Incomplete Champions matchday')
    csv_path=DATA_DIR/f'{dataset}.csv';manifest_path=DATA_DIR/f'{dataset}.sources.json';cal_path=DATA_DIR/'matches_footballdata.csv'
    old=pd.read_csv(csv_path);new=pd.DataFrame(rows)
    def check(frame):
        v=frame.copy();v['date']=pd.to_datetime(v.date);v['is_home']=v.is_home.astype(str).str.lower().map({'true':True,'false':False})
        validate_stats(v)
    check(new)
    fresh=[]
    for row in rows:
        duplicate=old[(old.date==date)&(old.league==league)&(old.team==row['team'])&(old.opponent==row['opponent'])]
        if len(duplicate)>1:raise ValueError('Duplicate fixture in existing data')
        if not duplicate.empty:
            if any(duplicate.iloc[0][k]!=row[k] for k in row if k.endswith(('_for','_against'))):raise ValueError('Conflicting existing statistics')
        else:fresh.append(row)
    combined=pd.concat([old,pd.DataFrame(fresh)],ignore_index=True)[old.columns];check(combined)
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'));known={x['match_id'] for x in manifest['sources']}
    manifest['sources'].extend(s for s in sources if s['match_id'] not in known)
    counts=combined.groupby('team').size().to_dict()
    manifest.update(as_of=date,matches=int(combined.match_id.nunique()),rows=len(combined),date_min=str(combined.date.min()),date_max=str(combined.date.max()),
       source=f'Sofascore full-match ALL statistics for the original rounds; public ESPN final boxscores through {date}.',
       scope=f'Finalised {league} fixtures recorded through {date}; coverage is recorded per source.',
       team_match_counts={k:int(v) for k,v in counts.items()},round_counts={str(k):sum(int(x['round'])==k for x in manifest['sources']) for k in sorted({int(x['round']) for x in manifest['sources']})})
    if domestic:
        manifest['coverage']=[{'league':name,'matches':int(g.match_id.nunique()),'rows':len(g),
          'round_counts':{str(k):sum(x.get('league')==name and int(x['round'])==k for x in manifest['sources'])
             for k in sorted({int(x['round']) for x in manifest['sources'] if x.get('league')==name})}}
          for name,g in combined.groupby('league')]
    calendar=pd.read_csv(cal_path)
    for rec in records:
        mask=calendar.match_id.astype(str).eq(rec['fixture_id'])
        if mask.sum()!=1:raise ValueError('Missing or duplicate calendar event')
        calendar.loc[mask,['status','home_score','away_score']]=['FINISHED',*rec['metrics']['goals']]
    backup=archive/'before_update';backup.mkdir(parents=True,exist_ok=True)
    for path in [csv_path,manifest_path,cal_path]:
        if not (backup/path.name).exists():shutil.copy2(path,backup/path.name)
    # All parsing, identity, count and coverage checks finish before mutation.
    for target,frame in [(csv_path,combined),(cal_path,calendar)]:
        tmp=target.with_suffix(target.suffix+'.tmp');frame.to_csv(tmp,index=False);tmp.replace(target)
    save(manifest_path,manifest)
    record={'date':date,'ingested_at':datetime.now(timezone.utc).isoformat(),'provider':'ESPN final boxscores, final scores cross-checked with football-data.org',
      'matches':records,'added_rows':len(combined)-len(pd.read_csv(backup/csv_path.name)),
      'added_rows_this_run':len(fresh),'dataset_matches':int(combined.match_id.nunique()),'dataset_rows':len(combined),'columns':list(combined.columns)}
    save(archive/'ingestion.json',record);save(WEB_DIR/'data'/f"actuals_{date}{'_domestic' if domestic else ''}.json",record)
    for src in capture.glob('*.json'):
        if not (archive/src.name).exists():shutil.copy2(src,archive/src.name)
    for name,digest in hashes.items():
        if hashlib.sha256((WEB_DIR/'data'/name).read_bytes()).hexdigest()!=digest:raise ValueError('Original predictions changed')
    print(json.dumps({'date':date,'matches_ingested':len(records),'added_rows':len(fresh),'dataset_matches':int(combined.match_id.nunique()),'dataset_rows':len(combined)},indent=2))
    return record

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--capture-dir',required=True);p.add_argument('--date',required=True);p.add_argument('--league',default=LEAGUE,choices=[LEAGUE,'La Liga']);a=p.parse_args();main(a.capture_dir,a.date,a.league)

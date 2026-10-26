"""Import a dated set of final boxscores with independent score verification.

Raw provider responses and frozen forecasts remain immutable. Deferred fixtures
are recorded explicitly rather than fabricated or silently dropped.
"""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from data_store import canonical_team, validate_stats
from ingest_champions_matchday import parse_event
from paths import DATA_DIR, ARTIFACT_DIR, WEB_DIR
from review_matchday import save

LEAGUES = {'esp.1':'La Liga','eng.1':'Premier League','ger.1':'Bundesliga',
           'ita.1':'Serie A','fra.1':'Ligue 1','uefa.champions':'UEFA Champions League'}
ESPN_ALIASES = {'Ipswich Town':'Ipswich','Nottingham Forest':"Nott'm Forest",
    'Alavés':'Alaves','Málaga':'Malaga','Coventry City':'Coventry',
    'Tottenham Hotspur':'Tottenham','Rayo Vallecano':'Vallecano',
    'Racing Santander':'Santander','Espanyol':'Espanol','Deportivo':'La Coruna',
    'FC Cologne':'FC Koln','SV Elversberg':'Elversberg','Hamburg SV':'Hamburg'}
ESPN_ALIASES.update({'Newcastle United':'Newcastle','Hull City':'Hull',
    'Brighton & Hove Albion':'Brighton','Leeds United':'Leeds','Celta Vigo':'Celta',
    'Real Sociedad':'Sociedad','AS Monaco':'Monaco','Stade Rennais':'Rennes',
    'TSG Hoffenheim':'Hoffenheim','Bayer Leverkusen':'Leverkusen'})

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def validate_frame(frame):
    checked=frame.copy()
    checked['date']=pd.to_datetime(checked.date)
    checked['is_home']=checked.is_home.astype(str).str.lower().map({'true':True,'false':False})
    validate_stats(checked)

def main(capture_dir, apply=False):
    capture=Path(capture_dir)
    verification=read(capture/'score_verification.json')
    frozen=read(capture/'predictions_before_results.json')
    original_hashes={name:hashlib.sha256((WEB_DIR/'data'/name).read_bytes()).hexdigest()
                     for name in ['predictions.json','fijas.json']}
    expected={str(m['fixture_id']):m for m in frozen['matches']
              if m['fecha'] in verification['dates'] and m['competition'] in LEAGUES.values()}
    if len(expected)!=sum(m['fecha'] in verification['dates'] and m['competition'] in LEAGUES.values()
                          for m in frozen['matches']):raise ValueError('Duplicate forecasts')
    rescheduled={str(x['fixture_id']):x for x in verification.get('rescheduled',[])}
    all_forecasts={str(m['fixture_id']):m for m in frozen['matches']}
    for fid,change in rescheduled.items():
        m=all_forecasts[fid]
        if (change['new_date'] not in verification['dates'] or not change.get('source_url')
                or change['original_date']!=m['fecha']
                or pd.Timestamp(change['original_kickoff_utc'])!=pd.Timestamp(m['kickoff_utc'])):
            raise ValueError('Invalid documented schedule change')
        expected[fid]=m
    pairs={(rescheduled[fid]['new_date'] if fid in rescheduled else m['fecha'],
            m['competition'],m['local'],m['visitante']):fid for fid,m in expected.items()}
    deferred={str(x['fixture_id']):x for x in verification['deferred']}
    verified={str(x['fixture_id']):x for x in verification['matches']}
    if set(expected)!=set(verified)|set(deferred) or set(verified)&set(deferred):
        raise ValueError('Incomplete verification coverage')
    records=[];seen=set();rows=[];sources=[]
    for date in verification['dates']:
        for code,league in LEAGUES.items():
            board=read(capture/date/f'{code}_scoreboard.json')
            for event in board['events']:
                rec=parse_event(event,read(capture/date/f'espn_{event["id"]}.json'),date)
                rec['home']=canonical_team(ESPN_ALIASES.get(rec['home'],rec['home']))
                rec['away']=canonical_team(ESPN_ALIASES.get(rec['away'],rec['away']))
                key=(date,league,rec['home'],rec['away'])
                if key not in pairs:raise ValueError(f'Unexpected event: {key}')
                fid=pairs[key];m=expected[fid]
                if fid in seen:raise ValueError('Duplicate event')
                seen.add(fid)
                expected_kickoff=rescheduled[fid]['new_kickoff_utc'] if fid in rescheduled else m['kickoff_utc']
                if pd.Timestamp(rec['kickoff_utc'])!=pd.Timestamp(expected_kickoff):
                    raise ValueError('Conflicting kickoff')
                v=verified[fid]
                if (v['home'],v['away'])!=(rec['home'],rec['away']) or not v['source_url']:
                    raise ValueError('Wrong independently verified identity')
                if v['goals']!=rec['metrics']['goals']:raise ValueError('Conflicting final score')
                if pd.Timestamp(m['generated_at'])>=pd.Timestamp(rec['kickoff_utc']):
                    raise ValueError('Forecast was generated after kickoff')
                mid=f"{league}_2026/27_espn_{rec['espn_event_id']}"
                rec.update(match_id=mid,fixture_id=fid,date=date,round=m['jornada'],league=league,
                    score_verification=v)
                if fid in rescheduled:rec['schedule_change']=rescheduled[fid]
                for side in [0,1]:
                    row={'match_id':mid,'date':date,'league':league,'is_home':side==0,
                         'team':key[2+side],'opponent':key[3-side]}
                    for metric,value in rec['metrics'].items():
                        row[metric+'_for']=value[side];row[metric+'_against']=value[1-side]
                    rows.append(row)
                sources.append({'match_id':mid,'fixture_id':fid,'espn_event_id':rec['espn_event_id'],
                    'date':date,'league':league,'round':rec['round'],'home':rec['home'],'away':rec['away'],
                    'yellow_home':rec['yellow'][0],'yellow_away':rec['yellow'][1],
                    'red_home':rec['red'][0],'red_away':rec['red'][1],
                    'url':rec['source_url'],'provider':'ESPN',
                    'statistics_endpoint':f'https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/summary?event={rec["espn_event_id"]}',
                    'score_verification_url':v['source_url']})
                records.append(rec)
    if seen!=set(verified):raise ValueError('Missing final boxscore')
    old_path=DATA_DIR/'match_stats_actualseason.csv'
    old=pd.read_csv(old_path);fresh=[]
    for row in rows:
        previous=old[(old.date==row['date'])&(old.league==row['league'])&
                     (old.team==row['team'])&(old.opponent==row['opponent'])]
        if len(previous)>1:raise ValueError('Existing duplicate natural identity')
        if not previous.empty:
            if any(previous.iloc[0][k]!=row[k] for k in row if k.endswith(('_for','_against'))):
                raise ValueError('Existing result conflict')
        else:fresh.append(row)
    combined=pd.concat([old,pd.DataFrame(fresh)],ignore_index=True)[old.columns]
    validate_frame(combined)
    if combined.duplicated(['date','league','team','opponent']).any():raise ValueError('Duplicate natural fixture')
    manifest_path=DATA_DIR/'match_stats_actualseason.sources.json'
    manifest=read(manifest_path)
    known={(x.get('date'),x.get('league'),canonical_team(x['home']),canonical_team(x['away']))
           for x in manifest['sources']}
    manifest['sources'].extend(s for s in sources
        if (s['date'],s['league'],s['home'],s['away']) not in known)
    manifest.update(as_of=max(str(combined.date.max()),manifest['as_of']),
        matches=int(combined.match_id.nunique()),rows=len(combined),
        date_max=str(combined.date.max()),
        source='Sofascore full-match ALL statistics for original rounds; ESPN final boxscores for subsequent updates, with independently checked scores.',
        scope=f'Finalised fixtures through {combined.date.max()}; source coverage recorded per match.')
    manifest['coverage']=[{'league':league,'matches':int(g.match_id.nunique()),'rows':len(g),
        'round_counts':{str(round_no):sum(s.get('league')==league and s.get('round')==round_no
            for s in manifest['sources']) for round_no in sorted({s['round'] for s in manifest['sources']
                if s.get('league')==league})}}
        for league,g in combined.groupby('league')]
    calendar_path=DATA_DIR/'matches_footballdata.csv'
    calendar=pd.read_csv(calendar_path)
    for r in records:
        mask=calendar.match_id.astype(str).eq(r['fixture_id'])
        if mask.sum()!=1:raise ValueError('Missing calendar event')
        calendar.loc[mask,['status','home_score','away_score']]=['FINISHED',*r['metrics']['goals']]
        stamp=pd.Timestamp(r['kickoff_utc'])
        calendar.loc[mask,['date','kickoff_time_utc']]=[str(stamp.date()),stamp.strftime('%H:%M')]
    for fid,d in deferred.items():
        mask=calendar.match_id.astype(str).eq(fid)
        if mask.sum()!=1:raise ValueError('Missing deferred calendar event')
        kickoff=pd.Timestamp(d['new_kickoff_utc'])
        if calendar.loc[mask,'status'].iloc[0]=='FINISHED':
            # An earlier review must not undo a final already verified on the
            # rescheduled date by a later review.
            if str(calendar.loc[mask,'date'].iloc[0])!=str(kickoff.date()):
                raise ValueError('Deferred event conflicts with recorded final date')
            continue
        calendar.loc[mask,['date','kickoff_time_utc','status']]=[str(kickoff.date()),kickoff.strftime('%H:%M'),'TIMED']
        calendar.loc[mask,['home_score','away_score']]=float('nan')
    summary={'dates':verification['dates'],'matches':len(records),'new_rows':len(fresh),
        'deferred':list(deferred.values()),'by_date':{day:sum(x['date']==day for x in records)
                   for day in verification['dates']},'dataset_matches':int(combined.match_id.nunique())}
    save(capture/'validated_ingestion_plan.json',summary)
    if not apply:
        print(json.dumps(summary,ensure_ascii=False,indent=2));return summary
    backup=capture/'before_update';backup.mkdir(exist_ok=True)
    for path in [old_path,manifest_path,calendar_path]:
        if not (backup/path.name).exists():shutil.copy2(path,backup/path.name)
    for target,frame in [(old_path,combined),(calendar_path,calendar)]:
        tmp=target.with_suffix(target.suffix+'.tmp');frame.to_csv(tmp,index=False);tmp.replace(target)
    save(manifest_path,manifest)
    for day in verification['dates']:
        archive=ARTIFACT_DIR/'daily_reviews'/day;archive.mkdir(parents=True,exist_ok=True)
        for name in ['predictions','fijas']:
            dst=archive/f'{name}_before_results.json'
            if not dst.exists():shutil.copy2(capture/f'{name}_before_results.json',dst)
        record={'date':day,'ingested_at':datetime.now(timezone.utc).isoformat(),
            'provider':'ESPN final boxscores; scores independently checked against Soccerbase and, when final, football-data.org',
            'matches':[r for r in records if r['date']==day],
            'deferred':[d for d in deferred.values() if d['original_date']==day],
            'added_rows_this_run':sum(r['date']==day for r in fresh),
            'scope':list(LEAGUES.values()),'capture_directory':str(capture/day)}
        save(archive/'ingestion.json',record);save(WEB_DIR/'data'/f'actuals_{day}.json',record)
    save(capture/'ingestion_summary.json',summary)
    for name,digest in original_hashes.items():
        if hashlib.sha256((WEB_DIR/'data'/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Frozen public predictions changed')
    print(json.dumps(summary,ensure_ascii=False,indent=2));return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--capture-dir',required=True);p.add_argument('--apply',action='store_true')
    args=p.parse_args();main(args.capture_dir,args.apply)

"""Ingest verified visible final statistics and evaluate frozen pre-match forecasts.

The input directory contains saved browser text, fixture links, a dated provider
result response and the ORIGINAL public predictions; no forecasts are regenerated.
"""
import argparse, csv, hashlib, json, math, re, shutil
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from data_store import canonical_team, validate_stats
from paths import DATA_DIR, ARTIFACT_DIR, WEB_DIR

METRICS=['goals','shots','sot','fouls','corners','cards']
LABELS={'shots':'Total shots','sot':'Shots on target','fouls':'Fouls','corners':'Corner kicks'}
ALIASES={'Real Racing Club':'Santander','Celta Vigo':'Celta','Real Sociedad':'Sociedad','Brighton & Hove Albion':'Brighton',
         'Leeds United':'Leeds','Nottingham Forest':"Nott'm Forest",'AS Monaco':'Monaco',
         "Borussia M'gladbach":"M'gladbach",'TSG Hoffenheim':'Hoffenheim',
         'Stade Rennais':'Rennes','Olympique Lyonnais':'Lyon','Coventry City':'Coventry',
         'Rayo Vallecano':'Vallecano','Tottenham Hotspur':'Tottenham'}

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');temp.replace(path)

def pairs(text,label,optional=False):
    lines=[s.strip() for s in text.splitlines() if s.strip()]
    found=[]
    for i,s in enumerate(lines):
        if s==label:
            pair=[int(lines[i-1]),int(lines[i+1])]
            if min(pair)<0:raise ValueError('Negative '+label)
            found.append(pair)
    if not found:
        if optional:return [0,0]
        raise ValueError('Missing '+label)
    if any(p!=found[0] for p in found):raise ValueError('Conflicting full-match '+label)
    return found[0]

def outcome(h,a):return 0 if h>a else 1 if h==a else 2

def main(capture_dir,date):
    capture=Path(capture_dir);archive=ARTIFACT_DIR/'daily_reviews'/date
    original_bytes=(WEB_DIR/'data/predictions.json').read_bytes()
    original_hash=hashlib.sha256(original_bytes).hexdigest()
    frozen=json.loads((capture/'predictions_before_results.json').read_text(encoding='utf-8'))
    original={str(m['fixture_id']):m for m in frozen['matches'] if m['fecha']==date}
    # Use the most recent archived forecast genuinely generated before kickoff.
    for file in sorted((ARTIFACT_DIR/'prediction_archive').glob('*.json')):
        for m in json.loads(file.read_text(encoding='utf-8')).get('matches',[]):
            fid=str(m.get('fixture_id'))
            if fid not in original or m['fecha']!=date:continue
            if pd.Timestamp(m['generated_at'])<pd.Timestamp(m['kickoff_utc']) and pd.Timestamp(m['generated_at'])>pd.Timestamp(original[fid]['generated_at']):original[fid]=m
    targets={t['fixture_id']:t for t in json.loads((capture/'targets.json').read_text(encoding='utf-8'))}
    api={str(m['id']):m for m in json.loads((capture/'football_data_matches_range.json').read_text(encoding='utf-8'))['matches']}
    # Keep raw provider responses intact. Explicit, evidenced corrections are
    # applied only to this review and remain attached to its audit trail.
    resolutions={}
    resolution_path=capture/'result_resolutions.json'
    if resolution_path.exists():
        for correction in json.loads(resolution_path.read_text(encoding='utf-8')):
            fid=str(correction['fixture_id']);result=api[fid]
            old=[result['score']['fullTime']['home'],result['score']['fullTime']['away']]
            if old!=correction['provider_score'] or not correction.get('source_url') or not correction.get('reason'):
                raise ValueError('Invalid evidenced score correction')
            resolved=correction['verified_score']
            if len(resolved)!=2 or any(type(x) is not int or x<0 for x in resolved):raise ValueError('Invalid verified score')
            result['score']['fullTime']={'home':resolved[0],'away':resolved[1]}
            resolutions[fid]=correction
    visible=json.loads((capture/'sofascore_visible.json').read_text(encoding='utf-8'))
    if len({v['fixture_id'] for v in visible})!=len(visible):raise ValueError('Duplicate captured fixture')
    if set(original)!=set(targets) or set(targets)!={v['fixture_id'] for v in visible}:raise ValueError('Incomplete matchday coverage')
    actuals={};additions=[];sources=[];comparisons=[]
    for entry in visible:
        fid=entry['fixture_id'];m=original[fid];t=targets[fid];result=api[fid]
        if pd.Timestamp(m['generated_at'])>=pd.Timestamp(m['kickoff_utc']):raise ValueError('Forecast was not pre-match')
        if result['status']!='FINISHED':raise ValueError('Not a final result')
        if f'{date[8:10]}/{date[5:7]}/{date[:4]}' not in entry['header']:raise ValueError('Wrong date in visible page')
        if not entry['stats'].startswith('ALL\n') or 'Match overview' not in entry['stats']:raise ValueError('Wrong statistics period')
        teams=entry['heading'].split(' live score')[0].split(' vs ')
        teams=[canonical_team(ALIASES.get(s,s)) for s in teams]
        if teams!=[m['local'],m['visitante']]:raise ValueError(f'Wrong teams: {teams} vs {[m["local"],m["visitante"]]}')
        goals=[result['score']['fullTime']['home'],result['score']['fullTime']['away']]
        if goals!=t['sofa_goals']:raise ValueError('Conflicting final scores')
        metrics={'goals':goals,**{key:pairs(entry['stats'],label) for key,label in LABELS.items()}}
        yellow=pairs(entry['stats'],'Yellow cards',optional=True);red=pairs(entry['stats'],'Red cards',optional=True)
        metrics['cards']=[yellow[i]+red[i] for i in range(2)]
        mid=f"{m['competition']}_2026/27_sofascore_{t['event_id']}"
        for side in range(2):
            row={'match_id':mid,'date':date,'league':m['competition'],'is_home':side==0,'team':teams[side],'opponent':teams[1-side]}
            for key in METRICS:row[key+'_for']=metrics[key][side];row[key+'_against']=metrics[key][1-side]
            additions.append(row)
        source={'match_id':mid,'fixture_id':fid,'league':m['competition'],'date':date,'round':m['jornada'],
                'home':teams[0],'away':teams[1],'yellow_home':yellow[0],'yellow_away':yellow[1],
                'red_home':red[0],'red_away':red[1],'url':t['url']+',tab:statistics'}
        if fid in resolutions:source['result_resolution']=resolutions[fid]
        sources.append(source);actuals[fid]={'metrics':metrics,'source':source}
        p=[m['p_home']/100,m['p_draw']/100,m['p_away']/100];o=outcome(*goals);pred=max(range(3),key=lambda i:p[i])
        score=m['marcador_top1'][0];actual_score=f'{goals[0]}-{goals[1]}'
        btts=all(g>0 for g in goals);btts_pred=m['btts']>=50;count_stats=[]
        for key in METRICS:
            forecast=[m['cruces'][key]['home'],m['cruces'][key]['away']];observed=metrics[key]
            interval=m.get('count_markets',{}).get(key,{}).get('interval_90')
            count_stats.append({'metric':key,'forecast':forecast,'actual':observed,'predicted_total':sum(forecast),'actual_total':sum(observed),
                                'absolute_error_total':abs(sum(forecast)-sum(observed)),
                                'interval_90':interval,'inside_interval':interval[0]<=sum(observed)<=interval[1] if interval else None})
        goal_lines=[]
        for line,prob in m['goal_lines'].items():
            over=sum(goals)>float(line);prediction=prob['over']>=.5
            goal_lines.append({'line':float(line),'probability_over':prob['over'],'prediction_over':prediction,'actual_over':over,'hit':prediction==over})
        comparisons.append({'fixture_id':fid,'date':date,'league':m['competition'],'home':teams[0],'away':teams[1],
            'generated_at':m['generated_at'],'kickoff_utc':m['kickoff_utc'],'probabilities':p,'predicted_outcome':pred,
            'actual_goals':goals,'actual_outcome':o,'hit_1x2':pred==o,'predicted_score':score,'actual_score':actual_score,
            'predicted_score_probability':m['marcador_top1'][1]/100,'hit_exact':score==actual_score,
            'btts_probability':m['btts']/100,'predicted_btts':btts_pred,'actual_btts':btts,'hit_btts':btts_pred==btts,
            'brier':sum((p[i]-int(i==o))**2 for i in range(3)),'log_loss':-math.log(max(p[o],1e-12)),
            'goal_lines':goal_lines,'statistics':count_stats,'source_url':source['url']})
    new=pd.DataFrame(additions);new['date']=pd.to_datetime(new.date);validate_stats(new)
    csv_path=DATA_DIR/'match_stats_actualseason.csv';old=pd.read_csv(csv_path)
    backup=archive/'before_update';backup.mkdir(parents=True,exist_ok=True)
    for path in [csv_path,DATA_DIR/'match_stats_actualseason.sources.json',DATA_DIR/'matches_footballdata.csv']:
        dest=backup/path.name
        if not dest.exists():shutil.copy2(path,dest)
    # Compare existing raw IDs and natural fixture identities before any mutation.
    for row in additions:
        duplicate=old[(old['date']==date)&(old.league==row['league'])&(old.team==row['team'])&(old.opponent==row['opponent'])]
        if not duplicate.empty:
            previous=duplicate.iloc[0]
            if any(previous[f'{metric}_{side}']!=row[f'{metric}_{side}'] for metric in METRICS for side in ['for','against']):raise ValueError('Conflicting existing final data')
    existing=set(zip(old.match_id,old.team));natural=set(zip(old['date'],old.league,old.team,old.opponent))
    fresh=[r for r in additions if (r['match_id'],r['team']) not in existing and (r['date'],r['league'],r['team'],r['opponent']) not in natural]
    combined=pd.concat([old,pd.DataFrame(fresh)],ignore_index=True)[old.columns]
    check=combined.copy();check['date']=pd.to_datetime(check.date);check['is_home']=check.is_home.astype(str).str.lower().map({'true':True,'false':False});validate_stats(check)
    manifest_path=DATA_DIR/'match_stats_actualseason.sources.json';manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    known={s['match_id'] for s in manifest['sources']};manifest['sources'].extend(s for s in sources if s['match_id'] not in known)
    for source in manifest['sources']:
        if not source.get('league'):source['league']=source['match_id'].split('_2026/27_sofascore_')[0]
    manifest.update(as_of=date,matches=int(combined.match_id.nunique()),rows=len(combined),scope=f'Finalised fixtures recorded through {date}; includes every archived prediction for this date with verified final statistics.')
    manifest['coverage']=[{'league':name,'matches':int(g.match_id.nunique()),'rows':len(g),
        'round_counts':{str(k):sum(s['league']==name and s['round']==k for s in manifest['sources']) for k in sorted({s['round'] for s in manifest['sources'] if s['league']==name})}}
        for name,g in combined.groupby('league')]
    cal_path=DATA_DIR/'matches_footballdata.csv';calendar=pd.read_csv(cal_path)
    for fid,result in api.items():
        if fid not in original:continue
        match=calendar.match_id.astype(str).eq(fid)
        if match.sum()!=1:raise ValueError('Missing or duplicate calendar fixture')
        calendar.loc[match,['status','home_score','away_score']]=['FINISHED',result['score']['fullTime']['home'],result['score']['fullTime']['away']]
    # Validate all three outputs in memory before replacing any live data file.
    temporary=csv_path.with_suffix('.csv.tmp');combined.to_csv(temporary,index=False);temporary.replace(csv_path)
    save(manifest_path,manifest)
    tmp=cal_path.with_suffix('.csv.tmp');calendar.to_csv(tmp,index=False);tmp.replace(cal_path)
    comparisons.sort(key=lambda m:(m['kickoff_utc'],m['fixture_id']))
    total=len(comparisons)
    summary={'matches':total,'hits_1x2':sum(m['hit_1x2'] for m in comparisons),'hits_exact':sum(m['hit_exact'] for m in comparisons),
             'hits_btts':sum(m['hit_btts'] for m in comparisons),'mean_log_loss':float(np.mean([m['log_loss'] for m in comparisons])),
             'mean_brier':float(np.mean([m['brier'] for m in comparisons])),
             'goals_over_25_hits':sum(next(x for x in m['goal_lines'] if x['line']==2.5)['hit'] for m in comparisons),
             'mean_absolute_errors':{key:float(np.mean([next(x for x in m['statistics'] if x['metric']==key)['absolute_error_total'] for m in comparisons])) for key in METRICS}}
    payload={'date':date,'reviewed_at':datetime.now(timezone.utc).isoformat(),'summary':summary,'matches':comparisons,
             'rule':'Latest available archived forecast generated strictly before kickoff; 1X2 argmax, BTTS and goal-line direction use 50%; full-match final statistics only.',
             'result_resolutions':list(resolutions.values()),
             'original_predictions_sha256':original_hash,'added_rows':len(combined)-len(pd.read_csv(backup/csv_path.name)),
             'added_rows_this_run':len(fresh),'dataset_rows':len(combined),'dataset_matches':int(combined.match_id.nunique())}
    save(archive/'review.json',payload);save(WEB_DIR/'data'/f'review_{date}.json',payload);save(capture/'review.json',payload)
    for name in ['sofascore_visible.json','targets.json','football_data_matches_range.json','predictions_before_results.json']:
        dest=archive/name
        if not dest.exists():shutil.copy2(capture/name,dest)
    for name in ['result_resolutions.json','fijas_before_results.json']:
        if (capture/name).exists() and not (archive/name).exists():shutil.copy2(capture/name,archive/name)
    if hashlib.sha256((WEB_DIR/'data/predictions.json').read_bytes()).hexdigest()!=original_hash:raise ValueError('Original predictions were modified')
    print(json.dumps({'added_rows':payload['added_rows'],'added_rows_this_run':len(fresh),'dataset_matches':payload['dataset_matches'],'summary':summary},ensure_ascii=False,indent=2))
    return payload

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--capture-dir',required=True);parser.add_argument('--date',required=True)
    a=parser.parse_args();main(a.capture_dir,a.date)

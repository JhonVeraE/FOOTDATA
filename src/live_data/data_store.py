"""Validated, canonical, source-aware data access. Original CSVs are immutable."""
import hashlib
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from paths import DATA_DIR
from team_name_aliases import ALIASES

SOURCES = ['match_stats_4ligas.csv', 'match_stats_actualseason.csv',
           'match_stats_champions_actualseason.csv']
METRICS = ['goals','shots','sot','fouls','corners','cards']
ALIASES.update({
    'Eintracht Frankfurt':'Frankfurt','Manchester City':'Man City',
    'Manchester United':'Man United','Man Utd':'Man United',
    'Atlético Madrid':'Ath Madrid','Atl. Madrid':'Ath Madrid','Real Betis':'Betis',
    'Paris Saint-Germain':'Paris SG','PSG':'Paris SG','Bodø/Glimt':'Bodo/Glimt',
    'FK Bodø/Glimt':'Bodo/Glimt','Club Brugge':'Club Brugge KV',
    'Sporting Clube de Portugal':'Sporting CP','Sporting':'Sporting CP',
    'PSV Eindhoven':'PSV','Galatasaray SK':'Galatasaray','SK Slavia Praha':'Slavia Praha',
    'ŠK Slovan Bratislava':'Slovan Bratislava','Slovan':'Slovan Bratislava',
    'Sabah':'Sabah FK','AEK':'AEK Athens','Shakhtar':'Shakhtar Donetsk',
    'Viking':'Viking FK','Porto':'FC Porto','Leipzig':'RB Leipzig',
    'Fenerbahçe SK':'Fenerbahçe','PAE AEK':'AEK Athens','LASK Linz':'LASK',
    'FK Shakhtar Donetsk':'Shakhtar Donetsk','Feyenoord Rotterdam':'Feyenoord',
})

def today_local():
    return pd.Timestamp(datetime.now(ZoneInfo('America/Lima')).date())

def canonical_team(name):
    if not isinstance(name,str) or not name.strip():
        raise ValueError('Missing team identity')
    name=' '.join(name.strip().split())
    return ALIASES.get(name,name)

def team_id(name):
    """Stable ID independent of providers; unknown clubs are not fuzzy matched."""
    return 'club_'+hashlib.sha256(canonical_team(name).encode()).hexdigest()[:16]

def season_for(date):
    date=pd.Timestamp(date)
    year=date.year if date.month>=7 else date.year-1
    return f'{year}/{str(year+1)[2:]}'

def before(df, cutoff):
    if cutoff is None or not str(cutoff).strip():
        raise ValueError('An explicit prediction cutoff is required')
    # Source records only have dates. Never include another result on cutoff day.
    cut=pd.Timestamp(cutoff)
    if cut.tzinfo:cut=cut.tz_convert('UTC').tz_localize(None)
    return df[pd.to_datetime(df.date,format='mixed').dt.normalize()<cut.normalize()].copy()

def validate_stats(df):
    required={'match_id','date','league','is_home','team','opponent'}|{f'{m}_{s}' for m in METRICS for s in ['for','against']}
    if missing:=required-set(df.columns):raise ValueError(f'Missing columns: {sorted(missing)}')
    if df[list(required & {'match_id','date','league','team','opponent'})].isna().any().any():raise ValueError('Missing fixture identity')
    if df.duplicated(['match_id','team']).any():raise ValueError('Duplicate team/match rows')
    # Compare aligned home/away blocks without constructing thousands of Series.
    # The same reciprocal, nonnegative-integer and missing-value rules still apply.
    if not pd.api.types.is_bool_dtype(df.is_home):raise ValueError('Invalid home/away flag')
    groups=df.groupby('match_id',sort=False).is_home.agg(['size','sum'])
    invalid=(groups['size']!=2)|(groups['sum']!=1)
    if invalid.any():raise ValueError(f'Invalid home/away pair: {groups.index[invalid][0]}')
    h=df[df.is_home].set_index('match_id');a=df[~df.is_home].set_index('match_id').reindex(h.index)
    bad=(h.team!=a.opponent)|(a.team!=h.opponent)|(h.team==a.team)|(h.date!=a.date)|(h.league!=a.league)
    if bad.any():raise ValueError(f'Non-reciprocal identity: {h.index[bad][0]}')
    for metric in METRICS:
        for side in ['for','against']:
            x=pd.to_numeric(h[f'{metric}_{side}'],errors='raise');y=pd.to_numeric(a[f'{metric}_{"against" if side=="for" else "for"}'],errors='raise')
            bad=(x.isna()!=y.isna())|(x.notna()&((x!=y)|(x<0)|(x%1!=0)))
            if bad.any():raise ValueError(f'Invalid {metric}: {h.index[bad][0]}')
    if df[['goals_for','goals_against']].isna().any().any():raise ValueError('Unknown final score')
    bad=df.sot_for>df.shots_for
    if bad.any():raise ValueError(f'SOT exceeds shots: {df.loc[bad,"match_id"].iloc[0]}')
    return df

def load_match_stats(data_dir=DATA_DIR):
    frames=[];audit=[];quality_issues=[]
    for source in SOURCES:
        p=data_dir/source
        if not p.exists():
            if source==SOURCES[0]:raise FileNotFoundError(p)
            continue
        d=pd.read_csv(p)
        d['date']=pd.to_datetime(d.date,format='mixed',errors='raise').dt.normalize()
        if (d.date>today_local()).any():raise ValueError(f'Future result in {source}')
        home=d.is_home.astype(str).str.lower().map({'true':True,'false':False})
        if home.isna().any():raise ValueError(f'Invalid is_home in {source}')
        d['is_home']=home.astype(bool)
        for c in ['team','opponent']:d[c]=d[c].map(canonical_team)
        # Retain valid scores but quarantine impossible auxiliary statistics.
        # Never silently repair raw files or infer a replacement count.
        for suffix in ['for','against']:
            bad=d[f'sot_{suffix}']>d[f'shots_{suffix}']
            for _,row in d[bad].iterrows():quality_issues.append({'source':source,'match_id':str(row.match_id),'team':row.team,'issue':f'sot_{suffix} exceeds shots_{suffix}; both excluded'})
            d.loc[bad,[f'sot_{suffix}',f'shots_{suffix}']]=np.nan
        validate_stats(d)
        d['source']=source;d['source_match_id']=d.match_id.astype(str)
        home_name=d.team.where(d.is_home,d.opponent);away_name=d.opponent.where(d.is_home,d.team)
        keys=d.date.dt.strftime('%Y-%m-%d')+'|'+d.league+'|'+home_name+'|'+away_name
        d['match_id']=keys.map(lambda x:'match_'+hashlib.sha256(x.encode()).hexdigest()[:20])
        d['team_id']=d.team.map(team_id);d['opponent_id']=d.opponent.map(team_id)
        d['season']=d.date.map(season_for)
        frames.append(d);audit.append({'file':source,'rows':len(d),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    combined=pd.concat(frames,ignore_index=True)
    # Prefer no provider silently: overlapping fixtures must agree before deduplication.
    metrics=[f'{m}_{s}' for m in METRICS for s in ['for','against']]
    duplicate=combined[combined.duplicated(['match_id','team'],keep=False)]
    for key,g in duplicate.groupby(['match_id','team']):
        if (g[metrics].nunique(dropna=False)>1).any():raise ValueError(f'Conflicting providers: {key}')
    combined=combined.drop_duplicates(['match_id','team']).sort_values(['date','match_id','is_home']).reset_index(drop=True)
    validate_stats(combined)
    combined.attrs['sources']=audit
    combined.attrs['dataset_id']=hashlib.sha256(json.dumps(audit,sort_keys=True).encode()).hexdigest()
    combined.attrs['quality_issues']=quality_issues
    return combined

def results_from_stats(stats, cutoff=None):
    df=before(stats,cutoff) if cutoff is not None else stats
    h=df[df.is_home].copy()
    return h.rename(columns={'team':'home_team','opponent':'away_team','goals_for':'home_score','goals_against':'away_score','league':'tournament'}).assign(neutral=False)

def load_calendar(stats, data_dir=DATA_DIR):
    p=data_dir/'matches_footballdata.csv'
    if not p.exists():return pd.DataFrame()
    d=pd.read_csv(p)
    for c in ['home_team','away_team']:d[c]=d[c].map(canonical_team)
    d['date']=pd.to_datetime(d.date,format='mixed',errors='raise')
    played={(r.date,r.tournament,r.home_team,r.away_team):(r.home_score,r.away_score) for r in results_from_stats(stats).itertuples()}
    for i,r in d.iterrows():
        if key:=(played.get((r.date.normalize(),r.competition,r.home_team,r.away_team))):
            d.loc[i,['status','home_score','away_score']]=['FINISHED',*key]
    d.attrs['stale_past_scheduled']=int(((d.date<today_local())&d.status.isin(['SCHEDULED','TIMED'])).sum())
    return d

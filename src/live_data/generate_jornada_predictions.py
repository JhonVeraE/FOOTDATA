"""Generate future fixtures using the validated model and all supported CSVs."""
import argparse,json
import pandas as pd
from data_store import load_match_stats,load_calendar,results_from_stats,today_local,before,canonical_team
from full_report import build_full_match_report,model_settings
from goal_model import AttackDefenceModel,ModelConfig
from paths import DATA_DIR,ARTIFACT_DIR,WEB_DIR

SUPPORTED=['La Liga','Premier League','Bundesliga','Serie A','Ligue 1','UEFA Champions League']

def proxima_jornada(calendar,competition,forced=None,as_of=None):
    if calendar.empty:return calendar
    now=pd.Timestamp(as_of) if as_of is not None else pd.Timestamp.now(tz='UTC')
    now=now.tz_localize('UTC') if now.tzinfo is None else now.tz_convert('UTC')
    d=calendar[(calendar.competition==competition)&calendar.status.isin(['SCHEDULED','TIMED'])].copy()
    d['_kickoff']=pd.to_datetime(d.date.astype(str).str[:10]+'T'+d.kickoff_time_utc.fillna('00:00')+':00Z',utc=True,errors='coerce')
    d=d[d._kickoff>now]
    if d.empty:return d
    # Earliest upcoming actual fixture rather than minimum stale matchday number.
    round_no=forced if forced is not None else d.sort_values('_kickoff').iloc[0].matchday
    return d[d.matchday==round_no].sort_values('_kickoff')

def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');tmp.replace(path)

def next_complete_round(calendar,competition,as_of=None,forced=None):
    """Return the next unstarted round plus nearby pending older fixtures.

    A postponed fixture from an old round must not replace the next full round.
    Unknown kick-off times are excluded rather than filled with invented times.
    """
    now=pd.Timestamp(as_of) if as_of is not None else pd.Timestamp.now(tz='UTC')
    now=now.tz_localize('UTC') if now.tzinfo is None else now.tz_convert('UTC')
    all_matches=calendar[calendar.competition==competition].copy()
    all_matches['_kickoff']=pd.to_datetime(all_matches.date.astype(str).str[:10]+'T'+all_matches.kickoff_time_utc.astype(str)+':00Z',utc=True,errors='coerce')
    future=all_matches[all_matches.status.isin(['SCHEDULED','TIMED'])&(all_matches._kickoff>now)].copy()
    if future.empty:return future,{}
    chosen=None
    for round_no,g in future.sort_values('_kickoff').groupby('matchday',sort=False):
        if forced is not None:
            if round_no==forced:chosen=g;break
            continue
        round_matches=all_matches[all_matches.matchday==round_no]
        started=round_matches.status.isin(['FINISHED','IN_PLAY','PAUSED','LIVE']).any() or (round_matches._kickoff<=now).any()
        if not started:chosen=g;break
    if chosen is None:return future.iloc[:0],{'reason':'No verified future unstarted round'}
    round_no=chosen.iloc[0].matchday
    expected=all_matches[all_matches.matchday==round_no]
    summary={'round':int(round_no),'matches':len(chosen),'expected_matches':len(expected),
             'first_kickoff':chosen._kickoff.min().isoformat(),'last_kickoff':chosen._kickoff.max().isoformat(),
             'unavailable_fixture_ids':[str(x) for x in expected.loc[~expected.match_id.isin(chosen.match_id),'match_id']]}
    chosen=chosen.assign(forecast_scope='next_complete_round')
    pending=future[(future.matchday<round_no)&(future._kickoff<chosen._kickoff.max()+pd.Timedelta(days=1))].assign(forecast_scope='pending_previous_round')
    return pd.concat([chosen,pending]).sort_values('_kickoff'),summary

def verified_training_cutoff(stats,provider_calendar,as_of=None):
    """An exclusive date boundary may include today only with independent FT proof."""
    now=pd.Timestamp(as_of) if as_of is not None else pd.Timestamp.now(tz='UTC')
    now=now.tz_localize('UTC') if now.tzinfo is None else now.tz_convert('UTC')
    day=now.tz_convert('America/Lima').tz_localize(None).normalize()
    today=stats[(stats.date==day)&stats.is_home]
    if today.empty:return day
    raw=provider_calendar.copy();raw['date']=pd.to_datetime(raw.date).dt.normalize()
    for col in ['home_team','away_team']:raw[col]=raw[col].map(canonical_team)
    raw['_kickoff']=pd.to_datetime(raw.date.astype(str).str[:10]+'T'+raw.kickoff_time_utc.astype(str)+':00Z',utc=True,errors='coerce')
    for r in today.itertuples():
        fixture=raw[(raw.date==r.date)&(raw.competition==r.league)&(raw.home_team==r.team)&(raw.away_team==r.opponent)]
        if len(fixture)!=1:raise ValueError('Today result lacks a unique independently verified fixture')
        f=fixture.iloc[0]
        if f.status!='FINISHED' or pd.isna(f._kickoff) or f._kickoff>=now or f.home_score!=r.goals_for or f.away_score!=r.goals_against:raise ValueError('Unverified or unfinished result dated today')
    # This is an exclusive result-date boundary, not a claim of future knowledge.
    return day+pd.Timedelta(days=1)

def main(liga_filtro=None,jornada_forzada=None,next_complete=True):
    stats=load_match_stats();provider_calendar=pd.read_csv(DATA_DIR/'matches_footballdata.csv');calendar=load_calendar(stats)
    cut=verified_training_cutoff(stats,provider_calendar)
    settings=model_settings(cut)
    model=AttackDefenceModel(ModelConfig(**settings['config'])).fit(results_from_stats(stats),cut)
    from league_core import build_elo_ratings
    from count_model import snapshot,selected_count_settings
    past=before(stats,cut);selection=selected_count_settings();count_caches={}
    if selection and cut>=pd.Timestamp(selection['active_from']):
        halves=sorted({v['config']['half_life_matches'] for v in selection['metrics'].values() if v['promoted']})
        if halves:
            for league in SUPPORTED[:-1]:count_caches[league]=snapshot(past[past.league==league],cut,halves)
    context={'past':past,'cutoff':cut,'elo':build_elo_ratings(results_from_stats(past)),'counts':count_caches}
    out={};warnings=[];coverage={}
    stale=calendar[calendar.competition.isin(SUPPORTED)&(calendar.date<cut)&calendar.status.isin(['SCHEDULED','TIMED'])]
    if len(stale):warnings.append(f'{len(stale)} past scheduled fixtures excluded; refresh the calendar')
    for league in [liga_filtro] if liga_filtro else SUPPORTED:
        if next_complete:fixtures,coverage[league]=next_complete_round(calendar,league,forced=jornada_forzada)
        else:fixtures=proxima_jornada(calendar,league,forced=jornada_forzada).assign(forecast_scope='nearest_upcoming_round')
        if fixtures.empty:
            warnings.append(f'{league}: no verified upcoming fixture');continue
        for _,fx in fixtures.iterrows():
            entry=build_full_match_report(stats,fx.home_team,fx.away_team,competition=league,fecha=str(fx.date.date()),cutoff=cut,model=model,batch_context=context)
            if 'error' in entry:warnings.append(entry['error']);continue
            key=str(fx.match_id)
            entry.update(fixture_id=key,jornada=int(fx.matchday),hora=fx.kickoff_time_utc,kickoff_utc=fx._kickoff.isoformat(),calendar_status=fx.status,forecast_scope=fx.forecast_scope)
            # Source stats and API independently describe the fixture; never replace it by a guessed pairing.
            out[key]=entry
    if not out:raise RuntimeError('No valid future predictions: previous outputs retained')
    atomic_json(DATA_DIR/'jornada_predictions.json',out)
    metadata={'generated_at':pd.Timestamp.now(tz='UTC').isoformat(),'dataset_id':stats.attrs['dataset_id'],'matches_available':int(stats.match_id.nunique()),'rows':len(stats),'sources':stats.attrs['sources'],'quality_issues':stats.attrs['quality_issues'],'warnings':warnings,'model':model.metadata(),
              'forecast_selection':'next_complete_rounds_with_nearby_pending' if next_complete else 'nearest_upcoming_round',
              'round_coverage':coverage,'training_boundary_note':'Exclusive result dates; same-day rows included only after independently verified FINISHED scores and past kickoffs.',
              'count_model_selection':selection}
    atomic_json(ARTIFACT_DIR/'prediction_run.json',metadata)
    payload={'schema_version':2,'run':metadata,'matches':list(out.values())}
    atomic_json(WEB_DIR/'data/predictions.json',payload)
    # Append-only snapshots keep predictions and input version available for later scoring.
    stamp=pd.Timestamp.now(tz='UTC').strftime('%Y%m%dT%H%M%S%fZ')
    atomic_json(ARTIFACT_DIR/'prediction_archive'/f'{stamp}.json',payload)
    from recommendations import publish_recommendations
    publish_recommendations(payload,stats)
    evaluation=ARTIFACT_DIR/'evaluation.json'
    if evaluation.exists():
        e=json.loads(evaluation.read_text(encoding='utf-8'))
        atomic_json(WEB_DIR/'data/evaluation.json',{k:v for k,v in e.items() if k!='predictions'})
    print(json.dumps({'predictions':len(out),'dataset_matches':metadata['matches_available'],'leagues':sorted({m['competition'] for m in out.values()}),'warnings':warnings},ensure_ascii=False,indent=2))
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--liga');p.add_argument('--jornada',type=int);p.add_argument('--nearest-only',action='store_true');a=p.parse_args();main(a.liga,a.jornada,next_complete=not a.nearest_only)

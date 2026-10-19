"""Refresh only verified current-season calendars; preserve prior data on errors."""
import json
import pandas as pd
from fetch_footballdata import fetch_matches,COMPETITIONS
from data_store import today_local
from paths import DATA_DIR,ARTIFACT_DIR

def main():
    target=DATA_DIR/'matches_footballdata.csv'
    old=pd.read_csv(target) if target.exists() else pd.DataFrame()
    now=today_local();start=pd.Timestamp(now.year if now.month>=7 else now.year-1,7,1)
    kept=[];report=[]
    for name,code in COMPETITIONS.items():
        if code=='BSA':
            if not old.empty:kept.append(old[old.competition==name])
            continue
        try:
            d=fetch_matches(name,code)
            if d.empty:raise ValueError('Empty response')
            dates=pd.to_datetime(d.date,errors='raise')
            d=d[(dates>=start)&(dates<start+pd.DateOffset(years=1))].copy()
            if d.empty or not (pd.to_datetime(d.date)>=now).any():raise ValueError('Response is not a current-season future calendar')
            if d.duplicated('match_id').any():raise ValueError('Duplicate fixture IDs')
            kept.append(d);report.append({'competition':name,'status':'refreshed','fixtures':len(d)})
        except Exception as e:
            if not old.empty:kept.append(old[old.competition==name])
            report.append({'competition':name,'status':'retained_prior_calendar','reason':str(e)[:180]})
    if kept:
        result=pd.concat(kept,ignore_index=True)
        pending=target.with_suffix('.csv.tmp');result.to_csv(pending,index=False);pending.replace(target)
    ARTIFACT_DIR.mkdir(parents=True,exist_ok=True)
    (ARTIFACT_DIR/'calendar_refresh.json').write_text(json.dumps({'as_of':str(now.date()),'competitions':report},indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()

"""Score the latest archived prediction made before each actual kickoff."""
import json
import numpy as np
import pandas as pd
from data_store import load_match_stats,results_from_stats,canonical_team,load_calendar
from paths import ARTIFACT_DIR
from generate_jornada_predictions import atomic_json

def main(stats=None):
    stats=load_match_stats() if stats is None else stats
    played=results_from_stats(stats)
    calendar=load_calendar(stats)
    fixture_keys={str(r.match_id):(str(r.date.date()),r.competition,r.home_team,r.away_team)
                  for r in calendar.itertuples() if r.status=='FINISHED'}
    actual={(str(r.date.date()),r.tournament,r.home_team,r.away_team):(r.home_score,r.away_score) for r in played.itertuples()}
    latest={}
    for path in sorted((ARTIFACT_DIR/'prediction_archive').glob('*.json')):
        archive=json.loads(path.read_text(encoding='utf-8'))
        for m in archive['matches']:
            generated=pd.Timestamp(m['generated_at']);kickoff=pd.Timestamp(m['kickoff_utc'])
            if generated>=kickoff:continue
            key=(m['fecha'],m['competition'],canonical_team(m['local']),canonical_team(m['visitante']))
            if key not in latest or generated>pd.Timestamp(latest[key]['generated_at']):latest[key]=m
    rows=[]
    for key,m in latest.items():
        final_key=key if key in actual else fixture_keys.get(str(m['fixture_id']))
        if final_key not in actual or final_key[1:]!=key[1:]:continue
        h,a=actual[final_key];outcome=0 if h>a else 1 if h==a else 2
        p=np.array([m['p_home'],m['p_draw'],m['p_away']])/100
        rows.append({'fixture_id':m['fixture_id'],'date':final_key[0],'forecast_original_date':m['fecha'],'model':m['model']['version'],'generated_at':m['generated_at'],'probabilities':p.tolist(),'outcome':outcome,'hit':bool(p.argmax()==outcome),'log_loss':float(-np.log(max(p[outcome],1e-12)))})
    result={'status':'scored' if rows else 'awaiting_finished_matches','scored_matches':len(rows),'accuracy':float(np.mean([r['hit'] for r in rows])) if rows else None,'log_loss':float(np.mean([r['log_loss'] for r in rows])) if rows else None,'rule':'Latest archived prediction generated before kickoff; scores from canonical dated final statistics only.','predictions':rows}
    atomic_json(ARTIFACT_DIR/'prospective_results.json',result)
    print(f'Prospective archive: {len(rows)} completed matches scored.')
    return result

if __name__=='__main__':main()

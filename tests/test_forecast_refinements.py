import sys,unittest
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src/live_data'))
from generate_jornada_predictions import next_complete_round,verified_training_cutoff
from count_model import snapshot,predict_snapshot,weighted_context,COLS
from data_store import validate_stats

def fixture(fid,day,round_no,status='TIMED',time='18:00'):
    return {'match_id':fid,'date':pd.Timestamp(day),'competition':'Test','matchday':round_no,'status':status,
            'kickoff_time_utc':time,'home_team':'A','away_team':'B','home_score':2,'away_score':1}

class ForecastRefinementTests(unittest.TestCase):
    def test_pending_round_does_not_replace_next_full_round(self):
        calendar=pd.DataFrame([fixture('old6done','2026-10-01',6,'FINISHED'),fixture('done','2026-10-17',9,'FINISHED'),fixture('pending','2026-10-19',9),
            fixture('delayed','2026-10-22',6),fixture('next1','2026-10-24',10),fixture('next2','2026-10-25',10)])
        result,coverage=next_complete_round(calendar,'Test',as_of='2026-10-19T02:00:00Z')
        self.assertEqual(coverage['round'],10)
        self.assertEqual(set(result[result.forecast_scope=='next_complete_round'].match_id),{'next1','next2'})
        self.assertEqual(set(result[result.forecast_scope=='pending_previous_round'].match_id),{'pending','delayed'})

    def test_unknown_kickoff_is_not_invented(self):
        calendar=pd.DataFrame([fixture('known','2026-10-24',10),fixture('unknown','2026-10-25',10,time=None)])
        selected,coverage=next_complete_round(calendar,'Test',as_of='2026-10-19T02:00:00Z')
        self.assertEqual(selected.match_id.tolist(),['known'])
        self.assertEqual(coverage['unavailable_fixture_ids'],['unknown'])

    def test_verified_today_result_can_train_next_fixture(self):
        stats=pd.DataFrame([{'date':pd.Timestamp('2026-10-18'),'is_home':True,'league':'Test','team':'A','opponent':'B','goals_for':2,'goals_against':1}])
        calendar=pd.DataFrame([fixture('done','2026-10-18',9,'FINISHED')])
        self.assertEqual(verified_training_cutoff(stats,calendar,'2026-10-19T02:00:00Z'),pd.Timestamp('2026-10-19'))
        calendar.loc[0,'status']='IN_PLAY'
        with self.assertRaisesRegex(ValueError,'Unverified'):verified_training_cutoff(stats,calendar,'2026-10-19T02:00:00Z')

    def test_venue_prior_is_not_the_all_venue_mean(self):
        one=np.ones(5);h={'means':np.r_[20*one,8*one],'effective':10*np.ones(10)};a={'means':np.r_[8*one,10*one],'effective':10*np.ones(10)}
        cache={'contexts':{20:{('L','H',True):h,('L','A',False):a}},'priors':{('L',True):np.r_[10*one,8*one],('L',False):np.r_[8*one,10*one]}}
        prediction=predict_snapshot(cache,'L','H','A',{'method':'venue_ratio','half_life_matches':20,'prior_matches':5})
        np.testing.assert_allclose(prediction[0],np.full(5,50/3));np.testing.assert_allclose(prediction[1],np.full(5,8.))

    def test_missing_count_uses_its_own_effective_sample(self):
        frame=pd.DataFrame({'date':pd.to_datetime(['2026-10-01','2026-10-10']),'match_id':['a','b'],**{col:[np.nan,6] for col in COLS}})
        result=weighted_context(frame,10)
        np.testing.assert_allclose(result['means'],6);np.testing.assert_allclose(result['effective'],1)
        frame['league']='L';frame['team']='A';frame['is_home']=True
        with self.assertRaisesRegex(ValueError,'post-cutoff'):snapshot(frame,'2026-10-10')

    def test_vectorized_validator_still_rejects_bad_auxiliary_data(self):
        rows=[]
        for home,team,opponent in [(True,'A','B'),(False,'B','A')]:
            row={'match_id':'m','date':pd.Timestamp('2026-10-01'),'league':'L','is_home':home,'team':team,'opponent':opponent}
            for metric in ['goals','shots','sot','corners','cards','fouls']:row[metric+'_for']=2 if home else 1;row[metric+'_against']=1 if home else 2
            rows.append(row)
        good=pd.DataFrame(rows);validate_stats(good)
        for value in [-1,.5,np.nan]:
            bad=good.astype({'cards_for':'float64'}).copy();bad.loc[0,'cards_for']=value
            with self.assertRaises(ValueError):validate_stats(bad)
        bad=good.copy();bad['is_home']=True
        with self.assertRaises(ValueError):validate_stats(bad)

if __name__=='__main__':unittest.main()

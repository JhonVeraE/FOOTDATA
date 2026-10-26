import json,sys,unittest
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/live_data'))
from data_store import validate_stats
from ingest_verified_range import main

class MondayReviewTests(unittest.TestCase):
    def test_two_final_games_have_full_reciprocal_stats(self):
        data=pd.read_csv(ROOT/'data/live/match_stats_actualseason.csv')
        day=data[data.date=='2026-10-26'].copy()
        self.assertEqual(len(day),4)
        self.assertEqual(set(day.team),{'Paris SG','Lyon','Sevilla','Osasuna'})
        self.assertFalse(day.isna().any().any())
        day['date']=pd.to_datetime(day.date);validate_stats(day)
        self.assertEqual(day[day.is_home].goals_for.tolist(),[2,2])
        self.assertEqual(day[day.is_home].goals_against.tolist(),[0,0])

    def test_rerun_does_not_duplicate_or_edit_published_forecasts(self):
        files=[ROOT/'data/live/match_stats_actualseason.csv',ROOT/'web/data/fijas.json',ROOT/'web/data/predictions.json']
        before={p:p.read_bytes() for p in files}
        self.assertEqual(main(ROOT/'data/artifacts/review_20261026',False)['new_rows'],0)
        for p,value in before.items():self.assertEqual(p.read_bytes(),value)

    def test_psg_forecast_keeps_original_date_after_rescheduling(self):
        review=json.loads((ROOT/'web/data/review_2026-10-26.json').read_text(encoding='utf-8'))
        psg=next(m for m in review['matches'] if m['fixture_id']=='559648')
        self.assertEqual(psg['forecast_original_date'],'2026-10-25')
        self.assertEqual(psg['date'],'2026-10-26')
        self.assertTrue(psg['schedule_change']['source_url'])
        picks=json.loads((ROOT/'web/data/recommendation_review_2026-10-26.json').read_text(encoding='utf-8'))
        self.assertEqual(len([x for x in picks['tiers'] if x['fixture_id']=='559648']),3)
        self.assertEqual(len(picks['matches']),2)
        # Sunday's combined bet must not be relabelled as a Monday bet.
        self.assertTrue(all(p['status']=='unavailable' for p in picks['parlays']))

if __name__=='__main__':unittest.main()

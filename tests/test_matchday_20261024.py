import hashlib,json,sys,unittest
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/live_data'))
from data_store import validate_stats
from ingest_verified_range import main

class OctoberRangeTests(unittest.TestCase):
    def test_full_statistics_reciprocal_and_unique(self):
        data=pd.read_csv(ROOT/'data/live/match_stats_actualseason.csv')
        for day,count in [('2026-10-22',0),('2026-10-23',5),('2026-10-24',19)]:
            rows=data[data.date==day].copy()
            self.assertEqual(len(rows),count*2)
            self.assertEqual(rows.match_id.nunique(),count)
            self.assertFalse(rows.isna().any().any())
            self.assertFalse(rows.duplicated(['date','league','team','opponent']).any())
            if count:
                rows['date']=pd.to_datetime(rows.date);validate_stats(rows)
    def test_ingestion_rerun_is_idempotent_without_changing_forecasts(self):
        names=['match_stats_actualseason.csv','match_stats_actualseason.sources.json','matches_footballdata.csv']
        before={n:(ROOT/'data/live'/n).read_bytes() for n in names}
        forecasts={n:(ROOT/f'web/data/{n}.json').read_bytes() for n in ['predictions','fijas']}
        result=main(ROOT/'data/artifacts/review_20261022_24',apply=False)
        self.assertEqual(result['new_rows'],0)
        for n,contents in before.items():self.assertEqual((ROOT/'data/live'/n).read_bytes(),contents)
        for name in ['predictions','fijas']:
            self.assertEqual((ROOT/f'web/data/{name}.json').read_bytes(),forecasts[name])
    def test_postponed_fixture_has_no_fake_final(self):
        calendar=pd.read_csv(ROOT/'data/live/matches_footballdata.csv')
        row=calendar[calendar.match_id==559655].iloc[0]
        self.assertEqual(row.date,'2026-10-25')
        self.assertEqual(row.kickoff_time_utc,'16:15')
        self.assertEqual(row.status,'TIMED')
        self.assertTrue(pd.isna(row.home_score) and pd.isna(row.away_score))
        review=json.loads((ROOT/'web/data/recommendation_review_2026-10-24.json').read_text(encoding='utf-8'))
        self.assertEqual(len(review['matches']),19)
        rows=[r for r in review['unique_selections'] if r['fixture_id']=='559655']
        self.assertTrue(rows)
        self.assertTrue(all(r['status']=='unverified' and 'aplazado' in r['reason'] for r in rows))
        for parlay in review['parlays']:
            if any(leg['fixture_id']=='559655' for leg in parlay['legs']):
                self.assertNotEqual(parlay['status'],'won')

if __name__=='__main__':unittest.main()

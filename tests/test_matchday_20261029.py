import json,sys,unittest
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src/live_data'))
from data_store import validate_stats
from ingest_verified_range import main

class October29ReviewTests(unittest.TestCase):
    def test_final_only_reciprocal_records(self):
        d=pd.read_csv(ROOT/'data/live/match_stats_actualseason.csv')
        for date,n in [('2026-10-27',3),('2026-10-28',5),('2026-10-29',2)]:
            rows=d[d.date==date].copy();self.assertEqual(len(rows),n*2)
            self.assertFalse(rows.isna().any().any());rows['date']=pd.to_datetime(rows.date);validate_stats(rows)
        f=d[(d.date=='2026-10-29')&(d.team=='Fiorentina')].iloc[0];self.assertEqual((f.goals_for,f.goals_against,f.shots_for,f.sot_for,f.corners_for,f.cards_for),(2,2,26,4,8,3))
    def test_late_final_settles_original_picks(self):
        r=json.loads((ROOT/'web/data/recommendation_review_2026-10-29.json').read_text(encoding='utf-8'))
        picks=[x for x in r['tiers'] if x['fixture_id']=='558551']
        self.assertEqual(len(picks),3);self.assertEqual([x['status'] for x in sorted(picks,key=lambda x:x['tier'])],['won','won','lost'])
        self.assertEqual(r['tier_summary']['settled'],6)
        c=pd.read_csv(ROOT/'data/live/matches_footballdata.csv');p=c[c.match_id==558551].iloc[0]
        self.assertEqual(p.status,'FINISHED');self.assertEqual((p.home_score,p.away_score),(2,2))
    def test_repeat_import_is_idempotent(self):
        paths=[ROOT/'data/live/match_stats_actualseason.csv',ROOT/'web/data/predictions.json',ROOT/'web/data/fijas.json']
        before={p:p.read_bytes() for p in paths}
        with self.assertRaisesRegex(ValueError,'Pending snapshot conflicts with recorded final'):main(ROOT/'data/artifacts/review_20261027_29',False)
        for p,b in before.items():self.assertEqual(p.read_bytes(),b)

if __name__=='__main__':unittest.main()

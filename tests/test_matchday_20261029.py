import json,sys,unittest
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src/live_data'))
from data_store import validate_stats
from ingest_verified_range import main

FIORENTINA='558551'

def fiorentina_final():
    c=pd.read_csv(ROOT/'data/live/matches_footballdata.csv');p=c[c.match_id.astype(str)==FIORENTINA].iloc[0]
    return p.status=='FINISHED',p

class October29ReviewTests(unittest.TestCase):
    """Fiorentina–Atalanta was in play at the first review and was settled later.

    Both states are valid; a partial score must never appear as a final and a
    final must always come with full reciprocal statistics and settled picks.
    """
    def test_final_only_reciprocal_records(self):
        d=pd.read_csv(ROOT/'data/live/match_stats_actualseason.csv');final,_=fiorentina_final()
        for date,n in [('2026-10-27',3),('2026-10-28',5),('2026-10-29',2 if final else 1)]:
            rows=d[d.date==date].copy();self.assertEqual(len(rows),n*2)
            self.assertFalse(rows.isna().any().any());rows['date']=pd.to_datetime(rows.date);validate_stats(rows)
        late=d[(d.date=='2026-10-29')&d.team.isin(['Fiorentina','Atalanta'])]
        self.assertEqual(len(late),2 if final else 0)
        if final:self.assertEqual(sorted(late.goals_for),[2,2])
    def test_pending_is_never_scored_and_final_is_settled(self):
        r=json.loads((ROOT/'web/data/recommendation_review_2026-10-29.json').read_text(encoding='utf-8'))
        picks=[x for x in r['tiers'] if x['fixture_id']==FIORENTINA];final,p=fiorentina_final()
        self.assertEqual(len(picks),3)
        if final:
            self.assertEqual((p.home_score,p.away_score),(2,2))
            self.assertTrue(all(x['status'] in ('won','lost') for x in picks))
            self.assertEqual(r['tier_summary']['settled'],6)
        else:
            self.assertTrue(all(x['status']=='unverified' for x in picks))
            self.assertEqual(r['tier_summary']['settled'],3)
            self.assertTrue(pd.isna(p.home_score) and pd.isna(p.away_score))
    def test_repeat_import_is_idempotent_or_refuses_stale_pending(self):
        paths=[ROOT/'data/live/match_stats_actualseason.csv',ROOT/'web/data/predictions.json',ROOT/'web/data/fijas.json']
        before={p:p.read_bytes() for p in paths}
        if fiorentina_final()[0]:
            with self.assertRaisesRegex(ValueError,'Pending snapshot conflicts with recorded final'):
                main(ROOT/'data/artifacts/review_20261027_29',False)
        else:self.assertEqual(main(ROOT/'data/artifacts/review_20261027_29',False)['new_rows'],0)
        for p,b in before.items():self.assertEqual(p.read_bytes(),b)

if __name__=='__main__':unittest.main()

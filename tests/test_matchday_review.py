import hashlib,json,sys,unittest
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/live_data'))
from review_matchday import pairs,outcome

class MatchdayReviewTests(unittest.TestCase):
    def test_full_match_repeated_values_must_agree(self):
        self.assertEqual(pairs('ALL\n12\nTotal shots\n8\nShots\n12\nTotal shots\n8','Total shots'),[12,8])
        with self.assertRaises(ValueError):pairs('12\nTotal shots\n8\n13\nTotal shots\n8','Total shots')
        with self.assertRaises(ValueError):pairs('ALL\nNo statistics','Fouls')

    def test_missing_zero_card_category_is_the_only_optional_case(self):
        self.assertEqual(pairs('ALL\nMatch overview','Red cards',optional=True),[0,0])
        self.assertEqual(outcome(2,1),0);self.assertEqual(outcome(1,1),1);self.assertEqual(outcome(0,2),2)

    def test_review_matches_prospective_archive_and_source_scores(self):
        p=ROOT/'data/artifacts/daily_reviews/2026-10-18'
        review=json.loads((p/'review.json').read_text(encoding='utf-8'))
        self.assertEqual(review['summary']['matches'],19)
        self.assertEqual(review['summary']['hits_1x2'],13)
        self.assertEqual(review['summary']['hits_exact'],3)
        self.assertEqual(review['summary']['hits_btts'],12)
        actuals={str(m['id']):m for m in json.loads((p/'football_data_matches_range.json').read_text(encoding='utf-8'))['matches']}
        for m in review['matches']:
            api=actuals[m['fixture_id']]
            self.assertEqual(api['status'],'FINISHED')
            self.assertEqual(m['actual_goals'],[api['score']['fullTime']['home'],api['score']['fullTime']['away']])
            self.assertLess(pd.Timestamp(m['generated_at']),pd.Timestamp(m['kickoff_utc']))
        scored=json.loads((ROOT/'data/artifacts/prospective_results.json').read_text(encoding='utf-8'))
        previous=[r for r in scored['predictions'] if r['date']=='2026-10-18']
        self.assertEqual(len(previous),19)
        self.assertEqual(sum(r['hit'] for r in previous),13)
        self.assertEqual(hashlib.sha256((p/'original_public_predictions.json').read_bytes()).hexdigest(),review['original_predictions_sha256'])

    def test_import_is_unique_reciprocal_and_attested(self):
        rows=pd.read_csv(ROOT/'data/live/match_stats_actualseason.csv')
        current=rows[rows.date=='2026-10-18']
        self.assertEqual(len(current),38)
        self.assertFalse(current.duplicated(['match_id','team']).any())
        self.assertEqual(len(rows[rows.date<='2026-10-18']),682)
        source=json.loads((ROOT/'data/live/match_stats_actualseason.sources.json').read_text(encoding='utf-8'))
        for mid,g in current.groupby('match_id'):
            self.assertEqual(len(g),2)
            self.assertEqual(g.goals_for.sum(),g.goals_against.sum())
            proof=next(s for s in source['sources'] if s['match_id']==mid)
            h=g[g.is_home].iloc[0];a=g[~g.is_home].iloc[0]
            self.assertEqual(h.cards_for,proof['yellow_home']+proof['red_home'])
            self.assertEqual(a.cards_for,proof['yellow_away']+proof['red_away'])

if __name__=='__main__':unittest.main()

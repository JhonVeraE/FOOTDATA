import json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/live_data'))
from review_recommendations import settle

class SettlementTests(unittest.TestCase):
    def test_cancelled_parma_goal_changes_under_and_btts(self):
        metrics={'goals':[0,3]}
        self.assertEqual(settle({'kind':'goals','scope':'total','line':3.5,'side':'under'},metrics)['status'],'won')
        self.assertEqual(settle({'kind':'btts','side':'yes','line':None},metrics)['status'],'lost')
    def test_away_count_uses_away_not_home(self):
        self.assertEqual(settle({'kind':'fouls','scope':'away','line':12.5,'side':'over'},{'fouls':[20,9]})['status'],'lost')
    def test_result_and_goals_require_both(self):
        c={'kind':'result_goals','side':'1X','direction':'under','line':3.5}
        self.assertEqual(settle(c,{'goals':[3,1]})['status'],'lost')
        self.assertEqual(settle(c,{'goals':[0,3]})['status'],'lost')
        self.assertEqual(settle(c,{'goals':[1,1]})['status'],'won')
    def test_missing_data_and_bookmaker_cards_not_scored_as_zero(self):
        self.assertEqual(settle({'kind':'shots','scope':'away','side':'under','line':12.5},{'shots':[9,None]})['status'],'unverified')
        self.assertEqual(settle({'kind':'cards'},{'cards':[1,2]})['status'],'unverified')
    def test_published_parlay_and_unique_markets_reconcile(self):
        p=ROOT/'data/artifacts/daily_reviews/2026-10-19/recommendation_review.json'
        if not p.exists():self.skipTest('Review not generated')
        r=json.loads(p.read_text(encoding='utf-8'))
        self.assertEqual((r['tier_summary']['won'],r['tier_summary']['lost']),(8,4))
        self.assertEqual((r['unique_summary']['won'],r['unique_summary']['lost']),(22,10))
        self.assertEqual(r['parlays'][0]['status'],'won')
        self.assertEqual(r['parlays'][1]['status'],'unavailable')
        ids=[(x['fixture_id'],x['selection_id']) for x in r['unique_selections']]
        self.assertEqual(len(ids),len(set(ids)))
    def test_ingested_day_is_reciprocal_and_correction_is_auditable(self):
        import pandas as pd
        rows=pd.read_csv(ROOT/'data/live/match_stats_actualseason.csv')
        day=rows[rows.date=='2026-10-19']
        self.assertEqual(len(day),8)
        self.assertFalse(day.duplicated(['match_id','team']).any())
        parma=day[day.team=='Parma'].iloc[0]
        self.assertEqual((parma.goals_for,parma.goals_against),(0,3))
        p=ROOT/'data/artifacts/daily_reviews/2026-10-19'
        raw=json.loads((p/'football_data_matches_range.json').read_text(encoding='utf-8'))
        original=next(m for m in raw['matches'] if str(m['id'])=='558578')
        self.assertEqual(original['score']['fullTime'],{'home':1,'away':3})
        review=json.loads((p/'review.json').read_text(encoding='utf-8'))
        self.assertEqual(review['result_resolutions'][0]['verified_score'],[0,3])

if __name__=='__main__':unittest.main()

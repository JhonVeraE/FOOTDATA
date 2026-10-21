import copy,json,sys,unittest
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/live_data'))
from ingest_champions_matchday import parse_event
from data_store import validate_stats

class ChampionsIngestionTests(unittest.TestCase):
    def setUp(self):
        self.archive=ROOT/'data/artifacts/daily_reviews/2026-10-20'
        self.event=next(e for e in json.loads((self.archive/'espn_scoreboard_raw.json').read_text(encoding='utf-8'))['events'] if e['id']=='401915399')
        self.detail=json.loads((self.archive/'espn_401915399.json').read_text(encoding='utf-8'))
    def test_complete_day_and_reciprocal_database(self):
        rows=pd.read_csv(ROOT/'data/live/match_stats_champions_actualseason.csv')
        day=rows[rows.date=='2026-10-20']
        self.assertEqual(len(day),18);self.assertEqual(day.match_id.nunique(),9)
        self.assertFalse(day.duplicated(['match_id','team']).any())
        self.assertFalse(day.isna().any().any())
        v=rows.copy();v['date']=pd.to_datetime(v.date);v['is_home']=v.is_home.astype(str).str.lower().eq('true');validate_stats(v)
        before=pd.read_csv(self.archive/'before_update/match_stats_champions_actualseason.csv')
        pd.testing.assert_frame_equal(rows[rows.date<'2026-10-20'].reset_index(drop=True),before)
    def test_stats_order_is_not_assumed_and_red_zero_is_explicit(self):
        self.detail['boxscore']['teams'].reverse()
        r=parse_event(self.event,self.detail,'2026-10-20')
        self.assertEqual((r['home'],r['away']),('Paris SG','Barcelona'))
        self.assertEqual(r['metrics']['goals'],[4,2]);self.assertEqual(r['metrics']['fouls'],[11,10])
        self.assertEqual(r['metrics']['cards'],[0,1])
    def test_wrong_team_and_nonfinal_are_rejected(self):
        self.detail['boxscore']['teams'][0]['team']['id']='wrong'
        with self.assertRaises(ValueError):parse_event(self.event,self.detail,'2026-10-20')
        self.detail=json.loads((self.archive/'espn_401915399.json').read_text(encoding='utf-8'))
        self.detail['header']['competitions'][0]['status']['type']['completed']=False
        with self.assertRaises(ValueError):parse_event(self.event,self.detail,'2026-10-20')
    def test_missing_counts_are_not_replaced_by_zero(self):
        t=self.detail['boxscore']['teams'][0]
        t['statistics']=[x for x in t['statistics'] if x['name']!='totalShots']
        with self.assertRaises(KeyError):parse_event(self.event,self.detail,'2026-10-20')

if __name__=='__main__':unittest.main()

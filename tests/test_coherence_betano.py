import sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src/live_data'))
from goal_model import score_distribution
from recommendations import coherent,stance
from market_odds import betano_quote

def pick(kind,side,line=None,scope='total',**kw):return {'kind':kind,'side':side,'line':line,'scope':scope,**kw}
M=score_distribution(.9,2.1,-.05)  # weak home side vs strong visitor (Le Havre - PSG type)

class CoherenceTests(unittest.TestCase):
    def test_team_under_goals_and_same_team_plus_handicap_conflict(self):
        under=pick('goals','under',1.5,'home');plus=pick('handicap','home',1.5)
        self.assertFalse(coherent(plus,[under],M));self.assertFalse(coherent(under,[plus],M))
    def test_same_direction_picks_are_allowed(self):
        self.assertTrue(coherent(pick('result','away'),[pick('goals','under',1.5,'home')],M))
        self.assertTrue(coherent(pick('goals','over',2.5),[pick('btts','yes')],M))
    def test_total_over_and_under_conflict(self):
        self.assertFalse(coherent(pick('goals','under',3.5),[pick('goals','over',2.5)],M))
    def test_count_stance(self):
        self.assertEqual(stance(pick('shots','under',14.5,'home'),M),(-1,0))
        self.assertFalse(coherent(pick('handicap','home',1.5),[pick('shots','under',14.5,'home')],M))
        self.assertEqual(stance(pick('fouls','over',20.5,'total'),M),(0,0))

class BetanoHandicapTests(unittest.TestCase):
    REC={'result':[2,3.75,3.55],'goals':{'2.5':[1.62,2.3]},'btts':[1.53,2.4],'home_goals':{'0.5':[1.17,4.65],'1.5':[1.75,2]},
         'away_goals':{'0.5':[1.31,3.25],'1.5':[2.45,1.52]},'euro_handicap':{-2:[7.1,5.7,1.31],-1:[3.5,4,1.85],1:[1.32,5.2,7.6],2:[1.1,9,17.5]}}
    def test_asian_half_lines_map_to_european_rows(self):
        p,odds,_=betano_quote(pick('handicap','home',1.5),self.REC);self.assertEqual(odds,1.1)    # home +1.5 = row +2 home
        p,odds,_=betano_quote(pick('handicap','away',1.5),self.REC);self.assertEqual(odds,1.31)   # away +1.5 = row -2 away
        p,odds,_=betano_quote(pick('handicap','home',-1.5),self.REC);self.assertEqual(odds,3.5)   # home -1.5 = row -1 home
        p,odds,_=betano_quote(pick('handicap','away',-1.5),self.REC);self.assertEqual(odds,7.6)   # away -1.5 = row +1 away
    def test_demargined_and_unavailable(self):
        p,odds,_=betano_quote(pick('btts','yes'),self.REC);self.assertAlmostEqual(p,(1/1.53)/(1/1.53+1/2.4))
        self.assertIsNone(betano_quote(pick('goals','over',3.5),self.REC))
        self.assertIsNone(betano_quote(pick('corners','over',9.5),self.REC))

if __name__=='__main__':unittest.main()

import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src/live_data'))
from market_odds import parse_fixtures,implied,market_probability
from recommendations import market_ok

CSV="""Div,Date,Time,HomeTeam,AwayTeam,B365H,B365D,B365A,AvgH,AvgD,AvgA,B365>2.5,B365<2.5,Avg>2.5,Avg<2.5
I1,31/10/2026,19:45,Milan,Inter,2.9,3.3,2.5,2.85,3.35,2.55,1.9,1.9,1.88,1.95
SC0,31/10/2026,15:00,Celtic,Rangers,1.8,3.8,4.2,1.8,3.8,4.2,1.7,2.1,1.7,2.1
"""

class MarketOddsTests(unittest.TestCase):
    def test_parse_keeps_covered_leagues_and_average_prices(self):
        rows=parse_fixtures(CSV,'2026-10-30T10:00:00+00:00')
        self.assertEqual(len(rows),1);r=rows[0]
        self.assertEqual((r['date'],r['league'],r['price_set'],r['home']),('2026-10-31','Serie A','average',2.85))
    def test_demargined_probabilities_sum_to_one(self):
        m=implied(parse_fixtures(CSV,'2026-10-30T10:00:00+00:00')[0])
        self.assertAlmostEqual(sum(m['result'].values()),1)
        self.assertAlmostEqual(sum(m['goals_2.5'].values()),1)
        self.assertGreater(m['margin_1x2'],0)
    def test_only_derivable_markets_get_a_price(self):
        m=implied(parse_fixtures(CSV,'2026-10-30T10:00:00+00:00')[0])
        base={'line':None,'scope':'total'}
        self.assertIsNotNone(market_probability({**base,'kind':'double_chance','side':'1X'},m))
        self.assertIsNotNone(market_probability({'kind':'goals','side':'over','line':2.5,'scope':'total'},m))
        self.assertIsNone(market_probability({'kind':'goals','side':'over','line':3.5,'scope':'total'},m))
        self.assertIsNone(market_probability({'kind':'btts','side':'yes','line':None,'scope':'total'},m))
    def test_market_disagreement_removes_pick_without_changing_probability(self):
        item={'probability':.80,'market_probability':.70}
        self.assertFalse(market_ok(item,.78));self.assertEqual(item['probability'],.80)
        self.assertTrue(market_ok({'probability':.80,'market_probability':None},.78))
        self.assertTrue(market_ok({'probability':.80,'market_probability':.79},.78))

if __name__=='__main__':unittest.main()

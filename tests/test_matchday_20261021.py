import json
import unittest
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


class CompletedMatchdayTests(unittest.TestCase):
    def test_ten_matches_have_full_reciprocal_statistics(self):
        total = 0
        for name, expected in [('match_stats_actualseason.csv', 1),
                               ('match_stats_champions_actualseason.csv', 9)]:
            data = pd.read_csv(ROOT/'data/live'/name)
            day = data[data.date == '2026-10-21']
            self.assertEqual(day.match_id.nunique(), expected)
            self.assertEqual(len(day), expected * 2)
            self.assertFalse(day.isna().any().any())
            self.assertFalse(day.duplicated(['match_id', 'team']).any())
            for _, g in day.groupby('match_id'):
                a, b = g.iloc[0], g.iloc[1]
                self.assertEqual(a.team, b.opponent)
                for metric in ['goals', 'shots', 'sot', 'fouls', 'corners', 'cards']:
                    self.assertEqual(a[metric+'_for'], b[metric+'_against'])
            total += expected
        self.assertEqual(total, 10)

    def test_review_reconciles_with_saved_selections(self):
        d = json.loads((ROOT/'web/data/recommendation_review_2026-10-21.json').read_text(encoding='utf-8'))
        self.assertEqual(len(d['matches']), 10)
        self.assertEqual((d['tier_summary']['won'], d['tier_summary']['lost']), (11, 1))
        self.assertEqual((d['unique_summary']['won'], d['unique_summary']['settled']), (30, 36))
        self.assertEqual([(p['size'], p['status']) for p in d['parlays']], [(3, 'won'), (4, 'won')])
        madrid = [x for x in d['tiers'] if x['fixture_id'] == '575370']
        self.assertEqual(len(madrid), 3)
        self.assertTrue(all(x['status'] == 'won' for x in madrid))
        self.assertTrue(any('más de 2,5' in x['label'] and 'gana' in x['label'].lower() for x in madrid))


if __name__ == '__main__':
    unittest.main()

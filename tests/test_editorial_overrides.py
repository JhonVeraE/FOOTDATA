import copy,json,sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/live_data'))
from recommendations import apply_editorial_overrides
from data_store import load_match_stats
from goal_model import score_distribution

class EditorialOverrideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pred=json.loads((ROOT/'web/data/predictions.json').read_text(encoding='utf-8'))
        cls.original=json.loads((ROOT/'data/artifacts/recommendation_archive/20261019T054246228443Z.json').read_text(encoding='utf-8'))
        cls.overrides=json.loads((ROOT/'data/live/recommendation_overrides.json').read_text(encoding='utf-8'))['overrides']
        cls.stats=load_match_stats()
    def test_joint_probability_and_only_requested_slot_changes(self):
        data=copy.deepcopy(self.original)
        apply_editorial_overrides(data,self.pred,self.stats,as_of='2026-10-21T16:00:00Z',overrides=self.overrides)
        old=next(m for m in self.original['matches'] if m['fixture_id']=='575370')
        new=next(m for m in data['matches'] if m['fixture_id']=='575370')
        self.assertEqual(new['tiers'][:2],old['tiers'][:2])
        self.assertEqual(new['markets'],old['markets'])
        self.assertEqual([m for m in data['matches'] if m['fixture_id']!='575370'],[m for m in self.original['matches'] if m['fixture_id']!='575370'])
        c=new['tiers'][2]['selection'];m=next(m for m in self.pred['matches'] if m['fixture_id']=='575370')
        matrix=score_distribution(m['lam_home'],m['lam_away'],m['model']['rho']);h,a=np.indices(matrix.shape)
        self.assertAlmostEqual(c['probability'],float(matrix[(h>a)&(h+a>2.5)].sum()))
        self.assertNotAlmostEqual(c['probability'],m['p_home']/100*m['goal_lines']['2.5']['over'])
        self.assertNotIn('observed_quote',c);self.assertNotIn('odds_audit',c)
        self.assertTrue(c['editorial_override'])
    def test_expired_override_does_not_rewrite_history(self):
        data=copy.deepcopy(self.original)
        apply_editorial_overrides(data,self.pred,self.stats,as_of='2026-10-22T00:00:00Z',overrides=self.overrides)
        self.assertEqual(data,self.original)
    def test_wrong_opponent_is_rejected(self):
        overrides=copy.deepcopy(self.overrides);overrides[0]['away']='Another club'
        with self.assertRaises(ValueError):apply_editorial_overrides(copy.deepcopy(self.original),self.pred,self.stats,as_of='2026-10-21T16:00:00Z',overrides=overrides)

if __name__=='__main__':unittest.main()

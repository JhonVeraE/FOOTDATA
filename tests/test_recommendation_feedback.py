import sys,unittest,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src/live_data'))
from recommendation_feedback import annotate,signature
from recommendations import supported,recent_support

class FeedbackTests(unittest.TestCase):
    def candidate(self):
        return {'kind':'goals','scope':'home','side':'over','line':1.5,'probability':.8,
          'fair_odds':1.25,'support_gap':.1,'evidence':{'matches':10,'contexts':[
          {'matches':5,'hits':3,'current_hit_streak':0,'recent_matches':3,'recent_hits':1},
          {'matches':5,'hits':4,'current_hit_streak':1,'recent_matches':3,'recent_hits':2}]}}
    def record(self,hit=False,date='2026-10-20',reviewed='2026-10-21T01:00:00Z'):
        return {'date':date,'reviewed_at':reviewed,'home':'Club','away':'Other',
                'selection':self.candidate(),'probability':.8,'hit':hit}
    def report(self):return {'local':'Club','visitante':'Opponent','cutoff':'2026-10-27',
                           'fecha':'2026-10-30','generated_at':'2026-10-26T23:00:00Z'}
    def test_one_failure_is_not_a_blacklist_and_probability_unchanged(self):
        c=self.candidate();annotate([c],self.report(),[self.record()])
        self.assertFalse(c['performance_review']['repeat_failure_block'])
        self.assertEqual(c['probability'],.8)
    def test_two_failures_block_until_recent_support_returns(self):
        c=self.candidate();annotate([c],self.report(),[self.record(),self.record(date='2026-10-24')])
        self.assertFalse(supported(c));self.assertFalse(recent_support(c))
        for v in c['evidence']['contexts']:v.update(current_hit_streak=2,recent_hits=2)
        annotate([c],self.report(),[self.record(),self.record(date='2026-10-24')])
        self.assertTrue(supported(c));self.assertTrue(recent_support(c))
    def test_future_and_unreviewed_results_cannot_change_ranking(self):
        c=self.candidate();annotate([c],self.report(),[
            self.record(date='2026-10-28'),self.record(reviewed='2026-10-27T01:00:00Z')])
        self.assertEqual(c['performance_review']['family_observations'],0)
    def test_own_market_signature_survives_a_venue_change(self):
        c=self.candidate();a=copy.deepcopy(c);a['scope']='away'
        self.assertEqual(signature(c,'Club','Other'),signature(a,'NewOpponent','Club'))
        a['line']=2.5;self.assertNotEqual(signature(c,'Club','Other'),signature(a,'NewOpponent','Club'))

if __name__=='__main__':unittest.main()

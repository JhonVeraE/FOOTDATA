import copy
import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/live_data'))
from recommendations import historical_context,candidates,make_match,choose_parlay,build_payload,event_values,evidence,supported,LEVELS,preferred_selection
from goal_model import market_summary,score_distribution


def report():
    market=market_summary(1.8,.9,-.02)
    return {'fixture_id':'one','local':'H','visitante':'A','competition':'Test','fecha':'2026-10-24','cutoff':'2026-10-19','generated_at':'2026-10-19T03:00:00Z','kickoff_utc':'2026-10-24T19:00:00Z','calendar_status':'TIMED',
            'lam_home':1.8,'lam_away':.9,'model':{'rho':-.02},'p_home':market['p_home_win']*100,'p_draw':market['p_draw']*100,'p_away':market['p_away_win']*100,'quality':{'effective_sample_min':20},'data_warnings':[],
            'count_markets':{'corners':{'status':'estimate','mean':10.,'dispersion':0.},'cards':{'status':'insufficient_data','mean':None}}}


def stats():
    rows=[]
    for team,home in [('H',True),('A',False)]:
        for day in range(1,8):
            rows.append({'team':team,'opponent':'Opponent','is_home':home,'date':pd.Timestamp(f'2026-10-{day:02}'),'match_id':team+str(day),'league':'Test','goals_for':2 if home else 1,'goals_against':1 if home else 2,'corners_for':5,'corners_against':4,'cards_for':np.nan,'cards_against':np.nan})
    return pd.DataFrame(rows)


class RecommendationTests(unittest.TestCase):
    def test_supported_classic_markets_not_displaced_by_many_statistic_lines(self):
        classic={'kind':'double_chance','probability':.80,'support_gap':.03}
        counts=[{'kind':'shots','probability':.82,'support_gap':0} for _ in range(100)]
        self.assertIs(preferred_selection(counts+[classic],.82),classic)
        self.assertIn(preferred_selection(counts,.82),counts)

    def test_streak_is_descriptive_and_does_not_change_model_probability(self):
        data=stats();h=data.iloc[:5].copy();a=data.iloc[7:12].copy()
        h['goals_for']=[0,2,0,2,2]
        candidate={'kind':'goals','scope':'home','side':'over','line':1.5}
        ev=evidence(candidate,[h,a],report())
        self.assertEqual(ev['contexts'][0]['current_hit_streak'],2)
        self.assertEqual(ev['contexts'][0]['hits'],3)
        r=report();before=r['p_home'];make_match(r,data);self.assertEqual(r['p_home'],before)

    def test_handicap_half_lines_settle_by_margin(self):
        r=report();options=candidates(r,historical_context(stats(),r));matrix=score_distribution(1.8,.9,-.02);h,a=np.indices(matrix.shape)
        for side,margin in [('home',h-a),('away',a-h)]:
            for line in [-2.5,-1.5,1.5,2.5]:
                pick=next(c for c in options if c['kind']=='handicap' and c['side']==side and c['line']==line)
                self.assertAlmostEqual(pick['probability'],float(matrix[margin+line>0].sum()))
        values=event_values(stats().iloc[:3],{'kind':'handicap','side':'home','line':-1.5},True)
        self.assertFalse(values.any())  # 2-1 is not enough to cover -1.5.

    def test_double_chance_uses_published_outcome_probabilities(self):
        r=report();r.update(p_home=60,p_draw=25,p_away=15)
        picks={c['side']:c for c in candidates(r,historical_context(stats(),r)) if c['kind']=='double_chance'}
        self.assertAlmostEqual(picks['1X']['probability'],.85);self.assertAlmostEqual(picks['X2']['probability'],.4)
        self.assertAlmostEqual(picks['12']['probability'],.75)

    def test_poisson_lines_and_missing_counts(self):
        r=report();options=candidates(r,historical_context(stats(),r))
        self.assertFalse(any(c['kind']=='cards' for c in options))
        from scipy.stats import poisson
        over=next(c for c in options if c['kind']=='corners' and c['line']==9.5 and c['side']=='over')
        self.assertAlmostEqual(over['probability'],poisson.sf(9,10))
        self.assertEqual(over['evidence']['matches'],10)

    def test_cutoff_locality_and_league_prevent_leakage(self):
        r=report();data=stats();baseline=make_match(r,data)
        bad=data.iloc[[0]].copy();bad['date']=pd.Timestamp(r['cutoff']);bad['goals_for']=100
        other=bad.copy();other['date']=pd.Timestamp('2026-10-10');other['league']='Other'
        added=pd.concat([data,bad,other],ignore_index=True)
        self.assertEqual(baseline,make_match(r,added))
        contexts=historical_context(data,r)
        self.assertEqual([len(v) for v in contexts],[5,5])
        self.assertTrue(contexts[0].is_home.all());self.assertFalse(contexts[1].is_home.any())

    def test_levels_are_ordered_and_do_not_invent_sparse_picks(self):
        r=report();m=make_match(r,stats());selections=[t['selection'] for t in m['tiers']]
        available=[c for c in selections if c]
        self.assertTrue(available);self.assertEqual(len({c['kind'] for c in available}),len(available))
        self.assertEqual([c['probability'] for c in available],sorted([c['probability'] for c in available],reverse=True))
        for selection,level in zip(selections,LEVELS):
            if selection:self.assertTrue(supported(selection));self.assertTrue(level[2]<=selection['probability']<level[3])
        empty=make_match(r,stats().iloc[:0]);self.assertTrue(all(t['selection'] is None for t in empty['tiers']))
        self.assertIsNone(empty['parlay_selection'])

    def test_accumulator_uses_distinct_future_teams_and_no_padding(self):
        base=make_match(report(),stats());base['parlay_selection']={'probability':.8}
        pool=[]
        for i in range(4):
            m=copy.deepcopy(base);m.update(fixture_id=str(i),home='H'+str(i),away='A'+str(i));pool.append(m)
        combo=choose_parlay(pool,3,'2026-10-20T00:00:00Z');self.assertEqual(len(combo['legs']),3);self.assertAlmostEqual(combo['probability'],.8**3)
        pool[-1]['home']=pool[0]['home'];self.assertEqual(choose_parlay(pool,4,'2026-10-20T00:00:00Z')['status'],'insufficient_matches')
        pool[0]['kickoff_utc']='2026-10-19T19:00:00Z';self.assertEqual(choose_parlay(pool,3,'2026-10-25T00:00:00Z')['legs'],[])

    def test_local_date_and_started_fixtures(self):
        r=report();r['kickoff_utc']='2026-10-25T02:00:00Z';payload={'run':{'dataset_id':'test','generated_at':r['generated_at']},'matches':[r]}
        output=build_payload(payload,stats(),as_of='2026-10-24T12:00:00Z')
        self.assertEqual(output['days'][0]['date_lima'],'2026-10-24')
        self.assertEqual(output['days'][0]['parlays'][0]['status'],'insufficient_matches')
        self.assertEqual(build_payload(payload,stats(),as_of=r['kickoff_utc'])['matches'],[])

    def test_unknown_teams_excluded_from_accumulator(self):
        r=report();r['data_warnings']=['Equipos sin historial: fuerza contraída al promedio, no evaluada específicamente.']
        self.assertIsNone(make_match(r,stats())['parlay_selection'])
        r['data_warnings']=['Estadísticas descriptivas combinan competiciones; no son promedios propios de esta copa.']
        self.assertIsNotNone(make_match(r,stats())['parlay_selection'])

    def test_direct_encounter_not_double_counted_in_combined_support(self):
        data=stats();h=data.iloc[[0]].copy();a=data.iloc[[7]].copy();h['match_id']='same';a['match_id']='same'
        result=evidence({'kind':'goals','side':'over','line':2.5},[h,a],report())
        self.assertEqual([v['matches'] for v in result['contexts']],[1,1])
        self.assertEqual(result['matches'],1);self.assertEqual(result['hits'],1)

    def test_zero_or_minority_support_is_never_recommended(self):
        c={'probability':.58,'fair_odds':1/.58,'support_gap':.05,'evidence':{'matches':10,'contexts':[{'matches':5,'hits':5},{'matches':5,'hits':0}]}}
        self.assertFalse(supported(c));c['evidence']['contexts'][1]['hits']=2;self.assertFalse(supported(c))
        c['evidence']['contexts'][1]['hits']=3;self.assertTrue(supported(c))
        c['price_status']='below_reference';self.assertFalse(supported(c))

    def test_combined_market_is_joint_not_independent_product(self):
        r=report();options=candidates(r,historical_context(stats(),r));m=score_distribution(1.8,.9,-.02);h,a=np.indices(m.shape)
        pick=next(c for c in options if c['kind']=='result_goals' and c['side']=='home' and c['line']==1.5 and c['direction']=='over')
        self.assertAlmostEqual(pick['probability'],m[(h>a)&(h+a>1.5)].sum())
        self.assertFalse(any(c['kind']=='goals' and c['line']==.5 for c in options))
        self.assertFalse(any(c['kind']=='cards' for c in options))

    def test_team_shots_support_uses_opponent_conceded_not_opponent_attack(self):
        h=stats().iloc[:5].copy();a=stats().iloc[7:12].copy();h['shots_for']=15;h['shots_against']=7;a['shots_for']=20;a['shots_against']=8
        candidate={'kind':'shots','scope':'home','side':'over','line':10.5}
        ev=evidence(candidate,[h,a],report());self.assertEqual([v['hits'] for v in ev['contexts']],[5,0])
        self.assertEqual(ev['contexts'][1]['measure'],'permitido al rival')

    def test_odds_expire_and_must_match_fixture_kickoff(self):
        r=report();q={'kickoff_utc':r['kickoff_utc'],'observed_at':'2026-10-19T03:00:00Z','odds':2.0}
        quote_map={('one','double_chance:total:1X:None:'):q}
        def find(as_of):return next(c for c in candidates(r,historical_context(stats(),r),quotes=quote_map,as_of=as_of) if c['kind']=='double_chance' and c['side']=='1X')
        self.assertIn('observed_quote',find('2026-10-19T03:10:00Z'));self.assertNotIn('observed_quote',find('2026-10-19T03:16:00Z'))
        q['kickoff_utc']='2026-10-25T19:00:00Z';self.assertNotIn('observed_quote',find('2026-10-19T03:10:00Z'))

    def test_unoffered_line_not_recommended_in_fully_observed_market(self):
        r=report();quote={'kickoff_utc':r['kickoff_utc'],'observed_at':'2026-10-19T03:00:00Z','odds':2.0,'kind':'double_chance','scope':'total','complete_market_snapshot':True}
        options=candidates(r,historical_context(stats(),r),quotes={('one','double_chance:total:1X:None:'):quote},as_of='2026-10-19T03:10:00Z')
        absent=next(c for c in options if c['kind']=='double_chance' and c['side']=='12')
        self.assertEqual(absent['price_status'],'not_in_observed_lines');self.assertFalse(supported(absent))


if __name__=='__main__':unittest.main()

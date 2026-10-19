"""Behavioral regression tests for data integrity, time leakage and outputs."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/live_data'))
from data_store import load_match_stats,before,results_from_stats,canonical_team,team_id,validate_stats,load_calendar
from goal_model import AttackDefenceModel,ModelConfig,score_distribution,market_summary
from full_report import build_full_match_report,model_settings
from generate_jornada_predictions import proxima_jornada
from team_profile import _decay_weighted,build_team_profile
from league_core import build_elo_ratings

class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stats=load_match_stats();cls.results=results_from_stats(cls.stats)
        cls.cut=pd.Timestamp('2026-10-18');cls.settings=model_settings(cls.cut)
        cls.model=AttackDefenceModel(ModelConfig(**cls.settings['config'])).fit(cls.results,cls.cut)

    def test_all_new_sources_loaded_once(self):
        self.assertEqual(len(self.stats),sum(s['rows'] for s in self.stats.attrs['sources']))
        self.assertEqual(len(self.stats),2*self.stats.match_id.nunique())
        self.assertGreaterEqual(self.stats[self.stats.source=='match_stats_champions_actualseason.csv'].match_id.nunique(),36)
        self.assertFalse(self.stats.duplicated(['date','league','team','opponent']).any())
        self.assertEqual(self.stats.groupby('match_id').size().unique().tolist(),[2])

    def test_canonical_identity_has_no_fuzzy_guess(self):
        from team_name_aliases import normalize_team_name
        self.assertEqual(canonical_team('Eintracht Frankfurt'),'Frankfurt')
        self.assertEqual(team_id('FC Barcelona'),team_id('Barcelona'))
        self.assertEqual(normalize_team_name('Le Mans FC',{'Lens'}),'Le Mans FC')

    def test_missing_cutoff_and_same_day_results(self):
        with self.assertRaises(ValueError):before(self.stats,None)
        filtered=before(self.stats,'2026-10-17T23:59:00Z')
        self.assertTrue((filtered.date<pd.Timestamp('2026-10-17')).all())

    def test_future_results_cannot_change_past_fit(self):
        old=self.results[self.results.date<'2026-09-01']
        a=AttackDefenceModel(ModelConfig(365,3,True)).fit(old,'2026-09-01')
        changed=self.results.copy();changed.loc[changed.date>='2026-09-01','home_score']=50
        b=AttackDefenceModel(ModelConfig(365,3,True)).fit(changed,'2026-09-01')
        np.testing.assert_allclose(a.theta,b.theta,rtol=0,atol=0)
        self.assertEqual(a.rho,b.rho)

    def test_report_rejects_future_model(self):
        with self.assertRaisesRegex(ValueError,'post-cutoff'):
            build_full_match_report(self.stats,'Barcelona','Real Madrid','La Liga','2026-09-01',model=self.model)

    def test_probabilities_and_no_score_clipping(self):
        for h,a,rho in [(1.4,.8,-.1),(.05,5,.2),(9,8,-.2)]:
            m=score_distribution(h,a,rho)
            self.assertTrue((m>=0).all());self.assertAlmostEqual(m.sum(),1.)
            s=market_summary(h,a,rho)
            self.assertAlmostEqual(s['p_home_win']+s['p_draw']+s['p_away_win'],1.)
            for p in s['goal_lines'].values():self.assertAlmostEqual(sum(p.values()),1.)
        self.assertGreater(score_distribution(9,8).shape[0],9)

    def test_invalid_fixture_pairs_raise(self):
        d=self.stats.head(2).copy();d.loc[d.index[0],'opponent']='Wrong team'
        with self.assertRaises(ValueError):validate_stats(d)

    def test_auxiliary_missing_values_are_not_zero_or_nan(self):
        d=self.stats[self.stats.team=='Barcelona'].tail(8).copy();d.loc[d.index[-1],'shots_for']=np.nan
        result=_decay_weighted(d)
        self.assertTrue(np.isfinite(result['shots_for']))
        self.assertEqual(result['coverage']['shots_for'],7)
        self.assertGreater(result['shots_for'],0.)

    def test_corrupt_historical_auxiliary_stats_are_quarantined(self):
        d=self.stats[(self.stats.team=='West Ham')&(self.stats.date==pd.Timestamp('2021-08-15'))].iloc[0]
        self.assertTrue(pd.isna(d.shots_for));self.assertTrue(pd.notna(d.goals_for))
        self.assertTrue(self.stats.attrs['quality_issues'])

    def test_forecast_has_future_fixtures_only(self):
        calendar=load_calendar(self.stats)
        for league in ['La Liga','UEFA Champions League']:
            future=proxima_jornada(calendar,league,as_of='2026-10-18T00:00:00Z')
            self.assertGreater(len(future),0)
            self.assertTrue((future._kickoff>pd.Timestamp('2026-10-18',tz='UTC')).all())
        old=calendar.copy();old['date']=pd.Timestamp('2020-01-01');old['status']='SCHEDULED'
        self.assertTrue(proxima_jornada(old,'La Liga',as_of='2026-10-18').empty)

    def test_all_target_calendar_teams_have_explicit_identity(self):
        calendar=load_calendar(self.stats)
        for league in ['La Liga','Premier League','Bundesliga','Serie A','Ligue 1','UEFA Champions League']:
            fixtures=proxima_jornada(calendar,league,as_of='2026-10-18T00:00:00Z')
            unknown=(set(fixtures.home_team)|set(fixtures.away_team))-set(self.stats.team)
            self.assertEqual(unknown,set(),f'{league}: unresolved identity')

    def test_report_contract_and_h2h_uniqueness(self):
        r=build_full_match_report(self.stats,'Barcelona','Real Madrid','La Liga','2026-10-20',cutoff=self.cut,model=self.model)
        self.assertAlmostEqual(r['p_home']+r['p_draw']+r['p_away'],100.)
        self.assertEqual(r['h2h_total_partidos'],len({d['fecha'] for d in r['h2h_ida']['detalle']}))
        self.assertEqual(r['model']['latest_training_result'],'2026-10-17')
        self.assertIn('elo_home',r);self.assertIn('marcador_top1',r)
        self.assertLessEqual(r['forma_home']['temporada']['partidos'],10)
        self.assertFalse(r['h2h_adjusts_goals']);json.dumps(r,allow_nan=False)
        from build_excel_avanzado import build_match_excel
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'report.xlsx';build_match_excel(dict(r,jornada=10,hora='18:00'),str(p))
            from openpyxl import load_workbook
            wb=load_workbook(p,read_only=True);self.assertEqual(wb.active['A1'].value,'Barcelona  vs  Real Madrid');wb.close()

    def test_unknown_champions_club_is_explicit(self):
        r=build_full_match_report(self.stats,'Unknown FC','Barcelona','UEFA Champions League','2026-10-20',cutoff=self.cut,model=self.model)
        self.assertTrue(r['data_warnings']);self.assertFalse(r['confianza']['calibrated'])
        self.assertEqual(r['temperature'],1.)

    def test_undated_elo_rejected(self):
        d=self.results.head(5).copy();d.loc[d.index[0],'date']=pd.NaT
        with self.assertRaises(ValueError):build_elo_ratings(d)

    def test_api_cache_expires(self):
        import api_client
        with tempfile.TemporaryDirectory() as temp,patch.object(api_client,'CACHE_DIR',temp),patch.object(api_client,'API_KEY','test-only'):
            p=Path(temp)/(api_client._cache_key('fixtures',{'league':1})+'.json')
            p.write_text(json.dumps({'response':['stale']}))
            import os,time
            os.utime(p,(time.time()-100,time.time()-100))
            response=unittest.mock.Mock(status_code=200);response.json.return_value={'response':['new'],'errors':{}}
            with patch.object(api_client.requests,'get',return_value=response) as request:
                self.assertEqual(api_client.get('fixtures',{'league':1},ttl_seconds=1),['new']);request.assert_called_once()

class ArchiveTests(unittest.TestCase):
    def test_latest_prematch_snapshot_only(self):
        import score_archive
        fake=pd.DataFrame([{'date':pd.Timestamp('2026-10-10'),'match_id':'m1','is_home':True,'team':'A','opponent':'B','goals_for':1,'goals_against':0,'league':'Test'}])
        base={'fecha':'2026-10-10','competition':'Test','local':'A','visitante':'B','fixture_id':'1','kickoff_utc':'2026-10-10T18:00:00Z','model':{'version':'test'},'p_home':60.,'p_draw':20.,'p_away':20.}
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);archive=folder/'prediction_archive';archive.mkdir()
            entries=[dict(base,generated_at='2026-10-10T12:00:00Z',p_home=50.,p_draw=30.),dict(base,generated_at='2026-10-10T17:00:00Z'),dict(base,generated_at='2026-10-10T19:00:00Z',p_home=99.,p_draw=.5,p_away=.5)]
            for i,entry in enumerate(entries):(archive/f'{i}.json').write_text(json.dumps({'matches':[entry]}))
            with patch.object(score_archive,'ARTIFACT_DIR',folder),patch.object(score_archive,'load_match_stats',return_value=fake):result=score_archive.main()
            self.assertEqual(result['scored_matches'],1)
            self.assertEqual(result['predictions'][0]['generated_at'],'2026-10-10T17:00:00Z')
            self.assertAlmostEqual(result['log_loss'],-np.log(.6))

if __name__=='__main__':unittest.main()

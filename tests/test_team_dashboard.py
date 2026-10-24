"""Check denominators, splits and separation of official tables from CSV stats."""
import json
from pathlib import Path
import sys
import unittest
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/live_data'))
from build_team_dashboard import summarize, provider_rows, team_matches, standings_cover_stats, METRICS


class TeamDashboardTests(unittest.TestCase):
    def test_recent_table_must_cover_each_teams_verified_games(self):
        rows=pd.DataFrame({'team':['A','A','B','B'],'is_home':[True,False,True,False]})
        self.assertFalse(standings_cover_stats({'all':[{'team':'A','played':1},{'team':'B','played':3}]},rows))
        self.assertTrue(standings_cover_stats({'all':[{'team':'A','played':2},{'team':'B','played':2}]},rows))
        self.assertFalse(standings_cover_stats({'home':[{'team':'A','played':0},{'team':'B','played':1}]},rows))

    def test_published_standings_do_not_lag_recorded_results(self):
        data=json.loads((ROOT/'web/data/teams.json').read_text(encoding='utf-8'))
        for league in data['competitions'].values():
            tables=league.get('standings',{}).get('tables',{})
            for scope,table in tables.items():
                played={r['team']:r['played'] for r in table}
                for team in league['teams']:
                    self.assertGreaterEqual(played.get(team['team'],0),team['splits'][scope]['played'])

    def test_match_lists_preserve_home_scores_and_deduplicate_calendar(self):
        rows=pd.DataFrame([{'date':pd.Timestamp('2026-10-01'),'opponent':'Rival','is_home':False,'goals_for':1,'goals_against':3}])
        calendar=pd.DataFrame([
            {'date':pd.Timestamp('2026-10-01'),'home_team':'Rival','away_team':'Club','match_id':11,'status':'FINISHED','home_score':3,'away_score':1,'kickoff_time_utc':'19:00'},
            {'date':pd.Timestamp('2026-10-25'),'home_team':'Club','away_team':'Rival','match_id':12,'status':'TIMED','home_score':None,'away_score':None,'kickoff_time_utc':'20:00'},
            {'date':pd.Timestamp('2026-10-26'),'home_team':'Other','away_team':'Rival','match_id':13,'status':'TIMED','home_score':None,'away_score':None,'kickoff_time_utc':'20:00'},
        ])
        result=team_matches(rows,calendar,'Club')
        self.assertEqual(len(result['played']),1)
        self.assertEqual((result['played'][0]['home_score'],result['played'][0]['away_score']),(3,1))
        self.assertEqual(result['played'][0]['fixture_id'],'11')
        self.assertEqual(len(result['scheduled']),1)
        self.assertEqual(result['scheduled'][0]['kickoff_utc'],'2026-10-25T20:00:00+00:00')
        self.assertNotIn('home_score',result['scheduled'][0])

    def test_final_scores_without_stats_and_unknown_kickoff(self):
        calendar=pd.DataFrame([
            {'date':pd.Timestamp('2026-10-02'),'home_team':'Club','away_team':'Rival','match_id':21,'status':'FINISHED','home_score':0,'away_score':0,'kickoff_time_utc':None},
            {'date':pd.Timestamp('2026-10-27'),'home_team':'Rival','away_team':'Club','match_id':22,'status':'SCHEDULED','home_score':None,'away_score':None,'kickoff_time_utc':None},
        ])
        result=team_matches(pd.DataFrame(),calendar,'Club')
        self.assertEqual(result['played'][0]['home_score'],0)
        self.assertIsNone(result['scheduled'][0]['kickoff_utc'])

    def test_missing_metrics_do_not_become_zero(self):
        data={f'{metric}_{side}':[None,6] for metric in METRICS for side in ['for','against']}
        data['goals_for']=[2,1];data['goals_against']=[0,1]
        summary=summarize(pd.DataFrame(data))
        self.assertEqual(summary['played'],2)
        self.assertEqual(summary['points'],4)
        self.assertEqual(summary['metrics']['shots']['for'],{'total':6,'average':6.0,'observations':1})
        self.assertEqual(summary['metrics']['goals']['for']['average'],1.5)

    def test_no_matches_have_no_average(self):
        rows=pd.DataFrame(columns=[f'{metric}_{side}' for metric in METRICS for side in ['for','against']])
        result=summarize(rows)
        self.assertEqual(result['played'],0)
        self.assertIsNone(result['metrics']['corners']['for']['average'])
        self.assertIsNone(result['metrics']['corners']['for']['total'])

    def test_provider_points_are_preserved_even_with_deductions(self):
        row={'team':{'id':7,'name':'Different provider name'},'position':3,'playedGames':2,
             'won':2,'draw':0,'lost':0,'points':3,'goalsFor':4,'goalsAgainst':1,'goalDifference':3}
        tables=provider_rows({'standings':[{'type':'TOTAL','stage':'REGULAR_SEASON','table':[row]}]},{7:'Canonical club'})
        self.assertEqual(tables['all'][0]['points'],3)
        self.assertEqual(tables['all'][0]['position'],3)
        self.assertEqual(tables['all'][0]['team'],'Canonical club')

    def test_team_rosters_have_all_clubs_and_crests(self):
        data=json.loads((ROOT/'web/data/teams.json').read_text(encoding='utf-8'))
        assets=json.loads((ROOT/'web/data/assets.json').read_text(encoding='utf-8'))
        counts={'La Liga':20,'Premier League':20,'Bundesliga':18,'Serie A':20,'Ligue 1':18,'UEFA Champions League':36}
        for league,count in counts.items():
            teams=data['competitions'][league]['teams']
            self.assertEqual(len(teams),count,league)
            self.assertEqual(len({t['team'] for t in teams}),count)
            for t in teams:
                self.assertIn(t['team'],assets['teams'])
                self.assertTrue((ROOT/'web'/assets['teams'][t['team']]['image']).is_file())

    def test_splits_reconcile_and_means_use_observed_denominators(self):
        data=json.loads((ROOT/'web/data/teams.json').read_text(encoding='utf-8'))
        for league in data['competitions'].values():
            self.assertEqual(sum(t['splits']['all']['played'] for t in league['teams']),2*league['statistics_matches'])
            for t in league['teams']:
                splits=t['splits'];self.assertEqual(splits['all']['played'],splits['home']['played']+splits['away']['played'])
                for metric in METRICS:
                    for side in ['for','against']:
                        observations=[]
                        for scope in ['home','away','all']:
                            r=splits[scope]['metrics'][metric][side]
                            observations.append(r['observations'])
                            if r['observations']:self.assertAlmostEqual(r['average'],r['total']/r['observations'],places=3)
                            else:self.assertIsNone(r['average'])
                        self.assertEqual(observations[2],sum(observations[:2]))


if __name__=='__main__':unittest.main()
